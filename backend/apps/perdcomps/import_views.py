import io
import json

from django.core import signing
from django.db import IntegrityError, OperationalError
from django.db.models import F, Prefetch, Value
from django.db.models.functions import Replace
from django.utils import timezone
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.clients.models import Client
from apps.identity.permissions import IsEmployeeOrAdmin
from common.audit.services import AuditService
from .document_models import ImportedDocument, ImportedFile, ManualImportIssue
from .models import PerDcomp
from .import_files import ingest, ImportProblem
from .import_service import (
    apply_reviews, build_preview, manifest, publish, build_reprocess_preview,
    reprocess_manifest, reprocess_documents,
)
from .import_storage import sync_originals
from .import_parser import digits, valid_cnpj

SALT = "miele.perdcomp.documentary.preview.v1"
REPROCESS_SALT = "miele.perdcomp.reprocess.preview.v1"


class ImportThrottle(UserRateThrottle):
    rate = "12/min"
    scope = "documentary_import"


class ClientNotFoundForImport(ImportProblem):
    def __init__(self, cnpj):
        self.cnpj = cnpj
        super().__init__(
            f"Nenhum cliente cadastrado foi encontrado para o CNPJ {cnpj}."
        )


def client_for(client_id):
    return get_object_or_404(Client, public_id=client_id, deleted_at__isnull=True)


def read_input(request):
    try:
        changes = json.loads(request.data.get("changes", "[]"))
    except (ValueError, TypeError):
        raise ImportProblem("Revisões inválidas.") from None
    entries = ingest(request.FILES.getlist("files"))
    apply_reviews(entries, changes, request.user)
    return entries, changes


def client_from_cnpj(cnpj, required=True):
    normalized = Replace(
        Replace(
            Replace(Replace(F("cnpj"), Value("."), Value("")), Value("/"), Value("")),
            Value("-"), Value(""),
        ),
        Value(" "), Value(""),
    )
    matches = list(Client.objects.filter(deleted_at__isnull=True)
                   .annotate(normalized_cnpj=normalized)
                   .filter(normalized_cnpj=cnpj)[:2])
    if not matches:
        if required:
            raise ClientNotFoundForImport(cnpj)
        return None
    if len(matches) > 1:
        raise ImportProblem(
            f"Mais de um cliente corresponde ao CNPJ {cnpj}. Corrija o cadastro antes de importar."
        )
    return matches[0]


def partition_entries(entries):
    """Partition a mixed upload without guessing ownership of ambiguous files."""
    partitions = {}
    pending = []
    protocol_owners = {}
    for entry in entries:
        fields = entry["extraction"].get("fields", {})
        cnpj = digits(fields.get("cnpj"))
        protocol = digits(fields.get("protocol"))
        if valid_cnpj(cnpj):
            partitions.setdefault(cnpj, []).append(entry)
            if protocol:
                protocol_owners.setdefault(protocol, set()).add(cnpj)
        else:
            pending.append(entry)

    unassigned = []
    for entry in pending:
        protocol = digits(entry["extraction"].get("fields", {}).get("protocol"))
        owners = protocol_owners.get(protocol, set()) if protocol else set()
        if len(owners) == 1:
            partitions.setdefault(next(iter(owners)), []).append(entry)
        else:
            unassigned.append(entry)
    return partitions, unassigned


def client_payload(client):
    return {
        "id": str(client.public_id),
        "cnpj": client.cnpj,
        "razao_social": client.razao_social,
        "nome_fantasia": client.nome_fantasia,
    }


def source_summary(entry):
    extraction = entry["extraction"]
    return {
        "index": entry["index"],
        "name": entry["name"],
        "sha256": entry["sha256"],
        "pages": entry["pages"],
        "status": extraction.get("status"),
        "issues": extraction.get("issues", []),
    }


