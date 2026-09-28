"""Read-only operational dashboard. Dates are calendar dates, money is Decimal."""
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.identity.permissions import IsEmployeeOrAdmin
from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp
from apps.perdcomps.deadlines import business_day, alert_start, OPEN_STATUSES


def money(value):
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).replace("R$", "").replace(" ", "").strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(raw)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def operations(request):
    return Response(build_operations_data())


def build_operations_data():
    today = timezone.localdate()
    clients = {c.id: c for c in Client.objects.filter(is_active=True, deleted_at__isnull=True)}
    records = PerDcomp.objects.filter(is_active=True, deleted_at__isnull=True, client_id__in=clients)
    counts, companies, alerts = Counter(), {}, []
    total, balance, missing = Decimal(0), Decimal(0), 0
    transmitted_count = 0
    open_statuses = OPEN_STATUSES
    for p in records.iterator():
        counts[p.status] += 1
        client = clients[p.client_id]
        item = companies.setdefault(p.client_id, {"id": str(client.public_id), "name": client.razao_social, "count": 0, "amount": Decimal(0)})
        transmitted = p.data_transmissao and p.data_transmissao <= today and p.status not in {"RASCUNHO", "CANCELADO"}
        if transmitted:
            transmitted_count += 1
            item["count"] += 1
            amount = money(p.valor_pedido)
            if amount is None:
                missing += 1
            else:
                total += amount
                item["amount"] += amount
        if p.status in open_statuses:
            amount = money(p.valor_saldo)
            if amount is None:
                missing += 1
            else:
                balance += amount
            due = p.data_vencimento
            if due and today >= alert_start(due):
                severity = "overdue" if due < today else "today" if due == today else "upcoming"
                days = sum(business_day(today + timedelta(days=i)) for i in range(1, max(0, (due - today).days) + 1))
                alerts.append({"id": str(p.public_id), "number": p.numero_perdcomp, "client": client.razao_social, "client_id": str(client.public_id), "cnpj": client.cnpj, "status": p.status, "status_label": p.get_status_display(), "balance": str(amount) if amount is not None else None, "due": due.isoformat(), "severity": severity, "business_days": days})
    alerts.sort(key=lambda a: (a["due"], a["number"]))
    quarter = (today.month - 1) // 3 + 1
    end = date(today.year + 1, 1, 1) if quarter == 4 else date(today.year, quarter * 3 + 1, 1)
    end -= timedelta(days=1)
    return {
        "generated_at": timezone.now().isoformat(), "reference_date": today.isoformat(),
        "clients": len(clients), "processes": sum(counts.values()),
        "transmitted_count": transmitted_count, "transmitted_amount": str(total),
        "balance": str(balance), "missing_values": missing,
        "quarter": quarter, "quarter_end": end.isoformat(),
        "quarter_alert": 0 <= (end - today).days <= 7 and balance > 0,
        "alerts": alerts,
        "statuses": [{"status": key, "label": label, "count": counts[key]} for key, label in PerDcomp.Status.choices],
        "companies": [{**c, "amount": str(c["amount"])} for c in sorted(companies.values(), key=lambda c: c["amount"], reverse=True) if c["count"]],
    }
