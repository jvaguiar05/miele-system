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
    """Serializer para anotações de clientes."""

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


class ClientAttachedFileSerializer(AttachedFileSerializer):
    """Serializer para arquivos de clientes."""

    # Substituir entity_type e entity_id por client_id mais simples
    entity_type = None  # Não expor este campo
    entity_id = None  # Não expor este campo
    client_id = serializers.UUIDField(
        write_only=True, help_text="UUID do cliente para associar o arquivo"
    )

    class Meta(AttachedFileSerializer.Meta):
        fields = [
            "id",
            "client_id",  # Substituir entity_type e entity_id
            "entity_name",
            "uploaded_by_name",
            "file_name",
            "description",
            "file_type",
            "file_size",
            "mime_type",
            "file_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "entity_name",
            "uploaded_by_name",
            "file_size",
            "mime_type",
            "file_url",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        # Converter client_id para entity_type e entity_id
        if "client_id" in attrs:
            attrs["entity_type"] = "client"
            attrs["entity_id"] = attrs.pop("client_id")
        return super().validate(attrs)


class ClientSerializer(serializers.ModelSerializer):
    """Serializer completo para Client com criação automática de endereço."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    # Campos do endereço (write-only no POST, read-only via nested address)
    logradouro = serializers.CharField(write_only=True, max_length=255, required=False)
    numero = serializers.CharField(write_only=True, max_length=20, required=False)
    complemento = serializers.CharField(
        write_only=True, max_length=255, required=False, allow_blank=True
    )
    bairro = serializers.CharField(write_only=True, max_length=100, required=False)
    municipio = serializers.CharField(write_only=True, max_length=100, required=False)
    uf = serializers.CharField(write_only=True, max_length=2, required=False)
    cep = serializers.CharField(write_only=True, max_length=10, required=False)

    # Endereço completo para leitura
    address = AddressSerializer(read_only=True)

    client_status = serializers.ChoiceField(
        choices=Client.ClientStatus.choices,
        required=False,
        default=Client.ClientStatus.PENDING,
        allow_null=True,
    )
    is_active = serializers.BooleanField(required=False, default=True, allow_null=True)

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
            # Campos do endereço
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
            # Endereço completo (read-only)
            "address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "address", "created_at", "updated_at"]

    def validate(self, attrs):
        """Validar que os campos do endereço estão completos se fornecidos."""
        address_fields = ["logradouro", "numero", "bairro", "municipio", "uf", "cep"]
        address_data = {
            field: attrs.get(field) for field in address_fields if field in attrs
        }

        if address_data:
            # Se algum campo de endereço foi fornecido, verificar os obrigatórios
            required_fields = [
                "logradouro",
                "numero",
                "bairro",
                "municipio",
                "uf",
                "cep",
            ]
            missing_fields = [
                field for field in required_fields if not attrs.get(field)
            ]

            if missing_fields:
                raise serializers.ValidationError(
                    f"Campos obrigatórios do endereço: {', '.join(missing_fields)}"
                )

        return super().validate(attrs)

    def create(self, validated_data):
        """Criar cliente com endereço automaticamente."""
        # Extrair dados do endereço
        address_fields = [
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
        ]
        address_data = {}

        for field in address_fields:
            if field in validated_data:
                address_data[field] = validated_data.pop(field)

        # Criar endereço se dados foram fornecidos
        address_id = None
        if address_data:
            address = Address.objects.create(**address_data)
            address_id = address.id

        # Criar cliente com referência ao endereço
        validated_data["address_id"] = address_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Atualizar cliente (endereço não é alterado via este serializer)."""
        # Remover campos de endereço se fornecidos (não suportado no update)
        address_fields = [
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
        ]
        for field in address_fields:
            validated_data.pop(field, None)

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
