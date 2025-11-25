from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema_field
from .models import (
    Annotation,
    AttachedFile,
    CLIENT_FILE_TYPES,
    PERDCOMP_FILE_TYPES,
    get_file_type_choices,
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
        """Criar nova anotação (apenas uma por usuário por entidade)."""
        user_id = self.context["request"].user.id
        content_type = validated_data["content_type"]
        object_id = validated_data["object_id"]

        # Verificar se já existe anotação para este usuário e entidade
        existing_annotation = Annotation.objects.filter(
            user_id=user_id,
            content_type=content_type,
            object_id=object_id,
            deleted_at__isnull=True,
        ).first()

        if existing_annotation:
            raise serializers.ValidationError(
                {
                    "detail": "Você já possui uma anotação para esta entidade. Use PUT para atualizar ou DELETE para remover a anotação existente.",
                    "existing_annotation_id": existing_annotation.public_id,
                }
            )

        # Criar nova anotação
        validated_data["user_id"] = user_id
        return super().create(validated_data)


class AttachedFileSerializer(serializers.ModelSerializer):
    """Serializer compartilhado para arquivos anexados."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    entity_type = serializers.CharField(
        write_only=True, help_text="Tipo da entidade (client, perdcomp)"
    )
    entity_id = serializers.UUIDField(
        write_only=True, help_text="UUID público da entidade"
    )
    entity_name = serializers.SerializerMethodField(read_only=True)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    file_size_human = serializers.CharField(read_only=True)
    available_file_types = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(serializers.CharField)
    def get_entity_name(self, obj):
        """Retorna o nome/identificador da entidade relacionada."""
        if obj.content_object:
            if hasattr(obj.content_object, "razao_social"):  # Client
                return obj.content_object.razao_social
            elif hasattr(obj.content_object, "numero_perdcomp"):  # PerDcomp
                return f"PER/DCOMP {obj.content_object.numero_perdcomp}"
        return "Entidade desconhecida"

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_available_file_types(self, obj):
        """Retorna os tipos de arquivo disponíveis baseados na entidade."""
        if obj.content_type:
            model_name = obj.content_type.model
            choices = get_file_type_choices(model_name)
            return [{"value": choice[0], "label": choice[1]} for choice in choices]
        return []

    class Meta:
        model = AttachedFile
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "entity_name",
            "uploaded_by_name",
            "file_type",
            "file_name",
            "file_url",
            "file_size",
            "file_size_human",
            "mime_type",
            "description",
            "available_file_types",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "entity_name",
            "uploaded_by_name",
            "file_size_human",
            "available_file_types",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """Validar entidade e tipo de arquivo."""
        entity_type = attrs.pop("entity_type")
        entity_id = attrs.pop("entity_id")
        file_type = attrs.get("file_type")

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

        # Validar tipo de arquivo
        valid_types = get_file_type_choices(entity_type)
        valid_type_values = [choice[0] for choice in valid_types]

        if file_type not in valid_type_values:
            raise serializers.ValidationError(
                f"Tipo de arquivo inválido para {entity_type}: {file_type}. "
                f"Opções válidas: {valid_type_values}"
            )

        attrs["content_type"] = content_type
        attrs["object_id"] = entity.id
        return attrs

    def create(self, validated_data):
        """Criar arquivo com uploaded_by_id automaticamente."""
        validated_data["uploaded_by_id"] = self.context["request"].user.id
        return super().create(validated_data)


class AnnotationBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para anotações (listagem)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Annotation
        fields = ["id", "user_name", "content", "created_at"]
        read_only_fields = ["id", "user_name", "created_at"]


class AttachedFileBasicSerializer(serializers.ModelSerializer):
    """Serializer básico para arquivos (listagem)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    file_size_human = serializers.CharField(read_only=True)

    class Meta:
        model = AttachedFile
        fields = ["id", "file_type", "file_name", "file_size_human", "created_at"]
        read_only_fields = ["id", "file_size_human", "created_at"]