def signed_client_preview(client, scoped_entries, all_entries, changes, user, include_unassigned):
    result = build_preview(client, scoped_entries)
    result["client"] = client_payload(client)
    result["token"] = signing.dumps({
        "client": str(client.public_id),
        "user": user.pk,
        "manifest": manifest(all_entries, changes),
        "scope_cnpj": digits(client.cnpj),
        "include_unassigned": include_unassigned,
    }, salt=SALT, compress=True)
    return result


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ImportThrottle])
def automatic_preview(request):
    """Build one preview or offer safe client selection for a mixed upload."""
    try:
        entries, changes = read_input(request)
        partitions, unassigned = partition_entries(entries)
        if not partitions:
            raise ImportProblem(
                "Não foi possível identificar o CNPJ titular. Confira o PDF ou importe pelo cadastro do cliente."
            )
        if len(partitions) == 1:
            cnpj, scoped = next(iter(partitions.items()))
            client = client_from_cnpj(cnpj)
            return Response(signed_client_preview(
                client, scoped + unassigned, entries, changes, request.user, True,
            ))

        options = []
        for cnpj, scoped in sorted(partitions.items()):
            client = client_from_cnpj(cnpj, required=False)
            option = {
                "cnpj": cnpj,
                "registered": client is not None,
                "client": client_payload(client) if client else None,
                "file_count": len(scoped),
                "document_count": len({digits(entry["extraction"].get("fields", {}).get("protocol"))
                                       for entry in scoped
                                       if digits(entry["extraction"].get("fields", {}).get("protocol"))}),
            }
            if client:
                option["preview"] = signed_client_preview(
                    client, scoped, entries, changes, request.user, False,
                )
                option["importable"] = option["preview"]["counts"]["importable"]
                option["rejected"] = option["preview"]["counts"]["rejected"]
            else:
                option.update(importable=0, rejected=0)
            options.append(option)
        return Response({
            "selection_required": True,
            "clients": options,
            "unassigned_files": [source_summary(entry) for entry in unassigned],
            "counts": {
                "files": len(entries),
                "clients": len(options),
                "unassigned": len(unassigned),
            },
            "notice": "Selecione um cliente. Somente os PDFs associados a ele serão apresentados e registrados.",
        })
    except ClientNotFoundForImport as exc:
        return Response({
            "detail": str(exc),
            "code": "client_not_found",
            "cnpj": exc.cnpj,
            "can_create_client": True,
        }, status=404)
    except ImportProblem as exc:
        return Response({"detail": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ImportThrottle])
def preview(request, client_id):
    client = client_for(client_id)
    try:
        entries, changes = read_input(request)
        partitions, unassigned = partition_entries(entries)
        target_cnpj = digits(client.cnpj)
        scoped = partitions.get(target_cnpj, []) + unassigned
        if not scoped:
            detected = ", ".join(sorted(partitions)) or "nenhum"
            raise ImportProblem(
                f"Nenhum PDF deste lote pertence ao cliente selecionado. CNPJs identificados: {detected}."
            )
        result = signed_client_preview(client, scoped, entries, changes, request.user, True)
        result["batch_selection"] = {
            "other_clients_ignored": sum(len(value) for key, value in partitions.items() if key != target_cnpj),
            "unassigned_included": len(unassigned),
        }
        return Response(result)
    except ImportProblem as exc:
        return Response({"detail": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ImportThrottle])
