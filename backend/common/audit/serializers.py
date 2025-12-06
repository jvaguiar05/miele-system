from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema_field
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer para logs de auditoria."""

    user_id = serializers.CharField(source="user.public_id", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()
    resource_type = serializers.CharField(read_only=True)
    resource_id = serializers.SerializerMethodField()
    resource_display_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "correlation_id",
            "user_id",
            "user_email",
            "user_name",
            "action",
            "resource_type",
            "resource_id",
            "resource_display_name",
            "old_data",
            "new_data",
            "metadata",
            "ip_address",
            "user_agent",
            "timestamp",
        ]

    @extend_schema_field(serializers.CharField)
    def get_user_name(self, obj):
        """Retorna o nome completo do usuário."""
        if obj.user:
            return (
                f"{obj.user.first_name} {obj.user.last_name}".strip()
                or obj.user.username
            )
        return None

    @extend_schema_field(serializers.CharField)
    def get_resource_id(self, obj):
        """Retorna o public_id do recurso afetado quando disponível."""
        if not obj.content_object:
            return obj.object_id  # Fallback para ID interno se objeto não existir

        # Verificar se o objeto tem public_id
        if hasattr(obj.content_object, "public_id"):
            return str(obj.content_object.public_id)

        return obj.object_id  # Fallback para ID interno

    @extend_schema_field(serializers.CharField)
    def get_resource_display_name(self, obj):
        """Retorna um nome/descrição amigável do recurso afetado."""
        if not obj.content_object:
            return None

        resource_type = obj.resource_type
        content_obj = obj.content_object

        try:
            if resource_type == "clients.client":
                return getattr(content_obj, "razao_social", None) or getattr(
                    content_obj, "nome_fantasia", None
                )
            elif resource_type == "perdcomps.perdcomp":
                return f"PER/DCOMP {getattr(content_obj, 'numero', 'N/A')}"
            elif resource_type == "identity.user":
                return f"{getattr(content_obj, 'first_name', '')} {getattr(content_obj, 'last_name', '')}".strip() or getattr(
                    content_obj, "username", ""
                )
            else:
                # Tentar usar __str__ como fallback
                return str(content_obj) if content_obj else None
        except Exception:
            # Em caso de erro, retornar None
            return None


class AuditLogFilterSerializer(serializers.Serializer):
    """Serializer para validação de filtros nos endpoints de logs."""

    # Paginação
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    # Filtros de tempo
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)

    # Filtros de ação
    action = serializers.ChoiceField(
        choices=AuditLog.AuditAction.choices, required=False
    )

    # Filtros de objeto/recurso
    resource_type = serializers.CharField(max_length=100, required=False)
    resource_id = serializers.CharField(max_length=255, required=False)

    # Filtros por public_id (UUID) - interface usa estes
    user_id = serializers.UUIDField(
        required=False, help_text="Public ID (UUID) do usuário"
    )
    client_id = serializers.UUIDField(
        required=False, help_text="Public ID (UUID) do cliente"
    )
    perdcomp_id = serializers.UUIDField(
        required=False, help_text="Public ID (UUID) do PER/DCOMP"
    )

    # Filtro de correlação
    correlation_id = serializers.UUIDField(required=False)

    def validate(self, data):
        """Validações customizadas."""
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError(
                {"end_date": "A data final deve ser posterior à data inicial."}
            )

        return data


class RecentLogsFilterSerializer(serializers.Serializer):
    """Serializer para o endpoint de logs recentes."""

    since = serializers.DateTimeField(help_text="Data a partir da qual buscar os logs")
    limit = serializers.IntegerField(
        min_value=1,
        max_value=1000,
        default=100,
        required=False,
        help_text="Número máximo de logs para retornar",
    )
