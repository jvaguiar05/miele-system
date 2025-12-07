from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema_field
from .models import (
    Annotation,
    AttachedFile,
)


class AnnotationSerializer(serializers.ModelSerializer):
    """Serializer compartilhado para anotações."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    entity_type = serializers.CharField(
        write_only=True, help_text="Tipo da entidade (client, perdcomp)"
    )
    entity_id = serializers.UUIDField(
        write_only=True, help_text="UUID público da entidade"
    )
    entity_name = serializers.SerializerMethodField(read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    @extend_schema_field(serializers.CharField)
    def get_entity_name(self, obj):
        """Retorna o nome/identificador da entidade relacionada."""
        if obj.content_object:
            if hasattr(obj.content_object, "razao_social"):  # Client
                return obj.content_object.razao_social
            elif hasattr(obj.content_object, "numero_perdcomp"):  # PerDcomp
                return f"PER/DCOMP {obj.content_object.numero_perdcomp}"
        return "Entidade desconhecida"

    class Meta:
        model = Annotation
        fields = [
            "id",
            "entity_type",
            "entity_id",
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
        """Validar entidade e converter para ContentType + object_id."""
        entity_type = attrs.pop("entity_type")
        entity_id = attrs.pop("entity_id")

        # Mapear tipo para modelo
        entity_map = {
            "client": ("clients", "Client"),
            "perdcomp": ("perdcomps", "PerDcomp"),
        }

        if entity_type not in entity_map:
            raise serializers.ValidationError(
                f"Tipo de entidade inválido: {entity_type}. Opções: {list(entity_map.keys())}"
            )

        app_label, model_name = entity_map[entity_type]

        try:
            content_type = ContentType.objects.get(
                app_label=app_label, model=model_name.lower()
            )
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(
                f"ContentType não encontrado para {entity_type}"
            )

        # Buscar a entidade pelo UUID público
        model_class = content_type.model_class()
        try:
            entity = model_class.objects.get(
                public_id=entity_id, deleted_at__isnull=True
            )
        except model_class.DoesNotExist:
            raise serializers.ValidationError(f"{entity_type.title()} não encontrado.")

        attrs["content_type"] = content_type
        attrs["object_id"] = entity.id
        return attrs

    def create(self, validated_data):
        """Criar nova anotação (permite múltiplas por usuário por entidade)."""
        user_id = self.context["request"].user.id

        # Criar nova anotação diretamente sem verificar duplicatas
        validated_data["user_id"] = user_id
        return super().create(validated_data)


class AnnotationBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para anotações (listagem)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Annotation
        fields = ["id", "user_name", "content", "created_at"]
        read_only_fields = ["id", "user_name", "created_at"]


class AttachedFileListSerializer(serializers.ModelSerializer):
    """Para GET (Leitura)"""

    id = serializers.UUIDField(source="public_id", read_only=True)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    file_size_human = serializers.CharField(read_only=True)

    class Meta:
        model = AttachedFile
        fields = [
            "id",
            "file_name",
            "file_type",
            "file_size",
            "file_size_human",
            "uploaded_by_name",
            "created_at",
        ]


from rest_framework import serializers
from .models import AttachedFile, get_file_type_choices
from .utils import resolve_entity


class AttachedFileListSerializer(serializers.ModelSerializer):
    """Para GET (Leitura) - Retorna dados formatados."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True, default="Sistema"
    )
    file_size_human = serializers.CharField(read_only=True)

    class Meta:
        model = AttachedFile
        fields = [
            "id",
            "file_name",
            "file_type",
            "mime_type",
            "file_size",
            "file_size_human",
            "uploaded_by_name",
            "created_at",
            "description",
        ]


class AttachedFileCreateSerializer(serializers.Serializer):
    """
    Para POST (Upload).
    Realiza a validação de negócio (Tipo de Arquivo vs Entidade)
    antes de tocar no Google Drive.
    """

    object_id = serializers.UUIDField(help_text="UUID da Entidade (Client/Perdcomp)")
    file_type = serializers.CharField(
        help_text="Código do tipo de arquivo (ex: contrato, recibo)"
    )
    description = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(write_only=True)

    def validate_file_type(self, value):
        return value.lower()

    def validate(self, attrs):
        """
        Validação Cruzada: Verifica se o file_type é válido para a entidade encontrada.
        """
        object_uuid = attrs.get("object_id")
        input_type = attrs.get("file_type")

        # 1. Resolver Entidade (Client ou PerDcomp)
        entity, entity_type = resolve_entity(object_uuid)

        if not entity:
            raise serializers.ValidationError(
                {"object_id": "Entidade não encontrada no sistema."}
            )

        # 2. Buscar regras de negócio (Tipos permitidos para esta entidade)
        # Retorna lista de tuplas, ex: [('contrato', 'Contrato'), ...]
        valid_choices = get_file_type_choices(entity_type)
        valid_keys = [choice[0] for choice in valid_choices]

        # 3. Validar se o tipo enviado é permitido
        if input_type not in valid_keys:
            raise serializers.ValidationError(
                {
                    "file_type": f"Tipo '{input_type}' inválido para {entity_type}. Opções válidas: {valid_keys}"
                }
            )

        # OTIMIZAÇÃO: Injetamos o tipo resolvido para a View não precisar buscar de novo
        attrs["resolved_entity_type"] = entity_type

        return attrs


class AttachedFileUpdateSerializer(serializers.ModelSerializer):
    """Para PATCH (atualização apenas de metadados, não do arquivo em si)."""

    description = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = AttachedFile
        fields = ["description"]  # Apenas descrição é editável
        # Nota: read_only_fields não é necessário se listarmos apenas description em fields,
        # mas mantemos aqui para documentação explícita do que NÃO muda.
        read_only_fields = [
            "id",
            "file_name",
            "file_type",
            "file_size",
            "uploaded_by",
            "created_at",
            "drive_file_id",
        ]
