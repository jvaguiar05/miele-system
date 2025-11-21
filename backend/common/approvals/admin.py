from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
import json
from .models import ApprovalRequest


class StatusFilter(SimpleListFilter):
    """Filtro de status com 'Pending' como padrão - o coração da funcionalidade."""

    title = "Status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [
            ("pending", "🟡 Pendentes (Ação Necessária)"),
            ("approved", "✅ Aprovadas"),
            ("rejected", "❌ Rejeitadas"),
            ("all", "📋 Todas"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "approved":
            return queryset.filter(status="approved")
        elif self.value() == "rejected":
            return queryset.filter(status="rejected")
        elif self.value() == "all":
            return queryset
        else:  # Default: show only pending requests
            return queryset.filter(status="pending")

    def choices(self, changelist):
        """Override to make 'pending' the default selection."""
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == lookup
                or (self.value() is None and lookup == "pending"),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


class RequestTypeFilter(SimpleListFilter):
    """Filtro inteligente para tipos de solicitação"""

    title = "Tipo de Solicitação"
    parameter_name = "request_type"

    def lookups(self, request, model_admin):
        return [
            ("account_creation", "👤 Criação de Contas"),
            ("sensitive_data", "🔒 Alteração de Dados Sensíveis"),
            ("client_management", "🏢 Gestão de Clientes"),
            ("perdcomp_management", "📋 Gestão de PER/DCOMPs"),
            ("other", "❓ Outros"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "account_creation":
            # Pedidos relacionados a usuários (criação, ativação, etc)
            return queryset.filter(resource_type__icontains="user")
        elif self.value() == "sensitive_data":
            # Pedidos de alteração de CNPJ, dados fiscais, etc
            return queryset.filter(
                action="update",
                payload_diff__has_any_keys=[
                    "cnpj",
                    "inscricao_estadual",
                    "regime_tributacao",
                ],
            )
        elif self.value() == "client_management":
            # Pedidos relacionados a clientes
            return queryset.filter(resource_type__icontains="client")
        elif self.value() == "perdcomp_management":
            # Pedidos relacionados a PER/DCOMPs
            return queryset.filter(resource_type__icontains="perdcomp")
        elif self.value() == "other":
            # Outros tipos de pedidos
            return (
                queryset.exclude(resource_type__icontains="user")
                .exclude(resource_type__icontains="client")
                .exclude(resource_type__icontains="perdcomp")
            )
        return queryset


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    """
    Admin configuration for ApprovalRequest model.
    The functional heart of the backoffice with "Pending First" logic.
    """

    list_display = [
        "subject",
        "get_requester_display",
        "action",
        "get_resource_display",
        "get_status_display_badge",
        "get_priority_indicator",
        "created_at",
    ]

    list_filter = [
        StatusFilter,  # Pending first filter - CRUCIAL
        RequestTypeFilter,
        "action",
        "resource_type",
        "requested_by",
        "created_at",
        "updated_at",
    ]

    search_fields = [
        "subject",
        "reason",
        "resource_id",
        "requested_by__username",
        "requested_by__email",
    ]

    readonly_fields = [
        "public_id",
        "created_at",
        "updated_at",
        "get_payload_diff_display",
        "get_requester_full_info",
    ]

    # Force ordering by creation time (oldest first) - queue management
    ordering = ["created_at"]

    fieldsets = (
        (
            "Informações da Solicitação",
            {
                "fields": ("public_id", "subject", "action", "status", "reason"),
            },
        ),
        (
            "Recurso Afetado",
            {
                "fields": (
                    "resource_type",
                    "resource_id",
                    "get_payload_diff_display",
                ),
            },
        ),
        (
            "Pessoas Envolvidas",
            {
                "fields": (
                    "get_requester_full_info",
                    "reviewed_by",
                    "review_notes",
                ),
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    actions = ["approve_requests", "reject_requests"]

    def get_status_display_badge(self, obj):
        """Display status with color-coded badges."""
        badges = {
            "pending": "🟡 Pendente",
            "approved": "✅ Aprovada",
            "rejected": "❌ Rejeitada",
        }
        return badges.get(obj.status, obj.status)

    get_status_display_badge.short_description = "Status"
    get_status_display_badge.admin_order_field = "status"

    def get_priority_indicator(self, obj):
        """Show urgency based on request age and type."""
        age_days = (timezone.now() - obj.created_at).days

        if obj.status != "pending":
            return ""

        if age_days >= 3:
            return format_html(
                '<span style="color: red; font-weight: bold;">🚨 URGENTE ({} dias)</span>',
                age_days,
            )
        elif age_days >= 1:
            return format_html(
                '<span style="color: orange;">⚠️ Pendente ({} dias)</span>', age_days
            )
        else:
            return format_html('<span style="color: green;">🕐 Novo</span>')

    get_priority_indicator.short_description = "Prioridade"

    def get_requester_display(self, obj):
        """Display requester with formatted info."""
        if obj.requested_by:
            return format_html(
                "<strong>{}</strong><br><small>{}</small>",
                obj.requested_by.get_full_name() or obj.requested_by.username,
                obj.requested_by.email,
            )
        return "Sistema"

    get_requester_display.short_description = "Solicitante"
    get_requester_display.admin_order_field = "requested_by"

    def get_resource_display(self, obj):
        """Display target resource with type and ID."""
        resource_icons = {
            "user": "👤",
            "client": "🏢",
            "perdcomp": "📋",
        }

        icon = "❓"
        for key, resource_icon in resource_icons.items():
            if key in obj.resource_type.lower():
                icon = resource_icon
                break

        return format_html(
            "{} <strong>{}</strong><br><small>ID: {}</small>",
            icon,
            obj.resource_type.replace("apps.", "").replace("models.", ""),
            obj.resource_id,
        )

    get_resource_display.short_description = "Recurso"

    def get_payload_diff_display(self, obj):
        """Display JSON diff in readable format."""
        if not obj.payload_diff:
            return "Nenhuma alteração de dados"

        try:
            formatted_json = json.dumps(obj.payload_diff, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>',
                formatted_json,
            )
        except (TypeError, ValueError):
            return str(obj.payload_diff)

    get_payload_diff_display.short_description = "Alterações Propostas"

    def get_requester_full_info(self, obj):
        """Display complete requester information."""
        if not obj.requested_by:
            return "Sistema"

        user = obj.requested_by
        return format_html(
            """
            <div style="background: #f8f9fa; padding: 10px; border-radius: 4px;">
                <strong>{}:</strong> {} ({})<br>
                <strong>Email:</strong> {}<br>
                <strong>Papel:</strong> {}<br>
                <strong>Status:</strong> {}
            </div>
            """,
            "Nome",
            user.get_full_name() or "Não informado",
            user.username,
            user.email,
            getattr(user, "role", "Não informado"),
            "Ativo" if user.is_active else "Inativo",
        )

    get_requester_full_info.short_description = "Informações do Solicitante"

    def approve_requests(self, request, queryset):
        """Bulk action to approve selected requests."""
        pending_requests = queryset.filter(status="pending")
        count = pending_requests.count()

        for approval_request in pending_requests:
            approval_request.status = "approved"
            approval_request.reviewed_by = request.user
            approval_request.reviewed_at = timezone.now()
            approval_request.save()

            # Here you would call the actual approval logic
            # approval_request.execute_approved_action()

        self.message_user(request, f"{count} solicitações foram aprovadas com sucesso.")

    approve_requests.short_description = "✅ Aprovar solicitações selecionadas"

    def reject_requests(self, request, queryset):
        """Bulk action to reject selected requests."""
        pending_requests = queryset.filter(status="pending")
        count = pending_requests.count()

        for approval_request in pending_requests:
            approval_request.status = "rejected"
            approval_request.reviewed_by = request.user
            approval_request.reviewed_at = timezone.now()
            approval_request.save()

        self.message_user(request, f"{count} solicitações foram rejeitadas.")

    reject_requests.short_description = "❌ Rejeitar solicitações selecionadas"

    def changelist_view(self, request, extra_context=None):
        """Add custom context to the change list view."""
        extra_context = extra_context or {}

        # Add summary statistics
        pending_count = ApprovalRequest.objects.filter(status="pending").count()
        urgent_count = ApprovalRequest.objects.filter(
            status="pending",
            created_at__lte=timezone.now() - timezone.timedelta(days=3),
        ).count()

        extra_context.update(
            {
                "pending_count": pending_count,
                "urgent_count": urgent_count,
                "title": "Solicitações de Aprovação",
                "subtitle": f"{pending_count} pendentes • {urgent_count} urgentes",
            }
        )

        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        """Approval requests are typically created programmatically."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete approval requests."""
        return request.user.is_superuser
