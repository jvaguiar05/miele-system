from django.db import models
from django.utils import timezone
import uuid


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

    # Identificadores
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Dados principais (sensíveis - requerem aprovação)
    cnpj = models.CharField(max_length=18, unique=True, help_text="CNPJ do cliente")
    razao_social = models.CharField(max_length=255, help_text="Razão social do cliente")
    client_status = models.CharField(
        max_length=20,
        choices=ClientStatus.choices,
        default=ClientStatus.PENDING,
        help_text="Status do cliente",
    )
    is_active = models.BooleanField(default=True, help_text="Cliente ativo no sistema")

    # Dados não sensíveis (não requerem aprovação)
    nome_fantasia = models.CharField(
        max_length=255, blank=True, help_text="Nome fantasia do cliente"
    )
    email = models.EmailField(blank=True, help_text="Email de contato")
    telefone = models.CharField(
        max_length=20, blank=True, help_text="Telefone de contato"
    )
    
    # Campo não sensível para anotações
    annotations = models.TextField(
        blank=True, 
        help_text="Anotações internas sobre o cliente"
    )

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "clients"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["cnpj"]),
            models.Index(fields=["client_status"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

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
