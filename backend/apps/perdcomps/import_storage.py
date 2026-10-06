"""Safe, retryable archival of PER/DCOMP originals in Google Drive."""
import hashlib
import io
import logging
import re
import time
import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.services.google_drive import GoogleDriveService
from .document_models import ImportedFile, ManualImportIssue

logger = logging.getLogger(__name__)


class OriginalUnavailable(Exception):
    """Raised when an original cannot be safely delivered."""

    def __init__(self, message, status=503):
        self.status = status
        super().__init__(message)


def _safe(value, fallback):
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", str(value or ""))
        if not unicodedata.combining(char)
    ).upper()
    value = re.sub(r"[^A-Z0-9-]+", "-", value).strip("-")
    return value or fallback


def standardized_drive_name(file):
    """Readable and deterministic; the hash prevents name collisions."""
    fields = file.document.data
    modality = _safe(fields.get("modality"), "PERDCOMP")
    kind = "DCOMP" if "COMPENSACAO" in modality else "PER"
    if fields.get("revision_kind") == "retificadora":
        kind += "-RETIFICADORA"
    cnpj = re.sub(r"\D", "", str(file.client.cnpj)) or "CNPJ-NAO-INFORMADO"
    protocol = (
        re.sub(r"\D", "", str(fields.get("protocol") or file.document.protocol))
        or "SEM-PROTOCOLO"
    )
    official_date = _safe(fields.get("transmitted_on"), "SEM-DATA")
    role = (
        "RECIBO"
        if file.kind == "receipt"
        else "DEMONSTRATIVO"
        if file.kind == "demonstrative"
        else _safe(file.kind, "DOCUMENTO")
    )
    return (
        f"{cnpj}_{kind}_{protocol}_{official_date}_{role}_"
        f"{file.sha256[:12].upper()}.pdf"
    )


def standardized_manual_drive_name(issue):
    """Stable name for a quarantined PDF that still requires human review."""
    cnpj = re.sub(r"\D", "", str(issue.client.cnpj)) or "CNPJ-NAO-INFORMADO"
    return f"{cnpj}_REVISAO-MANUAL_{issue.sha256[:12].upper()}.pdf"


def _configured_folder():
    credentials = all(
        getattr(settings, key, "")
        for key in (
            "GDRIVE_CLIENT_ID",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
        )
    )
    folder = getattr(settings, "GDRIVE_PERDCOMPS_FOLDER_ID", "")
    return credentials, folder if re.fullmatch(r"[A-Za-z0-9_-]+", folder) else ""


def _summary(imported_queryset, manual_queryset):
    total = imported_queryset.count() + manual_queryset.count()
    archived = (
        imported_queryset.exclude(drive_file_id="")
        .filter(original_content__isnull=True)
        .count()
        + manual_queryset.exclude(drive_file_id="")
        .filter(original_content__isnull=True)
        .count()
    )
    database_copies = (
        imported_queryset.filter(original_content__isnull=False).count()
        + manual_queryset.filter(original_content__isnull=False).count()
    )
    pending_drive = (
        imported_queryset.filter(drive_file_id="").count()
        + manual_queryset.filter(drive_file_id="").count()
    )
    pending_release = (
        imported_queryset.exclude(drive_file_id="")
        .filter(original_content__isnull=False)
        .count()
        + manual_queryset.exclude(drive_file_id="")
        .filter(original_content__isnull=False)
        .count()
    )
    unavailable = (
        imported_queryset.filter(drive_file_id="", original_content__isnull=True).count()
        + manual_queryset.filter(drive_file_id="", original_content__isnull=True).count()
    )
    pending = total - archived
    return {
        "status": "synced" if total and not pending else "empty" if not total else "pending",
        "total": total,
        "archived": archived,
        "pending": pending,
        "pending_drive": pending_drive,
        "pending_release": pending_release,
        "database_copies": database_copies,
        "unavailable": unavailable,
    }


def client_storage_summary(client):
    return _summary(
        ImportedFile.objects.filter(client=client),
        ManualImportIssue.objects.filter(client=client),
    )


