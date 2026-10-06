"""Durable DB originals with retryable Drive archival after publication commits."""
import io
import re
import time
import unicodedata
from django.conf import settings
from django.db import transaction
from common.services.google_drive import GoogleDriveService
from .document_models import ImportedFile


def _safe(value, fallback):
    value = "".join(char for char in unicodedata.normalize("NFD", str(value or ""))
                    if not unicodedata.combining(char)).upper()
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
    protocol = re.sub(r"\D", "", str(fields.get("protocol") or file.document.protocol)) or "SEM-PROTOCOLO"
    official_date = _safe(fields.get("transmitted_on"), "SEM-DATA")
    role = "RECIBO" if file.kind == "receipt" else "DEMONSTRATIVO" if file.kind == "demonstrative" else _safe(file.kind, "DOCUMENTO")
    return f"{cnpj}_{kind}_{protocol}_{official_date}_{role}_{file.sha256[:12].upper()}.pdf"


def sync_originals(queryset, limit=5):
    credentials = all(getattr(settings, key, "") for key in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    if not credentials:
        return {"status": "database", "synced": 0, "pending": queryset.filter(drive_file_id="").count(),
                "message": "Originais preservados no banco; Drive não configurado neste ambiente."}
    folder = getattr(settings, "GDRIVE_PERDCOMPS_FOLDER_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", folder):
        return {"status": "pending", "synced": 0, "pending": queryset.filter(drive_file_id="").count(),
                "message": "Originais preservados. Configure GDRIVE_PERDCOMPS_FOLDER_ID para arquivar no Drive."}
    synced = 0
    failed = False
    service = GoogleDriveService(request_timeout=15)
    started = time.monotonic()
    ids = list(queryset.filter(drive_file_id="").values_list("pk", flat=True)[:limit])
    for pk in ids:
        if time.monotonic() - started > 60:
            break
        try:
            with transaction.atomic():
                file = ImportedFile.objects.select_for_update().select_related("client", "document").get(pk=pk)
                if file.drive_file_id:
                    continue
                properties = {"miele_client": str(file.client.public_id), "miele_sha256": file.sha256,
                              "miele_protocol": file.document.protocol, "miele_kind": file.kind}
                drive_name = standardized_drive_name(file)
                q = f"trashed = false and '{folder}' in parents and appProperties has {{ key='miele_client' and value='{properties['miele_client']}' }} and appProperties has {{ key='miele_sha256' and value='{file.sha256}' }}"
                found = service._get_service().files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
                if found:
                    file.drive_file_id = found[0]["id"]
                    if found[0].get("name") != drive_name:
                        service.update_file(file.drive_file_id, new_name=drive_name)
                else:
                    file.drive_file_id = service.upload_stream(io.BytesIO(bytes(file.original_content)), drive_name,
                        "perdcomp", "application/pdf", app_properties=properties)
                file.save(update_fields=["drive_file_id"])
                synced += 1
        except Exception:
            # Never log PDF contents, token values or third-party exception bodies.
            failed = True
            break
    pending = queryset.filter(drive_file_id="").count()
    return {"status": "pending" if pending else "synced", "synced": synced, "pending": pending,
            "message": "Originais preservados. Drive indisponível: confira autorização e acesso à pasta; a sincronização pode ser repetida." if failed else
            "Originais preservados; há PDFs aguardando sincronização com o Drive." if pending else "Originais preservados e sincronizados com o Drive."}
