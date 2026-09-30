from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class QuarterSnapshot(models.Model):
    """Stored positions are append-only through the application API."""
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    year = models.PositiveSmallIntegerField()
    quarter = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=10, choices=[("position", "Posição parcial"), ("closing", "Fechamento")])
    captured_at = models.DateTimeField(default=timezone.now)
    captured_by = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    payload = models.JSONField()

    class Meta:
        ordering = ["-captured_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["year", "quarter"], condition=models.Q(kind="closing"), name="one_closing_per_quarter"),
        ]


class Address(models.Model):
    """
    Modelo para endereços.
    """

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    logradouro = models.CharField(max_length=255, blank=True, help_text="Logradouro")
    numero = models.CharField(max_length=20, blank=True, help_text="Número")
    complemento = models.CharField(max_length=255, blank=True, help_text="Complemento")
    bairro = models.CharField(max_length=100, blank=True, help_text="Bairro")
    municipio = models.CharField(max_length=100, blank=True, help_text="Município")
    uf = models.CharField(max_length=2, blank=True, help_text="UF")
    cep = models.CharField(max_length=10, blank=True, help_text="CEP")

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    # Note: No deleted_at for Address - hard delete via CASCADE when client is deleted

    class Meta:
        db_table = "addresses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["cep"]),
            models.Index(fields=["municipio"]),
            models.Index(fields=["uf"]),
        ]

    def __str__(self):
        return f"{self.logradouro}, {self.numero} - {self.bairro}, {self.municipio}/{self.uf}"


class Client(models.Model):
    """
    Modelo para clientes do sistema.
    """

    # Flag para auditoria automática
    __audit__ = True

    class ClientStatus(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACTIVE = "active", "Ativo"
        SUSPENDED = "suspended", "Suspenso"
        ARCHIVED = "archived", "Arquivado"

    class RegimeTributacao(models.TextChoices):
        LUCRO_REAL = "lucro_real", "Lucro Real"
        LUCRO_PRESUMIDO = "lucro_presumido", "Lucro Presumido"

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Dados principais
    razao_social = models.CharField(max_length=255, help_text="Razão social do cliente")
    nome_fantasia = models.CharField(
        max_length=255, null=True, blank=True, help_text="Nome fantasia do cliente"
    )
    cnpj = models.CharField(max_length=18, unique=True, help_text="CNPJ do cliente")
    inscricao_estadual = models.TextField(
        null=True, blank=True, help_text="Inscrição estadual"
    )
    inscricao_municipal = models.TextField(
        null=True, blank=True, help_text="Inscrição municipal"
    )
    tipo_empresa = models.TextField(blank=True, help_text="Tipo da empresa")
    recuperacao_judicial = models.BooleanField(
        default=False, help_text="Em recuperação judicial"
    )

    # Contatos comerciais
    telefone_comercial = models.TextField(
        null=True, blank=True, help_text="Telefone comercial"
    )
    email_comercial = models.CharField(
        max_length=255, null=True, blank=True, help_text="Email comercial"
    )
    website = models.TextField(null=True, blank=True, help_text="Website da empresa")

    # Contatos diretos
    telefone_contato = models.TextField(
        null=True, blank=True, help_text="Telefone de contato"
    )
    email_contato = models.TextField(
        null=True, blank=True, help_text="Email de contato"
    )

    # Dados societários e estruturais
    quadro_societario = models.JSONField(
        default=list,
        null=True,
        blank=True,
        help_text="Quadro societário - lista com nome e cargo de cada sócio: [{'nome': 'Nome do Sócio', 'cargo': 'Cargo/Função'}]",
    )
    responsavel_financeiro = models.TextField(
        null=True, blank=True, help_text="Responsável financeiro"
    )
    contador_responsavel = models.TextField(
        null=True, blank=True, help_text="Contador responsável"
    )

    # Dados fiscais
    atividades = models.JSONField(
        default=list,
        blank=True,
        help_text="Atividades da empresa - lista com CNAE e descrição: [{'cnae': 'Código CNAE', 'descricao': 'Descrição da atividade'}]",
    )
    regime_tributacao = models.CharField(
        max_length=20,
        choices=RegimeTributacao.choices,
        null=True,
        blank=True,
        help_text="Regime de tributação",
    )

    # Documentos e contratos
    contrato_social = models.TextField(
        null=True, blank=True, help_text="Dados do contrato social"
    )
    ultima_alteracao_contratual = models.DateField(
        null=True, blank=True, help_text="Data da última alteração contratual"
    )
    rg_cpf_socios = models.TextField(
        null=True, blank=True, help_text="RG/CPF dos sócios"
    )
    certificado_digital = models.TextField(
        null=True, blank=True, help_text="Informações do certificado digital"
    )

    # Controles
    autorizado_para_envio = models.BooleanField(
        default=False, help_text="Autorizado para envio"
    )

    # Status e controle
    client_status = models.CharField(
        max_length=20,
        choices=ClientStatus.choices,
        default=ClientStatus.ACTIVE,
        null=True,
        blank=True,
        help_text="Status do cliente",
    )
    is_active = models.BooleanField(
        default=True, null=True, blank=True, help_text="Cliente ativo no sistema"
    )

    # Relacionamentos
    address = models.OneToOneField(
        Address,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="client",
        help_text="Endereço do cliente",
    )

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "clients"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["cnpj"]),
            models.Index(fields=["client_status"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["address"]),
        ]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    def soft_delete(self):
        """Exclusão lógica do cliente com exclusão física do endereço."""
        # Hard delete do endereço (CASCADE automático)
        if self.address:
            self.address.delete()  # Exclusão física

        # Soft delete do cliente
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()

    def restore(self):
        """Restaurar cliente excluído."""
        self.deleted_at = None
        self.is_active = True

        # Criar novo endereço vazio se não existe
        if not self.address:
            self.address = Address.objects.create(
                logradouro="",
                numero="",
                complemento="",
                bairro="",
                municipio="",
                uf="",
                cep="",
            )

        self.save()


