from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

User = get_user_model()


class PerDcomp(models.Model):
    """
    Modelo para Pedido Eletrônico de Restituição, Ressarcimento ou Reembolso
    e Declaração de Compensação (PER/DCOMP).
    """

    # Flag para auditoria automática
    __audit__ = True

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        TRANSMITIDO = "TRANSMITIDO", "Transmitido"
        EM_PROCESSAMENTO = "EM_PROCESSAMENTO", "Em Processamento"
        DEFERIDO = "DEFERIDO", "Deferido"
        INDEFERIDO = "INDEFERIDO", "Indeferido"
        PARCIALMENTE_DEFERIDO = "PARCIALMENTE_DEFERIDO", "Parcialmente Deferido"
        CANCELADO = "CANCELADO", "Cancelado"
        VENCIDO = "VENCIDO", "Vencido"

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Relacionamentos - FK usando ID interno (BigInt)
    client_id = models.BigIntegerField(help_text="ID do cliente relacionado")
    created_by_id = models.BigIntegerField(help_text="ID do usuário que criou")

    # Dados do cliente (desnormalizado para performance)
    cnpj = models.CharField(max_length=18, help_text="CNPJ do cliente")

    # Identificação do processo
    numero = models.TextField(help_text="Número do documento")
    numero_perdcomp = models.TextField(null=True, blank=True, help_text="Número específico do PER/DCOMP")
    processo_protocolo = models.TextField(
        null=True, blank=True, help_text="Protocolo do processo (texto)"
    )

    # Datas importantes
    data_transmissao = models.DateTimeField(
        null=True, blank=True, help_text="Data e hora da transmissão"
    )
    data_vencimento = models.DateTimeField(help_text="Data e hora do vencimento")
    data_competencia = models.DateTimeField(help_text="Data da competência")

    # Dados fiscais
    tributo_pedido = models.TextField(help_text="Tributo do pedido")
    competencia = models.TextField(help_text="Competência do tributo")

    # Valores monetários (como VARCHAR para manter precisão exata)
    valor_pedido = models.CharField(
        max_length=50, help_text="Valor solicitado no pedido"
    )
    valor_compensado = models.CharField(max_length=50, help_text="Valor compensado")
    valor_recebido = models.CharField(
        max_length=50, help_text="Valor efetivamente recebido"
    )
    valor_saldo = models.CharField(
        max_length=50, help_text="Valor do saldo remanescente"
    )
    valor_selic = models.CharField(max_length=50, help_text="Valor dos juros SELIC")

    # Status do processo
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.RASCUNHO,
        help_text="Status atual do PER/DCOMP",
    )

    # Controles de sistema
    is_active = models.BooleanField(default=True, help_text="Registro ativo no sistema")

    # Auditoria
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "perdcomps"
        verbose_name = "PER/DCOMP"
        verbose_name_plural = "PER/DCOMPs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["numero_perdcomp"]),
            models.Index(fields=["processo_protocolo"]),
            models.Index(fields=["cnpj"]),
            models.Index(fields=["client_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["data_vencimento"]),
            models.Index(fields=["data_competencia"]),
        ]

    def __str__(self):
        return f"PER/DCOMP {self.numero_perdcomp} - {self.cnpj}"

    @property
    def client(self):
        """Propriedade para acessar o cliente relacionado."""
        if self.client_id:
            try:
                from apps.clients.models import Client

                return Client.objects.get(id=self.client_id, deleted_at__isnull=True)
            except Client.DoesNotExist:
                return None
        return None

    @property
    def created_by(self):
        """Propriedade para acessar o usuário que criou."""
        if self.created_by_id:
            try:
                return User.objects.get(id=self.created_by_id, deleted_at__isnull=True)
            except User.DoesNotExist:
                return None
        return None

    @property
    def esta_vencido(self):
        """Verificar se está vencido."""
        if self.data_vencimento:
            return timezone.now() > self.data_vencimento
        return False

    @property
    def pode_ser_editado(self):
        """Verificar se pode ser editado (apenas rascunhos)."""
        return self.status == self.Status.RASCUNHO

    @property
    def pode_ser_cancelado(self):
        """Verificar se pode ser cancelado."""
        return self.status in [
            self.Status.RASCUNHO,
            self.Status.TRANSMITIDO,
            self.Status.EM_PROCESSAMENTO,
        ]

    def soft_delete(self):
        """Exclusão lógica."""
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()

    def restore(self):
        """Restaurar registro excluído."""
        self.deleted_at = None
        self.is_active = True
        self.save()
