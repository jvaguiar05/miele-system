from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import json
from .models import AuditLog


class EntityTypeFilter(SimpleListFilter):
    """Filtro inteligente para tipos de entidade auditados"""

    title = "Tipo de Entidade"
    parameter_name = "entity_type"

    def lookups(self, request, model_admin):
        return [
            ("users", "👤 Usuários"),
            ("clients", "🏢 Clientes"),
            ("perdcomps", "📋 PER/DCOMPs"),
            ("addresses", "📍 Endereços"),
            ("files", "📎 Arquivos Anexos"),
            ("annotations", "💬 Anotações"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "users":
            return queryset.filter(content_type__model__icontains="user")
        elif self.value() == "clients":
            return queryset.filter(content_type__model__icontains="client")
        elif self.value() == "perdcomps":
            return queryset.filter(content_type__model__icontains="perdcomp")
        elif self.value() == "addresses":
            return queryset.filter(content_type__model__icontains="address")
        elif self.value() == "files":
            return queryset.filter(content_type__model__icontains="attachedfile")
        elif self.value() == "annotations":
            return queryset.filter(content_type__model__icontains="annotation")
        return queryset


class ActionFilter(SimpleListFilter):
    """Filtro para ações de auditoria (sem approval_requests)"""

    title = "Ação"
    parameter_name = "action_type"

    def lookups(self, request, model_admin):
        return [
            ("create", "✅ Criação"),
            ("update", "✏️ Atualização"),
            ("delete", "🗑️ Exclusão"),
            ("restore", "🔄 Restauração"),
            ("login", "🔐 Login"),
            ("logout", "🚪 Logout"),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(action__iexact=self.value())
        return queryset


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin configuration for AuditLog model - STRICTLY READ-ONLY for security.
    """

    # Security: Make completely read-only
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Display configuration
    list_display = [
        "timestamp",
        "get_actor_display",
        "get_action_display",
        "get_target_entity",
        "ip_address",
        "correlation_id",
    ]

    list_filter = [
        EntityTypeFilter,
        ActionFilter,
        "user",
        ("timestamp", admin.DateFieldListFilter),
    ]

    search_fields = [
        "object_id",
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "correlation_id",
    ]

    readonly_fields = [
        "id",
        "correlation_id",
        "user",
        "action",
        "content_type",
        "object_id",
        "content_object",
        "get_old_data_display",
        "get_new_data_display",
        "get_metadata_display",
        "ip_address",
        "user_agent",
        "timestamp",
    ]

    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"

    fieldsets = (
        (
            "Informações da Ação",
            {
                "fields": ("timestamp", "correlation_id", "action"),
            },
        ),
        (
            "Ator",
            {
                "fields": ("user", "ip_address", "user_agent"),
            },
        ),
        (
            "Recurso Afetado",
            {
                "fields": ("content_type", "object_id", "content_object"),
            },
        ),
        (
            "Dados da Mudança",
            {
                "fields": ("get_old_data_display", "get_new_data_display"),
            },
        ),
        (
            "Metadados",
            {
                "fields": ("get_metadata_display",),
                "classes": ["collapse"],
            },
        ),
    )

    def get_actor_display(self, obj):
        """Display actor with formatting."""
        if obj.user:
            return format_html(
                "<strong>{}</strong><br><small>{}</small>",
                obj.user.get_full_name() or obj.user.username,
                obj.user.email,
            )
        return format_html("<em>Sistema</em>")

    get_actor_display.short_description = "Ator"
    get_actor_display.admin_order_field = "user"

    def get_action_display(self, obj):
        """Display action with icons and colors."""
        action_map = {
            "create": ("✅", "Criação", "color: green;"),
            "update": ("✏️", "Atualização", "color: blue;"),
            "delete": ("🗑️", "Exclusão", "color: red;"),
            "restore": ("🔄", "Restauração", "color: orange;"),
            "login": ("🔐", "Login", "color: purple;"),
            "logout": ("🚪", "Logout", "color: gray;"),
        }

        action_lower = obj.action.lower()
        icon, display_name, color = action_map.get(
            action_lower, ("❓", obj.action, "color: black;")
        )

        return format_html('<span style="{}">{} {}</span>', color, icon, display_name)

    get_action_display.short_description = "Ação"
    get_action_display.admin_order_field = "action"

    def get_target_entity(self, obj):
        """Display target entity with clearer formatting and icons."""
        model_name = obj.content_type.model.lower()

        # Map models to user-friendly names and icons
        entity_map = {
            "user": ("👤", "Usuário"),
            "client": ("🏢", "Cliente"),
            "perdcomp": ("📋", "PER/DCOMP"),
            "address": ("📍", "Endereço"),
            "attachedfile": ("📎", "Arquivo"),
            "annotation": ("💬", "Anotação"),
        }

        icon, display_name = entity_map.get(model_name, ("❓", model_name.title()))

        return format_html(
            "{} <strong>{}</strong><br><small>ID: {}</small>",
            icon,
            display_name,
            obj.object_id,
        )

    get_target_entity.short_description = "Entidade Alvo"
    get_target_entity.admin_order_field = "content_type"

    def get_old_data_display(self, obj):
        """Display old data as pretty-printed JSON."""
        if obj.old_data:
            try:
                formatted_json = json.dumps(obj.old_data, indent=2, ensure_ascii=False)
                return format_html(
                    '<pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{}</pre>',
                    formatted_json,
                )
            except (TypeError, ValueError):
                return format_html("<em>Dados inválidos</em>")
        return format_html("<em>Nenhum dado anterior</em>")

    get_old_data_display.short_description = "Dados Anteriores"

    def get_new_data_display(self, obj):
        """Display new data as pretty-printed JSON."""
        if obj.new_data:
            try:
                formatted_json = json.dumps(obj.new_data, indent=2, ensure_ascii=False)
                return format_html(
                    '<pre style="background: #e8f5e8; padding: 10px; border-radius: 4px;">{}</pre>',
                    formatted_json,
                )
            except (TypeError, ValueError):
                return format_html("<em>Dados inválidos</em>")
        return format_html("<em>Nenhum novo dado</em>")

    get_new_data_display.short_description = "Novos Dados"

    def get_metadata_display(self, obj):
        """Display metadata as pretty-printed JSON."""
        if obj.metadata:
            try:
                formatted_json = json.dumps(obj.metadata, indent=2, ensure_ascii=False)
                return format_html(
                    '<pre style="background: #fff3cd; padding: 10px; border-radius: 4px;">{}</pre>',
                    formatted_json,
                )
            except (TypeError, ValueError):
                return format_html("<em>Metadados inválidos</em>")
        return format_html("<em>Nenhum metadado</em>")

    get_metadata_display.short_description = "Metadados"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("user", "content_type")

    # Remove all action buttons
    actions = None

    def changelist_view(self, request, extra_context=None):
        """Add security warning to changelist."""
        extra_context = extra_context or {}

        # Add statistics
        total_logs = AuditLog.objects.count()
        recent_logs = AuditLog.objects.filter(
            timestamp__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()

        extra_context.update(
            {
                "title": "Logs de Auditoria de Segurança",
                "subtitle": f"{total_logs} registros totais • {recent_logs} nos últimos 7 dias • Somente Leitura",
            }
        )
        return super().changelist_view(request, extra_context)
