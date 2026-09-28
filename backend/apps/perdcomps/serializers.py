from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import PerDcomp
from .deadlines import automatic_due_date
from django.utils import timezone
from django.db import transaction
from common.audit.services import AuditService
from common.shared.models import Annotation
from common.shared.serializers import (
    AnnotationSerializer,
    AnnotationBasicSerializer,
)


# Aliases para compatibilidade (usando modelos compartilhados)
class PerDcompAnnotationSerializer(AnnotationSerializer):
    """Serializer para anotações de PER/DCOMPs."""

    # Add entity fields as write-only to allow validation
    entity_type = serializers.CharField(write_only=True, required=False)
    entity_id = serializers.UUIDField(write_only=True, required=False)

    class Meta(AnnotationSerializer.Meta):
        fields = [
            "id",
            "entity_type",  # Add back for validation
            "entity_id",  # Add back for validation
            "entity_name",
            "user_name",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "entity_name",
            "user_name",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """Handle entity fields injected by the view."""
        # The view injects entity_type and entity_id before calling validate
        # We need to allow parent validation to run to convert these to content_type/object_id
        return super().validate(attrs)





class PerDcompSerializer(serializers.ModelSerializer):
    """Serializer completo para PerDcomp."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    recalculate_due_date = serializers.BooleanField(write_only=True, required=False, default=False)
    due_date_reason = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        requested_status = attrs.get("status")
        if requested_status == PerDcomp.Status.RASCUNHO and not (
            self.instance and self.instance.status == PerDcomp.Status.RASCUNHO
        ):
            raise serializers.ValidationError({"status": "Rascunho é um status histórico e não pode mais ser selecionado."})
        if not self.instance:
            attrs.setdefault("status", PerDcomp.Status.TRANSMITIDO)
        recalculate = attrs.pop("recalculate_due_date", False)
        reason = attrs.get("due_date_reason", "").strip()
        transmission = attrs.get("data_transmissao", self.instance.data_transmissao if self.instance else timezone.localdate())
        if not self.instance:
            attrs.setdefault("data_transmissao", transmission)
        expected = automatic_due_date(transmission)
        if recalculate or ("data_vencimento" not in attrs and (not self.instance or "data_transmissao" in attrs)):
            attrs["data_vencimento"] = expected
        due = attrs.get("data_vencimento")
        changed = due is not None and (not self.instance or due != self.instance.data_vencimento)
        if changed and due != expected and not reason:
            raise serializers.ValidationError({"due_date_reason": "Justifique o vencimento diferente do cálculo automático."})
        return attrs

    def record_due_reason(self, instance, reason, previous=None):
        if reason:
            AuditService.log_action("CUSTOM", instance, user=self.context["request"].user,
                old_data={"data_vencimento": previous.isoformat() if previous else None},
                new_data={"data_vencimento": instance.data_vencimento.isoformat()},
                metadata={"type": "due_date_override", "reason": reason})

    @transaction.atomic
    def update(self, instance, validated_data):
        reason = validated_data.pop("due_date_reason", "")
        previous = instance.data_vencimento
        client = validated_data.pop("client_cnpj", None)
        if client:
            validated_data.update(client_id=client.id, cnpj=client.cnpj)
        instance = super().update(instance, validated_data)
        self.record_due_reason(instance, reason, previous)
        return instance
    client_cnpj = serializers.CharField(
        write_only=True, help_text="CNPJ do cliente para vinculação"
    )
    client_name = serializers.CharField(source="client.razao_social", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )

    # Campos calculados
    esta_vencido = serializers.SerializerMethodField()
    pode_ser_editado = serializers.SerializerMethodField()
    pode_ser_cancelado = serializers.SerializerMethodField()

    @extend_schema_field(serializers.BooleanField)
    def get_esta_vencido(self, obj):
        """Verificar se está vencido."""
        return obj.esta_vencido

    @extend_schema_field(serializers.BooleanField)
    def get_pode_ser_editado(self, obj):
        """Verificar se pode ser editado."""
        return obj.pode_ser_editado

    @extend_schema_field(serializers.BooleanField)
    def get_pode_ser_cancelado(self, obj):
        """Verificar se pode ser cancelado."""
        return obj.pode_ser_cancelado

    class Meta:
        model = PerDcomp
        fields = [
            "id",
            "client_cnpj",
            "client_name",
            "created_by_name",
            "cnpj",
            "numero",
            "numero_perdcomp",
            "processo_protocolo",
            "data_transmissao",
            "data_vencimento",
            "recalculate_due_date",
            "due_date_reason",
            "data_competencia",
            "tributo_pedido",
            "competencia",
            "valor_pedido",
            "valor_compensado",
            "valor_recebido",
            "valor_saldo",
            "valor_selic",
            "status",
            "is_active",
            "created_at",
            "updated_at",
            "esta_vencido",
            "pode_ser_editado",
            "pode_ser_cancelado",
        ]
        read_only_fields = [
            "id",
            "client_name",
            "created_by_name",
            "cnpj",
            "created_at",
            "updated_at",
            "esta_vencido",
            "pode_ser_editado",
            "pode_ser_cancelado",
        ]
        extra_kwargs = {
            'numero': {'required': False, 'allow_null': True, 'allow_blank': True},
            'processo_protocolo': {'required': False, 'allow_null': True, 'allow_blank': True},
            'data_competencia': {'required': False, 'allow_null': True},
            'competencia': {'required': False, 'allow_null': True, 'allow_blank': True},
            'valor_compensado': {'required': False, 'allow_null': True, 'allow_blank': True},
            'valor_recebido': {'required': False, 'allow_null': True, 'allow_blank': True},
            'valor_saldo': {'required': False, 'allow_null': True, 'allow_blank': True},
            'valor_selic': {'required': False, 'allow_null': True, 'allow_blank': True},
            'status': {'required': False},
            'is_active': {'required': False},
        }

    def validate_client_cnpj(self, value):
        """Validar e converter client_cnpj para client_id."""
        try:
            from apps.clients.models import Client

            # Remove any non-numeric characters from CNPJ for comparison
            import re

            clean_cnpj = re.sub(r"[^\d]", "", str(value))

            # Try to find client by CNPJ (both original and cleaned versions)
            client = None
            try:
                client = Client.objects.get(cnpj=value, deleted_at__isnull=True)
            except Client.DoesNotExist:
                client = Client.objects.get(cnpj=clean_cnpj, deleted_at__isnull=True)

            return client
        except Client.DoesNotExist:
            raise serializers.ValidationError(
                f"Cliente com CNPJ '{value}' não encontrado."
            )

    @transaction.atomic
    def create(self, validated_data):
        """Criar PerDcomp com created_by_id e cnpj automaticamente."""
        # Get client from validated client_cnpj
        client = validated_data.pop("client_cnpj")
        reason = validated_data.pop("due_date_reason", "")

        # Set the client_id and cnpj from the found client
        validated_data["client_id"] = client.id
        validated_data["cnpj"] = client.cnpj
        validated_data["created_by_id"] = self.context["request"].user.id

        instance = super().create(validated_data)
        self.record_due_reason(instance, reason)
        return instance


class PerDcompBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para PerDcomp (listagem)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    client_name = serializers.CharField(source="client.razao_social", read_only=True)

    class Meta:
        model = PerDcomp
        fields = [
            "id",
            "numero_perdcomp",
            "cnpj",
            "client_name",
            "status",
            "valor_pedido",
            "data_vencimento",
            "created_at",
        ]
        read_only_fields = ["id", "client_name", "cnpj", "created_at"]


class PerDcompSensitiveSerializer(serializers.ModelSerializer):
    """Serializer para campos sensíveis (requer aprovação)."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    def validate_status(self, value):
        if value == PerDcomp.Status.RASCUNHO and not (
            self.instance and self.instance.status == PerDcomp.Status.RASCUNHO
        ):
            raise serializers.ValidationError("Rascunho é um status histórico e não pode mais ser selecionado.")
        return value

    class Meta:
        model = PerDcomp
        fields = [
            "id",
            "processo_protocolo",
            "data_transmissao",
            "data_vencimento",
            "valor_pedido",
            "valor_compensado",
            "valor_recebido",
            "valor_saldo",
            "valor_selic",
            "status",
        ]
        read_only_fields = ["id"]
