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


# ================================
# AttachedFile Serializers
# ================================


class AttachedFileListSerializer(serializers.ModelSerializer):
    """Serializer para listagem de arquivos (GET list)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    entity_type = serializers.SerializerMethodField()
    entity_name = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    file_size_human = serializers.SerializerMethodField()

    class Meta:
        model = AttachedFile
        fields = [
            "id",
            "file_name",
            "file_type",
            "drive_file_id",
            "file_size",
            "file_size_human",
            "entity_type",
            "entity_name",
            "uploaded_by_name",
            "sync_status",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_entity_type(self, obj):
        """Retorna tipo da entidade (client/perdcomp)."""
        if obj.content_type:
            app_label = obj.content_type.app_label
            model = obj.content_type.model
            return f"{app_label}.{model}".replace("clients.client", "client").replace(
                "perdcomps.perdcomp", "perdcomp"
            )
        return None

    @extend_schema_field(serializers.CharField)
    def get_entity_name(self, obj):
        """Retorna nome/descrição da entidade."""
        if not obj.content_object:
            return None

        try:
            content_obj = obj.content_object
            if hasattr(content_obj, "razao_social"):
                # Cliente
                return getattr(content_obj, "razao_social") or getattr(
                    content_obj, "nome_fantasia", "N/A"
                )
            elif hasattr(content_obj, "numero"):
                # PER/DCOMP
                return f"PER/DCOMP {getattr(content_obj, 'numero', 'N/A')}"
            else:
                return str(content_obj)
        except Exception:
            return None

    @extend_schema_field(serializers.CharField)
    def get_file_size_human(self, obj):
        """Retorna tamanho do arquivo em formato legível."""
        if not obj.file_size:
            return "N/A"

        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class AttachedFileDetailSerializer(AttachedFileListSerializer):
    """Serializer para detalhes de arquivo (GET detail)."""

    description = serializers.CharField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta(AttachedFileListSerializer.Meta):
        fields = AttachedFileListSerializer.Meta.fields + [
            "description",
            "updated_at",
        ]


class AttachedFileCreateSerializer(serializers.ModelSerializer):
    """Serializer para criação de arquivos (POST)."""

    object_id = serializers.UUIDField(
        write_only=True,
        help_text="Public ID da entidade (Cliente ou PER/DCOMP) para anexar o arquivo",
    )

    class Meta:
        model = AttachedFile
        fields = [
            "object_id",
            "file_type",
            "file_name",
            "drive_file_id",
            "file_size",
            "description",
        ]
        extra_kwargs = {
            "drive_file_id": {"help_text": "ID do arquivo no Google Drive"},
            "file_type": {
                "help_text": "Tipo do arquivo (ex: contrato, procuracao, documento, etc.)"
            },
            "file_name": {"help_text": "Nome do arquivo com extensão"},
            "file_size": {
                "help_text": "Tamanho do arquivo em bytes",
                "required": False,
            },
            "description": {
                "help_text": "Descrição opcional do arquivo",
                "required": False,
            },
        }

    def validate_drive_file_id(self, value):
        """Valida se arquivo existe no Google Drive."""
        from .services import AttachedFileService

        if not value:
            raise serializers.ValidationError(
                "ID do arquivo no Google Drive é obrigatório"
            )

        # Validar se já existe no sistema
        if AttachedFile.objects.filter(drive_file_id=value).exists():
            raise serializers.ValidationError(
                "Este arquivo já está registrado no sistema"
            )

        # Validar se existe no Google Drive
        if not AttachedFileService.validate_drive_file_exists(value):
            raise serializers.ValidationError("Arquivo não encontrado no Google Drive")

        return value

    def validate_file_type(self, value):
        """Validar tipo de arquivo."""
        if not value:
            raise serializers.ValidationError("Tipo de arquivo é obrigatório")
        return value.lower()

    def create(self, validated_data):
        """Criar arquivo usando service layer."""
        from .services import AttachedFileService

        user = self.context["request"].user
        return AttachedFileService.create_attached_file(validated_data, user)


class AttachedFileUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualização de arquivos (PUT/PATCH)."""

    class Meta:
        model = AttachedFile
        fields = [
            "file_type",
            "file_name",
            "drive_file_id",
            "file_size",
            "description",
        ]
        extra_kwargs = AttachedFileCreateSerializer.Meta.extra_kwargs

    def validate_drive_file_id(self, value):
        """Valida se arquivo existe no Google Drive."""
        from .services import AttachedFileService

        if not value:
            raise serializers.ValidationError(
                "ID do arquivo no Google Drive é obrigatório"
            )

        # Se mudou o drive_file_id, validar duplicação
        if value != self.instance.drive_file_id:
            if (
                AttachedFile.objects.filter(drive_file_id=value)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    "Este arquivo já está registrado no sistema"
                )

            # Validar se existe no Google Drive
            if not AttachedFileService.validate_drive_file_exists(value):
                raise serializers.ValidationError(
                    "Arquivo não encontrado no Google Drive"
                )

        return value

    def update(self, instance, validated_data):
        """Atualizar arquivo usando service layer."""
        from .services import AttachedFileService

        return AttachedFileService.update_attached_file(instance, validated_data)