def confirm(request, client_id):
    client = client_for(client_id)
    try:
        token = signing.loads(request.data.get("token", ""), salt=SALT, max_age=3600)
        if token.get("client") != str(client_id) or token.get("user") != request.user.pk:
            raise ImportProblem("Prévia pertence a outro cliente ou usuário.")
        entries, changes = read_input(request)
        if manifest(entries, changes) != token.get("manifest"):
            raise ImportProblem("Arquivos ou correções mudaram. Gere uma nova prévia.")
        if token.get("scope_cnpj"):
            target_cnpj = digits(client.cnpj)
            if token["scope_cnpj"] != target_cnpj:
                raise ImportProblem("Prévia pertence a outro CNPJ.")
            partitions, unassigned = partition_entries(entries)
            entries = list(partitions.get(target_cnpj, []))
            if token.get("include_unassigned"):
                entries += unassigned
            scoped_hashes = {entry["sha256"] for entry in entries}
            changes = [change for change in changes if change.get("sha256") in scoped_hashes]
            if not entries:
                raise ImportProblem("Nenhum PDF do cliente selecionado permanece neste lote.")
        selected = json.loads(request.data.get("selected", "[]"))
        manual_selected = json.loads(request.data.get("manual_selected", "[]"))
        financial_confirmed = json.loads(request.data.get("financial_confirmed", "[]"))
        ocr_confirmed = json.loads(request.data.get("ocr_confirmed", "[]"))
        if not isinstance(selected, list) or any(not isinstance(k, str) for k in selected):
            raise ImportProblem("Seleção inválida.")
        if not isinstance(manual_selected, list) or any(not isinstance(k, str) for k in manual_selected):
            raise ImportProblem("Seleção de tratamento manual inválida.")
        if not isinstance(financial_confirmed, list) or any(not isinstance(k, str) for k in financial_confirmed):
            raise ImportProblem("Confirmação financeira inválida.")
        if not isinstance(ocr_confirmed, list) or any(not isinstance(k, str) for k in ocr_confirmed):
            raise ImportProblem("Confirmação do OCR inválida.")
        reason = str(request.data.get("reason", ""))
        if len(reason) > 2000:
            raise ImportProblem("Justificativa deve ter até 2.000 caracteres.")
        result = publish(client, entries, selected, changes, request.user, reason, manual_selected,
                         financial_confirmed, ocr_confirmed)
        # Drive is an explicit, independently retryable second step. A network
        # timeout must never disguise a successfully committed publication.
        pending = ImportedFile.objects.filter(client=client, drive_file_id="").count()
        result["storage"] = {"status": "database", "pending": pending,
            "message": "Originais preservados no banco. Use Sincronizar originais com o Drive para arquivá-los na pasta de PER/DCOMPs."}
        return Response(result)
    except signing.BadSignature:
        return Response({"detail": "Prévia inválida ou expirada. Gere uma nova prévia."}, status=400)
    except (ImportProblem, ValueError, TypeError) as exc:
        return Response({"detail": str(exc) if isinstance(exc, ImportProblem) else "Dados de confirmação inválidos."}, status=400)
    except (IntegrityError, OperationalError):
        return Response({"detail": "Importação concorrente ou banco indisponível. Refaça a prévia antes de tentar novamente."}, status=409)


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ImportThrottle])
def preview_file(request, client_id):
    """Download a ZIP member/no-text PDF without persisting a staging batch."""
    client_for(client_id)
    try:
        entries = ingest(request.FILES.getlist("files"))
        target = next((e for e in entries if e["sha256"] == request.data.get("sha256") and e["raw"].startswith(b"%PDF-")), None)
        if not target:
            raise ImportProblem("PDF não encontrado neste lote.")
        response = FileResponse(io.BytesIO(target["raw"]), as_attachment=True, filename=target["name"], content_type="application/pdf")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"
        return response
    except ImportProblem as exc:
        return Response({"detail": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def documents(request, client_id):
    client = client_for(client_id)
    queryset = ImportedDocument.objects.filter(client=client).select_related(
        "superseded_by", "legacy_document").order_by("-created_at")
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
    except ValueError:
        offset = 0
    total = queryset.count()
    items = []
    for document in queryset[offset:offset + 50].prefetch_related(Prefetch("files", queryset=ImportedFile.objects.defer("original_content")), "relations", "debts", "components", "reviews"):
        items.append({"id": str(document.public_id), "key": document.protocol, "fields": document.data,
            "completeness": document.completeness, "fiscal_status": document.fiscal_status,
            "financial_effect": document.financial_effect, "credit_id": document.credit_id,
            "version_status": document.version_status,
            "superseded_by": document.superseded_by.protocol if document.superseded_by_id else None,
            "operational_id": str(document.legacy_document.public_id) if document.legacy_document_id else None,
            "debts": [d.data for d in document.debts.all()], "components": [c.data for c in document.components.all()],
            "relations": [{"kind": r.kind, "protocol": r.target_protocol, "resolved": bool(r.target_id or r.legacy_target_id)} for r in document.relations.all()],
            "files": [{"id": str(f.public_id), "name": f.original_name, "kind": f.kind, "sha256": f.sha256,
                       "extraction": f.extraction, "extracted_at": f.extracted_at.isoformat(), "pages": f.pages,
                       "drive_synced": bool(f.drive_file_id)} for f in document.files.all()],
            "reviews": [{"reviewer": r.reviewer_id, "date": r.created_at.isoformat(), "reason": r.reason, "changes": r.changes} for r in document.reviews.all()]})
    pending = ManualImportIssue.objects.filter(client=client, status=ManualImportIssue.Status.PENDING).defer("original_content").order_by("-created_at")[:100]
    return Response({"results": items, "count": total, "next_offset": offset + 50 if offset + 50 < total else None,
        "manual_issues": [{"id": str(issue.public_id), "name": issue.original_name, "sha256": issue.sha256,
            "pages": issue.pages, "issues": issue.issues, "created_at": issue.created_at.isoformat()}
            for issue in pending]})


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
@throttle_classes([ImportThrottle])
def reprocess_preview(request, client_id):
    client = client_for(client_id)
    result = build_reprocess_preview(client)
    result["token"] = signing.dumps({"client": str(client_id), "user": request.user.pk,
        "manifest": reprocess_manifest(result)}, salt=REPROCESS_SALT, compress=True)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@throttle_classes([ImportThrottle])
def reprocess_confirm(request, client_id):
    client = client_for(client_id)
    try:
        token = signing.loads(str(request.data.get("token", "")), salt=REPROCESS_SALT, max_age=3600)
        preview = build_reprocess_preview(client)
        if (token.get("client") != str(client_id) or token.get("user") != request.user.pk or
                token.get("manifest") != reprocess_manifest(preview)):
            raise ImportProblem("A prévia mudou ou pertence a outro usuário. Gere-a novamente.")
        selected = request.data.get("selected", [])
        financial_confirmed = request.data.get("financial_confirmed", [])
        if (not isinstance(selected, list) or not isinstance(financial_confirmed, list) or
                any(not isinstance(value, str) for value in selected + financial_confirmed)):
            raise ImportProblem("Seleção de documentos inválida.")
        reason = str(request.data.get("reason", ""))
        if len(reason) > 2000:
            raise ImportProblem("Justificativa deve ter até 2.000 caracteres.")
        return Response(reprocess_documents(client, selected, financial_confirmed, request.user, reason))
    except signing.BadSignature:
        return Response({"detail": "Prévia inválida ou expirada. Gere uma nova prévia."}, status=400)
    except ImportProblem as exc:
        return Response({"detail": str(exc)}, status=400)
    except (IntegrityError, OperationalError):
        return Response({"detail": "Operação concorrente ou banco indisponível. Gere uma nova prévia."}, status=409)


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def original(request, client_id, file_id):
    client = client_for(client_id)
    file = get_object_or_404(ImportedFile, client=client, public_id=file_id)
    response = FileResponse(io.BytesIO(bytes(file.original_content)), as_attachment=True,
        filename=file.original_name, content_type="application/pdf")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def manual_original(request, client_id, issue_id):
    client = client_for(client_id)
    issue = get_object_or_404(ManualImportIssue, client=client, public_id=issue_id)
    response = FileResponse(io.BytesIO(bytes(issue.original_content)), as_attachment=True,
        filename=issue.original_name, content_type="application/pdf")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
def resolve_manual(request, client_id, issue_id):
    if request.user.role != "admin":
        return Response({"detail": "Somente administradores podem concluir pendências manuais."}, status=403)
    client = client_for(client_id)
    issue = get_object_or_404(ManualImportIssue, client=client, public_id=issue_id,
        status=ManualImportIssue.Status.PENDING)
    note = str(request.data.get("note", "")).strip()
    if len(note) < 10 or len(note) > 2000:
        return Response({"detail": "Informe uma justificativa de 10 a 2.000 caracteres."}, status=400)
    operational_id = request.data.get("operational_id")
    operational = None
    if operational_id:
        operational = get_object_or_404(PerDcomp, public_id=operational_id, client_id=client.pk, deleted_at__isnull=True)
    action = request.data.get("action")
    if action not in ("resolved", "dismissed") or (action == "resolved" and not operational):
        return Response({"detail": "Para tratar, selecione a PER/DCOMP operacional; ou descarte com justificativa."}, status=400)
    issue.status = ManualImportIssue.Status.RESOLVED if action == "resolved" else ManualImportIssue.Status.DISMISSED
    issue.operational_document = operational
    issue.resolved_by = request.user
    issue.resolution_note = note
    issue.resolved_at = timezone.now()
    issue.save(update_fields=["status", "operational_document", "resolved_by", "resolution_note", "resolved_at"])
    AuditService.log_action("CUSTOM", issue, user=request.user,
        new_data={"status": issue.status, "operational_id": str(operational.public_id) if operational else None},
        metadata={"type": "perdcomp_manual_import_resolution", "reason": note})
    return Response({"status": issue.status})


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
@throttle_classes([ImportThrottle])
def sync_drive(request, client_id):
    if request.user.role != "admin":
        return Response({"detail": "Somente administradores podem sincronizar os originais."}, status=403)
    client = client_for(client_id)
    return Response(sync_originals(ImportedFile.objects.filter(client=client)))