def global_storage_summary():
    return _summary(ImportedFile.objects.all(), ManualImportIssue.objects.all())


def _properties(record):
    values = {
        "miele_client": str(record.client.public_id),
        "miele_sha256": record.sha256,
        "miele_kind": (
            "manual_review" if isinstance(record, ManualImportIssue) else record.kind
        ),
    }
    if isinstance(record, ImportedFile):
        values["miele_protocol"] = record.document.protocol
    return values


def _remote_is_verified(metadata, raw, properties, folder):
    try:
        remote_size = int(metadata.get("size"))
    except (AttributeError, TypeError, ValueError):
        return False
    remote_properties = metadata.get("appProperties") or {}
    return bool(
        metadata.get("id")
        and not metadata.get("trashed", False)
        and folder in (metadata.get("parents") or [])
        and remote_size == len(raw)
        and metadata.get("md5Checksum") == hashlib.md5(raw).hexdigest()
        and remote_properties.get("miele_client") == properties["miele_client"]
        and remote_properties.get("miele_sha256") == properties["miele_sha256"]
    )


def _find_remote(service, folder, properties):
    query = (
        f"trashed = false and '{folder}' in parents and "
        "appProperties has { key='miele_client' and "
        f"value='{properties['miele_client']}' }} and "
        "appProperties has { key='miele_sha256' and "
        f"value='{properties['miele_sha256']}' }}"
    )
    found = (
        service._get_service()
        .files()
        .list(
            q=query,
            fields="files(id,name,size,md5Checksum,appProperties,parents,trashed)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    return found[0] if found else None


def _sync_one(model, pk, service, folder):
    related = ("client", "document") if model is ImportedFile else ("client",)
    with transaction.atomic():
        record = model.objects.select_for_update().select_related(*related).get(pk=pk)
        if record.original_content is None:
            return False

        raw = bytes(record.original_content)
        if hashlib.sha256(raw).hexdigest() != record.sha256:
            raise ValueError("database checksum mismatch")
        properties = _properties(record)
        name = (
            standardized_drive_name(record)
            if model is ImportedFile
            else standardized_manual_drive_name(record)
        )

        if record.drive_file_id:
            metadata = service.get_file_metadata(record.drive_file_id)
        else:
            metadata = _find_remote(service, folder, properties)
            if metadata and metadata.get("name") != name:
                service.update_file(metadata["id"], new_name=name)
            if not metadata:
                metadata = service.upload_stream_metadata(
                    io.BytesIO(raw),
                    name,
                    "perdcomp",
                    "application/pdf",
                    app_properties=properties,
                )

        # Verify the persisted object instead of trusting the upload response.
        metadata = service.get_file_metadata(metadata.get("id"))
        if not _remote_is_verified(metadata, raw, properties, folder):
            raise ValueError("drive verification mismatch")

        now = timezone.now()
        record.drive_file_id = metadata["id"]
        record.drive_size = len(raw)
        record.drive_md5 = hashlib.md5(raw).hexdigest()
        record.drive_synced_at = now
        record.original_content = None
        record.database_released_at = now
        record.save(
            update_fields=[
                "drive_file_id",
                "drive_size",
                "drive_md5",
                "drive_synced_at",
                "original_content",
                "database_released_at",
            ]
        )
        return True


def _sync(imported_queryset, manual_queryset, limit=5):
    summary = _summary(imported_queryset, manual_queryset)
    credentials, folder = _configured_folder()
    if not credentials:
        summary.update(
            status="database",
            processed=0,
            released=0,
            synced=0,
            message=(
                "PDFs protegidos no banco. Configure as credenciais do Google Drive "
                "para concluir o arquivamento."
            ),
        )
        return summary
    if not folder:
        summary.update(
            status="pending",
            processed=0,
            released=0,
            synced=0,
            message=(
                "PDFs protegidos no banco. Configure GDRIVE_PERDCOMPS_FOLDER_ID "
                "para concluir o arquivamento."
            ),
        )
        return summary

    limit = min(max(int(limit or 5), 1), 5)
    candidates = []
    imported_pending = imported_queryset.filter(original_content__isnull=False)
    manual_pending = manual_queryset.filter(original_content__isnull=False)
    # Reserve one slot for manual-review PDFs when both queues have work, so
    # a problematic imported file cannot starve the quarantine queue.
    imported_limit = limit - 1 if limit > 1 and manual_pending.exists() else limit
    imported_ids = list(
        imported_pending.order_by("pk").values_list("pk", flat=True)[:imported_limit]
    )
    candidates.extend((ImportedFile, pk) for pk in imported_ids)
    remaining = limit - len(candidates)
    if remaining:
        manual_ids = list(
            manual_pending.order_by("pk").values_list("pk", flat=True)[:remaining]
        )
        candidates.extend((ManualImportIssue, pk) for pk in manual_ids)

    processed = 0
    released = 0
    failed = 0
    service = GoogleDriveService(request_timeout=15)
    started = time.monotonic()
    for model, pk in candidates:
        if time.monotonic() - started > 60:
            break
        processed += 1
        try:
            released += int(_sync_one(model, pk, service, folder))
        except Exception as exc:
            # Never log PDF contents, OAuth values, URLs or third-party bodies.
            logger.warning("Falha segura ao arquivar PER/DCOMP: %s", type(exc).__name__)
            failed += 1

    summary = _summary(imported_queryset, manual_queryset)
    if summary["unavailable"]:
        message = (
            f"{released} PDF(s) arquivado(s). {summary['unavailable']} registro(s) "
            "não possuem cópia disponível e precisam ser restaurados do backup."
        )
    elif failed:
        message = (
            f"{released} PDF(s) arquivado(s). {failed} permaneceram protegidos "
            "no banco e podem ser tentados novamente."
        )
    elif summary["pending"]:
        message = (
            f"{released} PDF(s) arquivado(s). Continue para concluir os "
            f"{summary['pending']} restante(s)."
        )
    else:
        message = "Todos os PDFs foram verificados no Drive e liberados do banco."
    summary.update(
        processed=processed,
        released=released,
        synced=released,
        failed=failed,
        message=message,
    )
    return summary


def sync_originals(queryset, limit=5):
    """Backward-compatible imported-file queue used by older callers/tests."""
    return _sync(queryset, ManualImportIssue.objects.none(), limit=limit)


def sync_client_storage(client, limit=5):
    return _sync(
        ImportedFile.objects.filter(client=client),
        ManualImportIssue.objects.filter(client=client),
        limit=limit,
    )


def sync_all_storage(limit=5):
    return _sync(ImportedFile.objects.all(), ManualImportIssue.objects.all(), limit=limit)


def read_original(record):
    """Read from the transition DB copy or transparently fetch from Drive."""
    if record.original_content is not None:
        raw = bytes(record.original_content)
    elif record.drive_file_id:
        credentials, folder = _configured_folder()
        if not credentials or not folder:
            raise OriginalUnavailable(
                "O arquivo está no Google Drive, mas o acesso não está configurado. "
                "Solicite ao administrador a renovação da conexão."
            )
        try:
            raw = GoogleDriveService(request_timeout=20).download_stream(
                record.drive_file_id
            ).getvalue()
        except Exception as exc:
            logger.warning(
                "Falha segura ao obter original de PER/DCOMP: %s", type(exc).__name__
            )
            raise OriginalUnavailable(
                "Não foi possível obter o PDF no Google Drive agora. Tente novamente "
                "ou solicite ao administrador a verificação da conexão."
            ) from None
    else:
        raise OriginalUnavailable(
            "O PDF original não está disponível. Solicite ao administrador a restauração "
            "a partir do backup."
        )

    if hashlib.sha256(raw).hexdigest() != record.sha256:
        raise OriginalUnavailable(
            "O PDF armazenado não corresponde ao registro. O download foi bloqueado "
            "para proteger a integridade dos dados.",
            status=409,
        )
    return raw