class ClientContract(models.Model):
    """Percentual contratual por vigência; cálculos são apenas informativos."""

    __audit__ = True
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="contracts")
    percentage = models.DecimalField(max_digits=7, decimal_places=4)
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    billing_evolution_requested = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_client_contracts")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_contracts"
        ordering = ["-starts_on", "-id"]
        indexes = [models.Index(fields=["client", "starts_on", "ends_on"])]

    def __str__(self):
        return f"{self.client} - {self.percentage}% desde {self.starts_on}"


class SelicAccumulatedReport(models.Model):
    """Immutable version of an official Sicalc accumulated-rate report."""

    __audit__ = True
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    reference_year = models.PositiveSmallIntegerField()
    reference_month = models.PositiveSmallIntegerField()
    version = models.PositiveSmallIntegerField(default=1)
    issued_on = models.DateField()
    source = models.CharField(max_length=255, default="Sicalc - Receita Federal")
    original_file_name = models.CharField(max_length=255)
    original_file_id = models.CharField(max_length=255, blank=True)
    original_content = models.BinaryField(null=True, blank=True, editable=False)
    file_sha256 = models.CharField(max_length=64, unique=True)
    extracted_data = models.JSONField(default=dict)
    value_count = models.PositiveIntegerField(default=0)
    blank_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    imported_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="imported_selic_reports")
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "selic_accumulated_reports"
        ordering = ["-reference_year", "-reference_month", "-version"]
        constraints = [models.UniqueConstraint(fields=["reference_year", "reference_month", "version"], name="unique_selic_report_version")]


class SelicAccumulatedRate(models.Model):
    """Rate for one origin period, always tied to a report version."""

    __audit__ = True
    report = models.ForeignKey(SelicAccumulatedReport, on_delete=models.CASCADE, related_name="rates")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    rate = models.DecimalField(max_digits=8, decimal_places=2)
    correction_reason = models.TextField(blank=True)
    corrected_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="corrected_selic_rates")
    corrected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "selic_accumulated_rates"
        ordering = ["report", "year", "month"]
        constraints = [
            models.UniqueConstraint(fields=["report", "year", "month"], name="unique_selic_report_month"),
            models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="selic_valid_month"),
            models.CheckConstraint(condition=models.Q(rate__gte=0), name="selic_nonnegative_rate"),
        ]
