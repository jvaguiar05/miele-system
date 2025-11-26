from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.contrib import messages
import json
from .models import ApprovalRequest
from .services import ApprovalService


class StatusFilter(SimpleListFilter):
    """Filtro de status com 'Pending' como padrão - o coração da funcionalidade."""

    title = "Status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [
            ("pending", "🔴 Pendentes (Ação Necessária)"),
            ("approved", "✅ Aprovadas (Executadas)"),
            ("rejected", "❌ Rejeitadas (Executadas)"),
            ("all", "📋 Todas"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "approved":
            return queryset.filter(status="executed", was_approved=True)
        elif self.value() == "rejected":
            return queryset.filter(status="executed", was_approved=False)
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
        "subject",
        "action",
        "reason",
        "resource_type",
        "resource_id",
        "requested_by",
        "created_at",
        "updated_at",
        "approved_at",
        "executed_at",
        "get_payload_diff_display",
        "get_requester_full_info",
        "get_approval_actions",
    ]

    # Force ordering by creation time (oldest first) - queue management
    ordering = ["created_at"]

    fieldsets = (
        (
            "📋 Solicitação",
            {
                "fields": ("public_id", "subject", "action", "reason"),
                "classes": ("wide",),
            },
        ),
        (
            "🎯 Decisão (EDITAR AQUI)",
            {
                "fields": ("status", "was_approved", "approval_notes"),
                "classes": ("wide", "collapse"),
                "description": "Para APROVAR: Status=Executed + Was_approved=True. Para REJEITAR: Status=Executed + Was_approved=False.",
            },
        ),
        (
            "🔍 Detalhes do Recurso",
            {
                "fields": (
                    "resource_type",
                    "resource_id",
                    "get_payload_diff_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "👥 Pessoas Envolvidas",
            {
                "fields": (
                    "get_requester_full_info",
                    "approved_by",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "⏰ Controle de Tempo",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "approved_at",
                    "executed_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "⚡ Ações Rápidas",
            {
                "fields": ("get_approval_actions",),
                "classes": ("wide",),
            },
        ),
    )

    actions = ["approve_requests", "reject_requests"]

    def get_status_display_badge(self, obj):
        """Display status with color-coded badges."""
        if obj.status == "pending":
            return "🔴 Pendente"
        elif obj.status == "executed":
            if obj.was_approved:
                return "✅ Aprovada"
            else:
                return "❌ Rejeitada"
        elif obj.status == "cancelled":
            return "🚫 Cancelada"
        return obj.get_status_display()

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
        success_count = 0
        error_count = 0

        for approval_request in pending_requests:
            try:
                notes = f"Aprovação em lote via admin por {request.user.get_full_name() or request.user.username} em {timezone.now().strftime('%d/%m/%Y às %H:%M')}"

                # Use the new approve_and_execute method
                approval_request.approve_and_execute(request.user, notes)

                # Execute the changes
                ApprovalService._execute_change(approval_request, request.user)

                success_count += 1

            except Exception as e:
                error_count += 1
                messages.error(
                    request,
                    f"❌ Erro ao aprovar solicitação {approval_request.subject}: {str(e)}",
                )

        if success_count > 0:
            messages.success(
                request,
                f"✅ {success_count} solicitações foram aprovadas e executadas automaticamente!",
            )
        if error_count > 0:
            messages.warning(
                request, f"⚠️ {error_count} solicitações não puderam ser processadas."
            )

    approve_requests.short_description = "✅ Aprovar solicitações selecionadas"

    def reject_requests(self, request, queryset):
        """Bulk action to reject selected requests."""
        pending_requests = queryset.filter(status="pending")
        count = pending_requests.count()
        success_count = 0
        error_count = 0

        for approval_request in pending_requests:
            try:
                notes = f"Rejeição em lote via admin por {request.user.get_full_name() or request.user.username} em {timezone.now().strftime('%d/%m/%Y às %H:%M')}"

                # Use the new reject_and_execute method
                approval_request.reject_and_execute(request.user, notes)

                # Handle user rejection if applicable
                if (
                    approval_request.resource_type == "identity.User"
                    and approval_request.action == "activate"
                ):
                    try:
                        from django.apps import apps

                        app_label, model_name = approval_request.resource_type.split(
                            "."
                        )
                        model_class = apps.get_model(app_label, model_name)
                        user = model_class.objects.get(pk=approval_request.resource_id)

                        user.approval_status = "declined"
                        user.is_active = False
                        user.save()

                    except Exception:
                        pass

                success_count += 1

            except Exception as e:
                error_count += 1
                messages.error(
                    request,
                    f"❌ Erro ao rejeitar solicitação {approval_request.subject}: {str(e)}",
                )

        if success_count > 0:
            messages.success(
                request, f"❌ {success_count} solicitações foram rejeitadas!"
            )
        if error_count > 0:
            messages.warning(
                request, f"⚠️ {error_count} solicitações não puderam ser processadas."
            )

    reject_requests.short_description = "❌ Rejeitar solicitações selecionadas"

    def get_approval_actions(self, obj):
        """Show quick approval action buttons."""
        if obj.status != "pending":
            status_text = "✅ Aprovada" if obj.was_approved else "❌ Rejeitada"
            return format_html(
                f'<span style="color: #888;">🔒 Solicitação já processada: {status_text}</span>'
            )

        return format_html(
            """<div style="display: flex; gap: 10px; align-items: center; flex-direction: column;">
                <div>
                    <strong>⚡ Ações Rápidas:</strong>
                </div>
                <div style="display: flex; gap: 10px;">
                    <span style="padding: 5px 10px; background: #e8f5e8; border: 1px solid #4CAF50; border-radius: 3px;">
                        ✅ <strong>APROVAR:</strong> Status = "Executed" + Was approved = ✅
                    </span>
                    <span style="padding: 5px 10px; background: #ffe8e8; border: 1px solid #f44336; border-radius: 3px;">
                        ❌ <strong>REJEITAR:</strong> Status = "Executed" + Was approved = ❌
                    </span>
                </div>
            </div>
            <div style="margin-top: 10px; padding: 8px; background: #f0f8ff; border-left: 4px solid #2196F3;">
                💡 <strong>Dica:</strong> Use o campo "Approval notes" para adicionar observações sobre sua decisão.
            </div>"""
        )

    get_approval_actions.short_description = "Ações de Aprovação"

    def save_model(self, request, obj, form, change):
        """Handle approval status changes with new simplified logic."""
        if change:  # Only on updates, not creation
            # Get the original object to compare status changes
            try:
                original = ApprovalRequest.objects.get(pk=obj.pk)
                status_changed = original.status != obj.status
                original_status = original.status
            except ApprovalRequest.DoesNotExist:
                status_changed = False
                original_status = None

            # Handle transition from pending to executed (approved/rejected)
            if (
                status_changed
                and obj.status == "executed"
                and original_status == "pending"
            ):
                try:
                    # Check was_approved to determine if this is approval or rejection
                    is_approval = obj.was_approved

                    # Set approval metadata
                    obj.approved_by = request.user
                    obj.approved_at = timezone.now()
                    obj.executed_at = timezone.now()

                    # Add automatic note if none provided
                    if not obj.approval_notes:
                        action_text = "aprovada" if is_approval else "rejeitada"
                        obj.approval_notes = f"Solicitação {action_text} via admin por {request.user.get_full_name() or request.user.username} em {timezone.now().strftime('%d/%m/%Y às %H:%M')}"

                    # Save the approval request first
                    super().save_model(request, obj, form, change)

                    # Execute the changes if approved
                    if is_approval:
                        try:
                            ApprovalService._execute_change(obj, request.user)
                            messages.success(
                                request,
                                f"✅ Solicitação aprovada e executada com sucesso! As mudanças foram aplicadas ao {obj.resource_type}.",
                            )
                        except Exception as e:
                            messages.error(
                                request,
                                f"❌ Erro na execução: {str(e)}. Solicitação foi marcada como aprovada mas não executada.",
                            )
                    else:  # rejected
                        # Handle user activation rejection
                        if (
                            obj.resource_type == "identity.User"
                            and obj.action == "activate"
                        ):
                            try:
                                from django.apps import apps

                                app_label, model_name = obj.resource_type.split(".")
                                model_class = apps.get_model(app_label, model_name)
                                user = model_class.objects.get(pk=obj.resource_id)

                                user.approval_status = "declined"
                                user.is_active = False
                                user.save()

                            except Exception:
                                pass  # Ignore errors in rejection handling

                        messages.success(
                            request, "❌ Solicitação rejeitada com sucesso!"
                        )

                    return  # Don't call super() again

                except Exception as e:
                    messages.error(
                        request, f"❌ Erro ao processar solicitação: {str(e)}"
                    )
                    # Revert status change on error
                    obj.status = original_status
                    super().save_model(request, obj, form, change)
                    return

        super().save_model(request, obj, form, change)

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
