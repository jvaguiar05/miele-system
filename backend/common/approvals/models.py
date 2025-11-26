import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ApprovalRequest(models.Model):
    """
    Modelo para solicitações de aprovação de mudanças críticas no sistema.
    """

    # Disable automatic audit logging for approval requests
    # since they serve as their own audit trail
    __audit__ = False

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pendente"
        EXECUTED = "executed", "Executado"
        CANCELLED = "cancelled", "Cancelado"

    class ApprovalAction(models.TextChoices):
        CREATE = "create", "Criar"
        UPDATE = "update", "Atualizar"
        DELETE = "delete", "Excluir"
        ACTIVATE = "activate", "Ativar"
        DEACTIVATE = "deactivate", "Desativar"
        CUSTOM = "custom", "Ação Personalizada"

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Informações da solicitação
    subject = models.CharField(
        max_length=255, help_text="Assunto da solicitação (ex: 'Ativar cliente XYZ')"
    )
    action = models.CharField(
        max_length=20,
        choices=ApprovalAction.choices,
        help_text="Tipo de ação a ser executada",
    )
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        help_text="Status da solicitação",
    )

    # Dados da mudança
    resource_type = models.CharField(
        max_length=100,
        help_text="Tipo do recurso a ser modificado (ex: 'clients.Client')",
    )
    resource_id = models.CharField(
        max_length=255, help_text="ID do recurso a ser modificado"
    )
    payload_diff = models.JSONField(
        help_text="Diferença dos dados (antes/depois da mudança)"
    )

    # Justificativa
    reason = models.TextField(help_text="Motivo da solicitação")

    # Resultado da decisão (para requests executados)
    was_approved = models.BooleanField(
        null=True,
        blank=True,
        help_text="True se aprovado, False se rejeitado, None se ainda pendente",
    )

    # Usuários envolvidos
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="approval_requests_made",
        help_text="Usuário que fez a solicitação",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests_approved",
        help_text="Usuário que aprovou/rejeitou a solicitação",
    )

    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now, help_text="Momento da criação da solicitação"
    )
    updated_at = models.DateTimeField(
        auto_now=True, help_text="Momento da última atualização"
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, help_text="Momento da aprovação/rejeição"
    )
    executed_at = models.DateTimeField(
        null=True, blank=True, help_text="Momento da execução da mudança"
    )

    # Metadados
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Informações adicionais sobre a solicitação"
    )
    approval_notes = models.TextField(blank=True, help_text="Notas do aprovador")

    class Meta:
        db_table = "approval_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["requested_by"]),
            models.Index(fields=["approved_by"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.subject} - {self.get_status_display()}"

    @property
    def is_pending(self):
        """Verifica se a solicitação está pendente."""
        return self.status == self.ApprovalStatus.PENDING

    @property
    def is_approved(self):
        """Verifica se a solicitação foi aprovada (executada como aprovada)."""
        return self.status == self.ApprovalStatus.EXECUTED and self.was_approved is True

    @property
    def can_be_executed(self):
        """Verifica se a solicitação pode ser executada."""
        return self.status == self.ApprovalStatus.PENDING

    def approve_and_execute(self, approved_by_user, notes=""):
        """Aprova e marca como executada."""
        self.was_approved = True
        self.status = self.ApprovalStatus.EXECUTED
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.executed_at = timezone.now()
        if notes:
            self.approval_notes = notes
        self.save()

    def reject_and_execute(self, approved_by_user, notes=""):
        """Rejeita e marca como executada."""
        self.was_approved = False
        self.status = self.ApprovalStatus.EXECUTED
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.executed_at = timezone.now()
        if notes:
            self.approval_notes = notes
        self.save()

    def cancel(self):
        """Cancela a solicitação."""
        if self.is_pending:
            self.status = self.ApprovalStatus.CANCELLED
            self.save()
