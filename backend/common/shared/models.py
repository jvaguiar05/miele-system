from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import uuid


class Annotation(models.Model):
    """Modelo compartilhado para anotações de qualquer entidade."""

    # Não auditar anotações (são apenas agregados)
    __audit__ = False

    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Generic Foreign Key para qualquer entidade
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Dados da anotação
    user_id = models.BigIntegerField(help_text="ID do usuário que criou a anotação")
    content = models.JSONField(
        help_text="Conteúdo da anotação em formato JSON", default=dict, blank=True
    )

    # Controle de datas
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "common_annotations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Anotação de {self.content_object} por User#{self.user_id}"

    @property
    def user(self):
        """Propriedade para acessar o usuário (lazy loading)."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=self.user_id)
        except User.DoesNotExist:
            return None

    def soft_delete(self):
        """Exclusão lógica da anotação."""
        self.deleted_at = timezone.now()
        self.save()


# --- LISTAS DE OPÇÕES (Regra de Negócio) ---
CLIENT_FILE_TYPES = [
    ("contrato", "Contrato"),
    ("cartao_cnpj", "Cartão CNPJ"),
    ("procuracao", "Procuração"),
    ("outros", "Outros"),
]

PERDCOMP_FILE_TYPES = [
    ("recibo", "Recibo de Transmissão"),
    ("aviso_recebimento", "Aviso de Recebimento"),
    ("perdcomp", "PER/DCOMP Completa"),
    ("outros", "Outros"),
]


def get_file_type_choices(content_type_name: str):
    """
    Retorna a lista de tuplas (key, label) baseada na entidade.
    Ex: get_file_type_choices('client') -> CLIENT_FILE_TYPES
    """
    mapping = {"client": CLIENT_FILE_TYPES, "perdcomp": PERDCOMP_FILE_TYPES}
    return mapping.get(content_type_name, [])


class AttachedFile(models.Model):
    """
    Modelo híbrido:
    - Dados de Negócio (file_type, description) -> Uso do Miele System
    - Dados Técnicos (drive_file_id, mime_type) -> Uso do Proxy/Drive
    """

    __audit__ = False

    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Vínculo Genérico (Cliente ou PerDcomp)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # --- CAMPOS DE NEGÓCIO (Sua lógica original) ---
    file_type = models.CharField(
        max_length=50,
        help_text="Categoria de negócio (ex: contrato, recibo). Validado via Serializer.",
    )
    description = models.TextField(
        blank=True, null=True, help_text="Descrição opcional para o usuário"
    )

    # --- CAMPOS TÉCNICOS / PROXY (Infraestrutura) ---
    file_name = models.CharField(
        max_length=255, help_text="Nome original do arquivo (ex: scan.pdf)"
    )
    file_size = models.PositiveBigIntegerField(help_text="Tamanho em bytes")

    # MIME Type é crucial para o Download Proxy funcionar corretamente (FileResponse)
    mime_type = models.CharField(
        max_length=100,
        help_text="Tipo MIME para o navegador (ex: application/pdf)",
        default="application/octet-stream",
    )

    drive_file_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="ID do arquivo no Google Drive (Service Account)",
    )

    # Campo para metadados extras condicionais
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Metadados extras condicionais (ex: data de validade para contratos)",
    )

    # Metadados de Auditoria
    uploaded_by_id = models.BigIntegerField(help_text="ID do usuário que fez upload")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "common_attached_files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),  # Busca por entidade
            models.Index(fields=["drive_file_id"]),  # Busca pelo Drive
            models.Index(fields=["file_type"]),  # Filtro de tela
        ]

    def __str__(self):
        return f"{self.file_name} ({self.file_type})"

    @property
    def uploaded_by(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=self.uploaded_by_id)
        except User.DoesNotExist:
            return None

    @property
    def file_size_human(self):
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
