"""Read-only details collected while importing an operational PER/DCOMP."""

from django.db.models import BooleanField, Case, Prefetch, Value, When

from apps.clients.models import Client
from .credit_chain import build_credit_chain_report
from .document_models import ImportedDocument, ImportedFile


def _file_item(file):
    return {
        "id": str(file.public_id),
        "name": file.original_name,
        "kind": file.kind,
        "pages": file.pages,
        "available": bool(file.drive_file_id or file.has_database_original),
        "storage": (
            "drive" if file.drive_file_id and file.database_released_at
            else "transition" if file.drive_file_id
            else "database"
        ),
        "extracted_at": file.extracted_at.isoformat(),
        "extraction": file.extraction,
    }


def _document_item(document):
    return {
        "id": str(document.public_id),
        "protocol": document.protocol,
        "fields": document.data,
        "completeness": document.completeness,
        "fiscal_status": document.fiscal_status,
        "financial_effect": document.financial_effect,
        "version_status": document.version_status,
        "superseded_by": document.superseded_by.protocol if document.superseded_by_id else None,
        "relations": [
            {
                "kind": relation.kind,
                "target_protocol": relation.target_protocol,
                "resolved": bool(relation.target_id or relation.legacy_target_id),
            }
            for relation in document.relations.all()
        ],
        "debts": [debt.data for debt in document.debts.all()],
        "components": [component.data for component in document.components.all()],
        "reviews": [
            {
                "reviewed_at": review.created_at.isoformat(),
                "reviewed_by": review.reviewer.get_full_name() or review.reviewer.username,
                "reason": review.reason,
                "changes": review.changes,
            }
            for review in document.reviews.all()
        ],
        "files": [_file_item(file) for file in document.files.all()],
    }


def build_perdcomp_documentary_detail(perdcomp):
    """Return imported evidence explicitly linked to an operational record."""
    files = ImportedFile.objects.only(
        "id", "public_id", "document_id", "original_name", "kind", "pages",
        "drive_file_id", "database_released_at", "extracted_at", "extraction",
    ).annotate(
        has_database_original=Case(
            When(original_content__isnull=False, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )
    documents = list(
        ImportedDocument.objects.filter(legacy_document=perdcomp)
        .select_related("superseded_by")
        .prefetch_related(
            Prefetch("files", queryset=files),
            "relations__target",
            "relations__legacy_target",
            "debts",
            "components",
            "reviews__reviewer",
        )
        .order_by("created_at", "protocol")
    )
    client = Client.objects.filter(pk=perdcomp.client_id, deleted_at__isnull=True).first()
    if not documents or not client:
        return {
            "has_import": False,
            "client_id": str(client.public_id) if client else None,
            "documents": [],
            "chain": None,
            "calculation": None,
            "message": (
                "Esta PER/DCOMP foi cadastrada manualmente ou ainda não possui "
                "um PDF importado vinculado ao registro operacional."
            ),
        }

    operational_id = str(perdcomp.public_id)
    chain_report = build_credit_chain_report(client)
    chain = next(
        (
            item for item in chain_report["chains"]
            if any(document.get("operational_id") == operational_id for document in item["documents"])
        ),
        None,
    )
    return {
        "has_import": True,
        "client_id": str(client.public_id),
        "documents": [_document_item(document) for document in documents],
        "chain": chain,
        "calculation": chain_report["calculation"],
        "message": None,
    }
