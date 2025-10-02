from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Address(models.Model):
    """
    Modelo para endereços.
    """

    # Flag para auditoria automática
    __audit__ = True

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    logradouro = models.CharField(max_length=255, help_text="Logradouro")
    numero = models.CharField(max_length=20, help_text="Número")
    complemento = models.CharField(max_length=255, blank=True, help_text="Complemento")
    bairro = models.CharField(max_length=100, help_text="Bairro")
    municipio = models.CharField(max_length=100, help_text="Município")
    uf = models.CharField(max_length=2, help_text="UF")
    cep = models.CharField(max_length=10, help_text="CEP")

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

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
        max_length=255, blank=True, help_text="Nome fantasia do cliente"
    )
    cnpj = models.CharField(max_length=18, unique=True, help_text="CNPJ do cliente")
    inscricao_estadual = models.TextField(blank=True, help_text="Inscrição estadual")
    inscricao_municipal = models.TextField(blank=True, help_text="Inscrição municipal")
    tipo_empresa = models.TextField(blank=True, help_text="Tipo da empresa")
    recuperacao_judicial = models.BooleanField(
        default=False, help_text="Em recuperação judicial"
    )

    # Contatos comerciais
    telefone_comercial = models.TextField(blank=True, help_text="Telefone comercial")
    email_comercial = models.CharField(
        max_length=255, blank=True, help_text="Email comercial"
    )
    website = models.TextField(blank=True, help_text="Website da empresa")

    # Contatos diretos
    telefone_contato = models.TextField(blank=True, help_text="Telefone de contato")
    email_contato = models.TextField(blank=True, help_text="Email de contato")

    # Dados societários e estruturais
    quadro_societario = models.JSONField(
        default=list, blank=True, help_text="Quadro societário (lista de sócios)"
    )
    cargos = models.JSONField(
        default=dict, blank=True, help_text="Cargos e responsabilidades"
    )
    responsavel_financeiro = models.TextField(
        blank=True, help_text="Responsável financeiro"
    )
    contador_responsavel = models.TextField(
        blank=True, help_text="Contador responsável"
    )

    # Dados fiscais
    cnaes = models.JSONField(default=list, blank=True, help_text="CNAEs da empresa")
    regime_tributacao = models.CharField(
        max_length=20,
        choices=RegimeTributacao.choices,
        blank=True,
        help_text="Regime de tributação",
    )

    # Documentos e contratos
    contrato_social = models.TextField(blank=True, help_text="Dados do contrato social")
    ultima_alteracao_contratual = models.DateTimeField(
        null=True, blank=True, help_text="Data da última alteração contratual"
    )
    rg_cpf_socios = models.TextField(blank=True, help_text="RG/CPF dos sócios")
    certificado_digital = models.TextField(
        blank=True, help_text="Informações do certificado digital"
    )

    # Controles
    autorizado_para_envio = models.BooleanField(
        default=False, help_text="Autorizado para envio"
    )
    atividades = models.JSONField(
        default=dict, blank=True, help_text="Atividades da empresa"
    )

    # Status e controle
    client_status = models.CharField(
        max_length=20,
        choices=ClientStatus.choices,
        default=ClientStatus.PENDING,
        help_text="Status do cliente",
    )
    is_active = models.BooleanField(default=True, help_text="Cliente ativo no sistema")

    # Relacionamentos - FK usando ID interno (BigInt)
    address_id = models.BigIntegerField(
        null=True, blank=True, help_text="ID do endereço do cliente"
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
            models.Index(fields=["address_id"]),
        ]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    @property
    def address(self):
        """Propriedade para acessar o endereço relacionado."""
        if self.address_id:
            try:
                return Address.objects.get(id=self.address_id, deleted_at__isnull=True)
            except Address.DoesNotExist:
                return None
        return None

    def soft_delete(self):
        """Exclusão lógica."""
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()

    def restore(self):
        """Restaurar cliente excluído."""
        self.deleted_at = None
        self.is_active = True
        self.save()


class ClientAnnotation(models.Model):
    """
    Modelo para anotações de clientes feitas por usuários.
    """

    # Flag para auditoria automática
    __audit__ = True

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # FK's usando ID interno (BigInt)
    client_id = models.BigIntegerField(help_text="ID do cliente relacionado à anotação")
    user_id = models.BigIntegerField(help_text="ID do usuário que fez a anotação")

    content = models.TextField(help_text="Conteúdo da anotação")

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "client_annotations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["client_id"]),
            models.Index(fields=["user_id"]),
            models.Index(fields=["created_at"]),
        ]

    @property
    def client(self):
        """Propriedade para acessar o cliente relacionado."""
        if self.client_id:
            try:
                return Client.objects.get(id=self.client_id, deleted_at__isnull=True)
            except Client.DoesNotExist:
                return None
        return None

    @property
    def user(self):
        """Propriedade para acessar o usuário relacionado."""
        if self.user_id:
            try:
                return User.objects.get(id=self.user_id, deleted_at__isnull=True)
            except User.DoesNotExist:
                return None
        return None

    def __str__(self):
        client_name = (
            self.client.razao_social if self.client else "Cliente desconhecido"
        )
        user_name = self.user.username if self.user else "Usuário desconhecido"
        return f"Anotação de {user_name} para {client_name}"


class ClientAttachedFile(models.Model):
    """
    Modelo para arquivos anexados aos clientes.
    """

    # Flag para auditoria automática
    __audit__ = True

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # FK's usando ID interno (BigInt)
    client_id = models.BigIntegerField(
        help_text="ID do cliente ao qual o arquivo está anexado"
    )
    uploaded_by_id = models.BigIntegerField(help_text="ID do usuário que fez o upload")

    file_name = models.CharField(max_length=255, help_text="Nome do arquivo")
    file_url = models.URLField(help_text="URL do arquivo no servidor")
    file_size = models.BigIntegerField(
        null=True, blank=True, help_text="Tamanho do arquivo em bytes"
    )
    file_type = models.CharField(
        max_length=100, blank=True, help_text="Tipo MIME do arquivo"
    )
    description = models.TextField(blank=True, help_text="Descrição do arquivo")

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "client_attached_files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["client_id"]),
            models.Index(fields=["uploaded_by_id"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["file_type"]),
        ]

    @property
    def client(self):
        """Propriedade para acessar o cliente relacionado."""
        if self.client_id:
            try:
                return Client.objects.get(id=self.client_id, deleted_at__isnull=True)
            except Client.DoesNotExist:
                return None
        return None

    @property
    def uploaded_by(self):
        """Propriedade para acessar o usuário que fez upload."""
        if self.uploaded_by_id:
            try:
                return User.objects.get(id=self.uploaded_by_id, deleted_at__isnull=True)
            except User.DoesNotExist:
                return None
        return None

    def __str__(self):
        client_name = (
            self.client.razao_social if self.client else "Cliente desconhecido"
        )
        return f"{self.file_name} - {client_name}"
