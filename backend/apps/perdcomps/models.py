from django.db import models
from django.contrib.auth import get_user_model
from apps.clients.models import Client

User = get_user_model()


class LossCompensation(models.Model):
    """
    Modelo de perda de compensação (perdcomp) com auditoria automática.
    """
    
    class LossStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        APPROVED = 'APPROVED', 'Aprovado'
        REJECTED = 'REJECTED', 'Rejeitado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    class LossType(models.TextChoices):
        OPERATIONAL = 'OPERATIONAL', 'Operacional'
        FINANCIAL = 'FINANCIAL', 'Financeira'
        TECHNICAL = 'TECHNICAL', 'Técnica'
        OTHER = 'OTHER', 'Outros'

    # Relacionamentos
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="loss_compensations",
        verbose_name="Cliente",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_compensations",
        verbose_name="Criado por",
    )

    # Campos principais (sensíveis - requerem aprovação)
    reference_number = models.CharField(
        max_length=50, unique=True, verbose_name="Número de referência"
    )

    loss_amount = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="Valor da perda"
    )

    compensation_amount = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="Valor da compensação"
    )

    loss_status = models.CharField(
        max_length=20,
        choices=LossStatus.choices,
        default=LossStatus.PENDING,
        verbose_name="Status",
    )

    loss_type = models.CharField(
        max_length=20, choices=LossType.choices, verbose_name="Tipo de perda"
    )

    # Campos descritivos (não sensíveis)
    description = models.TextField(verbose_name="Descrição")

    internal_notes = models.TextField(blank=True, verbose_name="Observações internas")

    # Datas importantes (sensíveis)
    loss_date = models.DateField(verbose_name="Data da perda")

    approval_deadline = models.DateField(
        null=True, blank=True, verbose_name="Prazo para aprovação"
    )

    # Campos de controle
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Excluído em")

    # Flag para auditoria automática
    __audit__ = True

    class Meta:
        verbose_name = "Perda de Compensação"
        verbose_name_plural = "Perdas de Compensação"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "loss_status"]),
            models.Index(fields=["reference_number"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["loss_date"]),
        ]

    def __str__(self):
        return f"PerdComp {self.reference_number} - {self.client.razao_social}"

    @property
    def compensation_percentage(self):
        """Calcular percentual de compensação."""
        if self.loss_amount > 0:
            return (self.compensation_amount / self.loss_amount) * 100
        return 0

    @property
    def is_overdue(self):
        """Verificar se está em atraso."""
        from django.utils import timezone

        if self.approval_deadline:
            return timezone.now().date() > self.approval_deadline
        return False
