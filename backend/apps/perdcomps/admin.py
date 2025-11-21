from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import PerDcomp
from common.shared.admin import AnnotationInline, AttachedFileInline


@admin.register(PerDcomp)
class PerDcompAdmin(admin.ModelAdmin):
    """Admin configuration for PerDcomp model."""

    list_display = [
        "numero",
        "numero_perdcomp",
        "get_client_display",
        "status",
        "valor_pedido",
        "data_transmissao",
        "created_at",
    ]
    list_filter = [
        "status",
        "data_transmissao",
        "data_vencimento",
        "created_at",
        "updated_at",
    ]
    search_fields = ["numero", "numero_perdcomp", "cnpj", "processo_protocolo"]
    readonly_fields = ["public_id", "created_at", "updated_at"]
    ordering = ["-created_at"]
    date_hierarchy = "data_transmissao"

    fieldsets = (
        (
            "Informações Gerais",
            {
                "fields": (
                    "public_id",
                    "numero",
                    "numero_perdcomp",
                    "processo_protocolo",
                ),
            },
        ),
        (
            "Vinculação",
            {
                "fields": ("client_id", "cnpj", "created_by_id"),
            },
        ),
        (
            "Status e Datas",
            {
                "fields": (
                    "status",
                    "data_transmissao",
                    "data_vencimento",
                    "data_competencia",
                ),
            },
        ),
        (
            "Dados Fiscais",
            {
                "fields": ("tributo_pedido", "competencia"),
            },
        ),
        (
            "Valores Monetários",
            {
                "fields": (
                    "valor_pedido",
                    "valor_compensado",
                    "valor_recebido",
                    "valor_saldo",
                    "valor_selic",
                ),
            },
        ),
        (
            "Controle",
            {
                "fields": ("is_active", "created_at", "updated_at", "deleted_at"),
            },
        ),
    )

    # Add the generic inlines for annotations and files
    inlines = [AnnotationInline, AttachedFileInline]

    def get_client_display(self, obj):
        """Display client information instead of raw ID."""
        try:
            from apps.clients.models import Client

            client = Client.objects.get(id=obj.client_id)
            return format_html(
                "<strong>{}</strong><br><small>CNPJ: {}</small>",
                client.razao_social or client.nome_fantasia,
                client.cnpj,
            )
        except Client.DoesNotExist:
            return format_html(
                "<em>Cliente #{} (não encontrado)</em><br><small>CNPJ: {}</small>",
                obj.client_id,
                obj.cnpj,
            )

    get_client_display.short_description = "Cliente"
    get_client_display.admin_order_field = "client_id"

    def get_queryset(self, request):
        """Filter out soft-deleted PerDcomps by default."""
        qs = super().get_queryset(request)
        return qs.filter(deleted_at__isnull=True)

    actions = [
        "mark_as_transmitted",
        "mark_as_processing",
        "mark_as_approved",
        "mark_as_cancelled",
    ]

    def mark_as_transmitted(self, request, queryset):
        """Batch action to mark as transmitted."""
        from django.utils import timezone

        updated = queryset.filter(status=PerDcomp.Status.RASCUNHO).update(
            status=PerDcomp.Status.TRANSMITIDO, data_transmissao=timezone.now()
        )
        self.message_user(
            request, f"{updated} PER/DCOMPs foram marcados como transmitidos."
        )

    mark_as_transmitted.short_description = "Marcar como transmitidos"

    def mark_as_processing(self, request, queryset):
        """Batch action to mark as processing."""
        updated = queryset.filter(status=PerDcomp.Status.TRANSMITIDO).update(
            status=PerDcomp.Status.EM_PROCESSAMENTO
        )
        self.message_user(
            request, f"{updated} PER/DCOMPs foram marcados como em processamento."
        )

    mark_as_processing.short_description = "Marcar como em processamento"

    def mark_as_approved(self, request, queryset):
        """Batch action to mark as approved."""
        updated = queryset.filter(status=PerDcomp.Status.EM_PROCESSAMENTO).update(
            status=PerDcomp.Status.DEFERIDO
        )
        self.message_user(request, f"{updated} PER/DCOMPs foram deferidos.")

    mark_as_approved.short_description = "Marcar como deferidos"

    def mark_as_cancelled(self, request, queryset):
        """Batch action to cancel."""
        updated = queryset.update(status=PerDcomp.Status.CANCELADO)
        self.message_user(request, f"{updated} PER/DCOMPs foram cancelados.")

    mark_as_cancelled.short_description = "Cancelar PER/DCOMPs selecionados"
