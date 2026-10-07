"""Durable, bounded quota for OCR executed inside the web process."""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .document_models import OcrDailyUsage

logger = logging.getLogger(__name__)


def _limit(name, default):
    try:
        return max(0, int(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return default


def _reset_at(usage_date):
    midnight = datetime.combine(usage_date + timedelta(days=1), time.min)
    return timezone.make_aware(midnight, timezone.get_current_timezone())


@dataclass
class OcrQuotaReservation:
    usage_date: object
    user_id: int
    reserved_pages: int
    per_operation_limit: int
    user_limit: int
    global_limit: int
    user_used_before: int
    global_used_before: int
    actual_pages: int = 0
    finalized: bool = False
    quota_exceeded: bool = False
    _payload: dict | None = field(default=None, repr=False)

    @property
    def remaining(self):
        return max(0, self.reserved_pages - self.actual_pages)

    @property
    def reset_at(self):
        return _reset_at(self.usage_date)

    def record(self, pages):
        pages = max(0, int(pages or 0))
        if pages > self.remaining:
            raise ValueError("OCR executou mais p\u00e1ginas do que a reserva autorizada.")
        self.actual_pages += pages

    def exceeded_message(self, required_pages):
        self.quota_exceeded = True
        required_pages = max(1, int(required_pages or 1))
        user_used = self.user_used_before + self.actual_pages
        global_used = self.global_used_before + self.actual_pages
        available = min(
            self.remaining,
            max(0, self.user_limit - user_used),
            max(0, self.global_limit - global_used),
        )
        reset = timezone.localtime(self.reset_at).strftime("%d/%m/%Y %H:%M")
        return (
            f"OCR online n\u00e3o executado: este PDF requer {required_pages} p\u00e1gina(s), "
            f"mas o saldo desta opera\u00e7\u00e3o \u00e9 {available}. Consumo hoje: usu\u00e1rio "
            f"{user_used}/{self.user_limit}, global {global_used}/{self.global_limit}; "
            f"renova em {reset}. Prepare o PDF com o Miele OCR Local e envie o "
            "pacote .miele.zip pelo mesmo bot\u00e3o Importar."
        )


@transaction.atomic
def reserve_online_ocr(user):
    usage_date = timezone.localdate()
    operation_limit = min(20, _limit("PERDCOMP_OCR_OPERATION_PAGES", 5))
    user_limit = _limit("PERDCOMP_OCR_USER_DAILY_PAGES", 10)
    global_limit = _limit("PERDCOMP_OCR_GLOBAL_DAILY_PAGES", 40)
    row, _ = OcrDailyUsage.objects.select_for_update().get_or_create(
        usage_date=usage_date,
        defaults={"global_pages": 0, "per_user": {}},
    )
    per_user = dict(row.per_user or {})
    user_key = str(user.pk)
    user_used = max(0, int(per_user.get(user_key, 0) or 0))
    global_used = max(0, int(row.global_pages or 0))
    reserved = max(0, min(
        operation_limit,
        user_limit - user_used,
        global_limit - global_used,
    ))
    if reserved:
        row.global_pages = global_used + reserved
        per_user[user_key] = user_used + reserved
        row.per_user = per_user
        row.save(update_fields=["global_pages", "per_user", "updated_at"])
    return OcrQuotaReservation(
        usage_date=usage_date,
        user_id=user.pk,
        reserved_pages=reserved,
        per_operation_limit=operation_limit,
        user_limit=user_limit,
        global_limit=global_limit,
        user_used_before=user_used,
        global_used_before=global_used,
    )


@transaction.atomic
def finalize_online_ocr(reservation):
    if reservation.finalized:
        return reservation._payload
    row = OcrDailyUsage.objects.select_for_update().get(
        usage_date=reservation.usage_date
    )
    per_user = dict(row.per_user or {})
    user_key = str(reservation.user_id)
    refund = max(0, reservation.reserved_pages - reservation.actual_pages)
    if refund:
        row.global_pages = max(0, int(row.global_pages or 0) - refund)
        per_user[user_key] = max(0, int(per_user.get(user_key, 0) or 0) - refund)
        row.per_user = per_user
        row.save(update_fields=["global_pages", "per_user", "updated_at"])
    user_used = max(0, int(per_user.get(user_key, 0) or 0))
    global_used = max(0, int(row.global_pages or 0))
    reservation._payload = {
        "per_operation_limit": reservation.per_operation_limit,
        "user_limit": reservation.user_limit,
        "user_used": user_used,
        "user_remaining": max(0, reservation.user_limit - user_used),
        "global_limit": reservation.global_limit,
        "global_used": global_used,
        "global_remaining": max(0, reservation.global_limit - global_used),
        "reset_at": reservation.reset_at.isoformat(),
        "best_effort": False,
    }
    reservation.finalized = True
    if reservation.actual_pages or reservation.quota_exceeded:
        logger.info(
            "OCR online finalizado: pages=%s reserved=%s user_used=%s global_used=%s quota_exceeded=%s",
            reservation.actual_pages,
            reservation.reserved_pages,
            user_used,
            global_used,
            reservation.quota_exceeded,
        )
    return reservation._payload
