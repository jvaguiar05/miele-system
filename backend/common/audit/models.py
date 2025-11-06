import uuid
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.conf import settings


class AuditLog(models.Model):
    """
    Modelo para registro de auditoria de todas as ações do sistema.
    """

    class AuditAction(models.TextChoices):
        CREATE = "CREATE", "Criar"
        UPDATE = "UPDATE", "Atualizar"
        DELETE = "DELETE", "Excluir"
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        APPROVAL_REQUESTED = "APPROVAL_REQUESTED", "Aprovação Solicitada"
        APPROVAL_GRANTED = "APPROVAL_GRANTED", "Aprovação Concedida"
        APPROVAL_DENIED = "APPROVAL_DENIED", "Aprovação Negada"
        CUSTOM = "CUSTOM", "Ação Personalizada"

    # Chave primária interna (BigInt) para performance máxima
    id = models.BigAutoField(primary_key=True)
    # ID de correlação para rastrear todas as ações de um request
    correlation_id = models.UUIDField(
        help_text="ID de correlação para rastrear todas as ações de um request"
    )

    # Usuário que executou a ação
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuário que executou a ação",
    )

    # Ação realizada
    action = models.CharField(
        max_length=100,
        choices=AuditAction.choices,
        help_text="Tipo de ação realizada (CREATE, UPDATE, DELETE, etc.)",
    )

    # Recurso afetado (usando Generic Foreign Key)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)
    content_object = GenericForeignKey("content_type", "object_id")

    # Dados da mudança
    old_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Estado anterior do objeto (para UPDATE/DELETE)",
    )
    new_data = models.JSONField(
        null=True, blank=True, help_text="Novo estado do objeto (para CREATE/UPDATE)"
    )

    # Metadata adicional
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Informações adicionais sobre a ação"
    )

    # Informações de request
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, help_text="IP do usuário que executou a ação"
    )
    user_agent = models.TextField(
        null=True, blank=True, help_text="User agent do browser/cliente"
    )

    # Timestamp
    timestamp = models.DateTimeField(
        default=timezone.now, help_text="Momento em que a ação foi executada"
    )

    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["correlation_id"]),
            models.Index(fields=["user"]),
            models.Index(fields=["action"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.content_type.model} by {self.user} at {self.timestamp}"

    @property
    def resource_type(self):
        """Retorna o tipo do recurso afetado."""
        return f"{self.content_type.app_label}.{self.content_type.model}"

    @property
    def resource_id(self):
        """Retorna o ID do recurso afetado."""
        return self.object_id
