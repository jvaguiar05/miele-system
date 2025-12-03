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
        # Removed unique constraint to allow multiple annotations per user per entity
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


class AttachedFile(models.Model):
    """Modelo compartilhado para arquivos anexados a qualquer entidade."""

    # Não auditar arquivos anexos (são apenas agregados)
    __audit__ = False

    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Generic Foreign Key para qualquer entidade
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Dados do arquivo
    file_type = models.CharField(
        max_length=50, help_text="Tipo do arquivo (específico por entidade)"
    )
    file_name = models.CharField(max_length=255)
    file_url = models.URLField(max_length=500)
    file_size = models.PositiveBigIntegerField(help_text="Tamanho do arquivo em bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    # Controle de upload
    uploaded_by_id = models.BigIntegerField(help_text="ID do usuário que fez o upload")

    # Controle de datas
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "common_attached_files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["file_type"]),
            models.Index(fields=["uploaded_by_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.file_type}) - {self.content_object}"

    @property
    def uploaded_by(self):
        """Propriedade para acessar o usuário que fez upload (lazy loading)."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(id=self.uploaded_by_id)
        except User.DoesNotExist:
            return None

    def soft_delete(self):
        """Exclusão lógica do arquivo."""
        self.deleted_at = timezone.now()
        self.save()

    @property
    def file_size_human(self):
        """Retorna o tamanho do arquivo em formato legível."""
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"


# Choices para tipos de arquivo por entidade
CLIENT_FILE_TYPES = [
    ("contrato", "Contrato"),
    ("cartao_cnpj", "Cartão CNPJ"),
]

PERDCOMP_FILE_TYPES = [
    ("recibo", "Recibo"),
    ("aviso_recebimento", "Aviso Recebimento"),
    ("perdcomp", "PER/DCOMP"),
]


def get_file_type_choices(content_type_name):
    """Retorna as opções de tipo de arquivo baseadas na entidade."""
    choices_map = {
        "client": CLIENT_FILE_TYPES,
        "perdcomp": PERDCOMP_FILE_TYPES,
    }
    return choices_map.get(content_type_name, [])
