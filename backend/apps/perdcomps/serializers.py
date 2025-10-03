from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import PerDcomp
from common.shared.models import Annotation, AttachedFile
from common.shared.serializers import (
    AnnotationSerializer,
    AttachedFileSerializer,
    AnnotationBasicSerializer,
    AttachedFileBasicSerializer,
)


# Aliases para compatibilidade (usando modelos compartilhados)
class PerDcompAnnotationSerializer(AnnotationSerializer):
    """Serializer para anotações de PER/DCOMPs (alias para AnnotationSerializer)."""

    def validate(self, attrs):
        # Forçar entity_type para perdcomp se não informado
        if "entity_type" not in attrs and "entity_id" in attrs:
            attrs["entity_type"] = "perdcomp"
        return super().validate(attrs)


class PerDcompAttachedFileSerializer(AttachedFileSerializer):
    """Serializer para arquivos de PER/DCOMPs (alias para AttachedFileSerializer)."""

    def validate(self, attrs):
        # Forçar entity_type para perdcomp se não informado
        if "entity_type" not in attrs and "entity_id" in attrs:
            attrs["entity_type"] = "perdcomp"
        return super().validate(attrs)


class PerDcompSerializer(serializers.ModelSerializer):
    """Serializer completo para PerDcomp."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    client_id = serializers.UUIDField(write_only=True)
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
            "client_id",
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

    def validate_client_id(self, value):
        """Validar e converter client_id de UUID para int."""
        try:
            from apps.clients.models import Client

            client = Client.objects.get(public_id=value, deleted_at__isnull=True)
            return client.id  # Retorna o ID interno
        except Client.DoesNotExist:
            raise serializers.ValidationError("Cliente não encontrado.")

    def create(self, validated_data):
        """Criar PerDcomp com created_by_id e cnpj automaticamente."""
        # Buscar cliente para pegar o CNPJ
        client_id = validated_data.get("client_id")
        if client_id:
            from apps.clients.models import Client

            try:
                client = Client.objects.get(id=client_id)
                validated_data["cnpj"] = client.cnpj
            except Client.DoesNotExist:
                pass  # Será capturado pela validação

        validated_data["created_by_id"] = self.context["request"].user.id
        validated_data["client_id"] = validated_data.pop("client_id")
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


class PerDcompBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para PerDcomp (listagem)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    client_name = serializers.CharField(source="client.razao_social", read_only=True)

    class Meta:
        model = PerDcomp
        fields = [
            "id",
            "numero_perdcomp",
            "tributo_pedido",
            "status",
            "client_name",
            "valor_pedido",
            "data_vencimento",
            "created_at",
        ]
        read_only_fields = ["id", "client_name", "created_at"]


class PerDcompSensitiveSerializer(serializers.ModelSerializer):
    """Serializer para campos sensíveis (requer aprovação)."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = PerDcomp
        fields = [
            "id",
            "processo_protocolo",
            "valor_pedido",
            "valor_compensado",
            "status",
            "data_vencimento",
            "data_transmissao",
        ]
        read_only_fields = ["id", "data_aprovacao"]
