"""Documentary records: deliberately separate from the operational/financial PerDcomp."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class ImportBatch(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    summary = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["client", "fingerprint"], name="unique_documentary_batch")]


class DocumentaryCredit(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT)
    origin_protocol = models.CharField(max_length=24)
    # An anchor, NOT an available credit or an accounting balance.
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["client", "origin_protocol"], name="unique_documentary_credit")]


class ImportedDocument(models.Model):
    class VersionStatus(models.TextChoices):
        CURRENT = "current", "Versão vigente"
        SUPERSEDED = "superseded", "Substituída"
        PREVIOUS = "previous", "Versão anterior — nenhum dado alterado"
        CANCELLED = "cancelled", "Cancelada"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT)
    cnpj = models.CharField(max_length=14)
    protocol = models.CharField(max_length=24)
    protocol_original = models.CharField(max_length=40)
    credit = models.ForeignKey(DocumentaryCredit, null=True, on_delete=models.PROTECT)
    legacy_document = models.ForeignKey("perdcomps.PerDcomp", null=True, on_delete=models.PROTECT)
    modality = models.CharField(max_length=30)
    revision_kind = models.CharField(max_length=16)
    completeness = models.CharField(max_length=30)
    fiscal_status = models.CharField(max_length=24, default="nao_consultada", editable=False)
    financial_effect = models.CharField(max_length=24, default="nao_aplicado", editable=False)
    version_status = models.CharField(max_length=16, choices=VersionStatus.choices, default=VersionStatus.CURRENT)
    superseded_by = models.ForeignKey("self", null=True, on_delete=models.PROTECT, related_name="superseded_documents")
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cnpj", "protocol"], name="unique_documentary_identity")]


class ImportedFile(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT)
    document = models.ForeignKey(ImportedDocument, related_name="files", on_delete=models.PROTECT)
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT)
    sha256 = models.CharField(max_length=64)
    original_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=20)
    pages = models.PositiveSmallIntegerField()
    drive_file_id = models.CharField(max_length=255, blank=True, db_index=True)
    drive_size = models.PositiveBigIntegerField(null=True, editable=False)
    drive_md5 = models.CharField(max_length=32, blank=True, editable=False)
    drive_synced_at = models.DateTimeField(null=True, editable=False)
    database_released_at = models.DateTimeField(null=True, editable=False)
    original_content = models.BinaryField(null=True, editable=False)
    parser_version = models.CharField(max_length=40)
    extracted_at = models.DateTimeField(default=timezone.now)
    extraction = models.JSONField(default=dict)
    # extraction contains field-level page, original text and interpreted values.

    class Meta:
        constraints = [models.UniqueConstraint(fields=["client", "sha256"], name="unique_documentary_file")]


class ManualImportIssue(models.Model):
    """Quarantined PDF that could not safely create an operational record."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        RESOLVED = "resolved", "Tratado"
        DISMISSED = "dismissed", "Descartado"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT)
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT)
    sha256 = models.CharField(max_length=64)
    original_name = models.CharField(max_length=255)
    pages = models.PositiveSmallIntegerField(default=0)
    drive_file_id = models.CharField(max_length=255, blank=True, db_index=True)
    drive_size = models.PositiveBigIntegerField(null=True, editable=False)
    drive_md5 = models.CharField(max_length=32, blank=True, editable=False)
    drive_synced_at = models.DateTimeField(null=True, editable=False)
    database_released_at = models.DateTimeField(null=True, editable=False)
    original_content = models.BinaryField(null=True, editable=False)
    extraction = models.JSONField(default=dict)
    issues = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    operational_document = models.ForeignKey("perdcomps.PerDcomp", null=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="created_manual_import_issues", on_delete=models.PROTECT)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="resolved_manual_import_issues", null=True, on_delete=models.PROTECT)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["client", "sha256"], name="unique_manual_import_file")]


class DocumentRelation(models.Model):
    source = models.ForeignKey(ImportedDocument, related_name="relations", on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    target_protocol = models.CharField(max_length=24)
    target = models.ForeignKey(ImportedDocument, related_name="incoming_relations", null=True, on_delete=models.PROTECT)
    legacy_target = models.ForeignKey("perdcomps.PerDcomp", null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "kind", "target_protocol"], name="unique_documentary_relation")]


class DocumentDebt(models.Model):
    document = models.ForeignKey(ImportedDocument, related_name="debts", on_delete=models.PROTECT)
    sequence = models.PositiveSmallIntegerField()
    principal = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    fine = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    interest = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    total = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    data = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "sequence"], name="unique_documentary_debt")]


class DocumentCreditComponent(models.Model):
    document = models.ForeignKey(ImportedDocument, related_name="components", on_delete=models.PROTECT)
    sequence = models.PositiveSmallIntegerField()
    assessed = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    deductions = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    previous_use = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    balance = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    used = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    data = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "sequence"], name="unique_documentary_component")]


class DocumentUtilization(models.Model):
    document = models.OneToOneField(ImportedDocument, on_delete=models.PROTECT)
    declared = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    applied = models.BooleanField(default=False, editable=False)


class DocumentReview(models.Model):
    document = models.ForeignKey(ImportedDocument, related_name="reviews", on_delete=models.PROTECT)
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    changes = models.JSONField(default=list)
    reason = models.TextField()


class DocumentaryEvent(models.Model):
    """Reserved evidence for future decisions/installments/liquidations/official queries.

    No API creates these or applies financial effects in the documentary importer.
    """
    document = models.ForeignKey(ImportedDocument, on_delete=models.PROTECT)
    kind = models.CharField(max_length=24, choices=[(k, k) for k in (
        "decision", "installment", "liquidation", "official_consultation", "calculation")])
    event_key = models.CharField(max_length=100)
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=22, decimal_places=2, null=True)
    data = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "kind", "event_key"], name="unique_documentary_event")]
