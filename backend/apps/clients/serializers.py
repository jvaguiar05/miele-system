from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Client, Address
from common.shared.models import Annotation, AttachedFile
from common.shared.serializers import (
    AnnotationSerializer,
    AttachedFileSerializer,
    AnnotationBasicSerializer,
    AttachedFileBasicSerializer,
)


class AddressSerializer(serializers.ModelSerializer):
    """Serializer para Address."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Address
        fields = [
            "id",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# Aliases para compatibilidade (usando modelos compartilhados)
class ClientAnnotationSerializer(AnnotationSerializer):
    """Serializer para anotações de clientes (alias para AnnotationSerializer)."""

    def validate(self, attrs):
        # Forçar entity_type para client se não informado
        if "entity_type" not in attrs and "entity_id" in attrs:
            attrs["entity_type"] = "client"
        return super().validate(attrs)


class ClientAttachedFileSerializer(AttachedFileSerializer):
    """Serializer para arquivos de clientes (alias para AttachedFileSerializer)."""

    def validate(self, attrs):
        # Forçar entity_type para client se não informado
        if "entity_type" not in attrs and "entity_id" in attrs:
            attrs["entity_type"] = "client"
        return super().validate(attrs)


class ClientSerializer(serializers.ModelSerializer):
    """Serializer completo para Client."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    address_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    address = AddressSerializer(read_only=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "razao_social",
            "nome_fantasia",
            "cnpj",
            "inscricao_estadual",
            "inscricao_municipal",
            "tipo_empresa",
            "recuperacao_judicial",
            "telefone_comercial",
            "email_comercial",
            "website",
            "telefone_contato",
            "email_contato",
            "quadro_societario",
            "cargos",
            "responsavel_financeiro",
            "contador_responsavel",
            "cnaes",
            "regime_tributacao",
            "contrato_social",
            "ultima_alteracao_contratual",
            "rg_cpf_socios",
            "certificado_digital",
            "autorizado_para_envio",
            "atividades",
            "client_status",
            "is_active",
            "address_id",
            "address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "address", "created_at", "updated_at"]

    def validate_address_id(self, value):
        """Validar e converter address_id de UUID para int."""
        if value is None:
            return None
        try:
            address = Address.objects.get(public_id=value, deleted_at__isnull=True)
            return address.id  # Retorna o ID interno
        except Address.DoesNotExist:
            raise serializers.ValidationError("Endereço não encontrado.")

    def create(self, validated_data):
        """Criar cliente convertendo address_id se fornecido."""
        if "address_id" in validated_data:
            validated_data["address_id"] = validated_data.pop("address_id")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Atualizar cliente convertendo address_id se fornecido."""
        if "address_id" in validated_data:
            validated_data["address_id"] = validated_data.pop("address_id")
        return super().update(instance, validated_data)


class ClientBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para Client (campos essenciais)."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "razao_social",
            "nome_fantasia",
            "cnpj",
            "client_status",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ClientSensitiveSerializer(serializers.ModelSerializer):
    """Serializer para campos sensíveis (requer aprovação)."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Client
        fields = ["id", "cnpj", "razao_social", "client_status", "is_active"]
        read_only_fields = ["id"]
