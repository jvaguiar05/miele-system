from rest_framework import serializers
from .models import Client, Address, ClientAnnotation, ClientAttachedFile


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


class ClientAnnotationSerializer(serializers.ModelSerializer):
    """Serializer para ClientAnnotation."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    client_id = serializers.UUIDField(write_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    client_name = serializers.CharField(source="client.razao_social", read_only=True)

    class Meta:
        model = ClientAnnotation
        fields = [
            "id",
            "client_id",
            "user_name",
            "client_name",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_name",
            "client_name",
            "created_at",
            "updated_at",
        ]

    def validate_client_id(self, value):
        """Validar e converter client_id de UUID para int."""
        try:
            client = Client.objects.get(public_id=value, deleted_at__isnull=True)
            return client.id  # Retorna o ID interno
        except Client.DoesNotExist:
            raise serializers.ValidationError("Cliente não encontrado.")

    def create(self, validated_data):
        """Criar anotação com user_id automaticamente."""
        validated_data["user_id"] = self.context["request"].user.id
        # client_id já foi convertido para int no validate_client_id
        validated_data["client_id"] = validated_data.pop("client_id")
        return super().create(validated_data)


class ClientAttachedFileSerializer(serializers.ModelSerializer):
    """Serializer para ClientAttachedFile."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    client_id = serializers.UUIDField(write_only=True)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    client_name = serializers.CharField(source="client.razao_social", read_only=True)

    class Meta:
        model = ClientAttachedFile
        fields = [
            "id",
            "client_id",
            "client_name",
            "file_name",
            "file_url",
            "file_size",
            "file_type",
            "description",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "client_name",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]

    def validate_client_id(self, value):
        """Validar e converter client_id de UUID para int."""
        try:
            client = Client.objects.get(public_id=value, deleted_at__isnull=True)
            return client.id  # Retorna o ID interno
        except Client.DoesNotExist:
            raise serializers.ValidationError("Cliente não encontrado.")

    def create(self, validated_data):
        """Criar arquivo anexado com uploaded_by_id automaticamente."""
        validated_data["uploaded_by_id"] = self.context["request"].user.id
        # client_id já foi convertido para int no validate_client_id
        validated_data["client_id"] = validated_data.pop("client_id")
        return super().create(validated_data)


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
