from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import PerDcomp
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

    def create(self, validated_data):
        """Criar PerDcomp com created_by_id e cnpj automaticamente."""
        # Get client from validated client_cnpj
        client = validated_data.pop("client_cnpj")

        # Set the client_id and cnpj from the found client
        validated_data["client_id"] = client.id
        validated_data["cnpj"] = client.cnpj
        validated_data["created_by_id"] = self.context["request"].user.id

        return super().create(validated_data)


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
