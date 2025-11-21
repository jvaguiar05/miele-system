from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Client, Address
from common.shared.admin import AnnotationInline, AttachedFileInline


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Admin configuration for Address model."""

    list_display = ["__str__", "municipio", "uf", "cep", "created_at"]
    list_filter = ["uf", "municipio", "created_at"]
    search_fields = ["logradouro", "numero", "bairro", "municipio", "cep"]
    readonly_fields = ["public_id", "created_at", "updated_at"]

    fieldsets = (
        (
            "Informações Gerais",
            {
                "fields": ("public_id",),
            },
        ),
        (
            "Endereço",
            {
                "fields": ("logradouro", "numero", "complemento", "bairro"),
            },
        ),
        (
            "Localização",
            {
                "fields": ("municipio", "uf", "cep"),
            },
        ),
        (
            "Controle",
            {
                "fields": ("created_at", "updated_at", "deleted_at"),
            },
        ),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Admin configuration for Client model."""

    list_display = [
        "razao_social",
        "nome_fantasia",
        "cnpj",
        "client_status",
        "regime_tributacao",
        "is_active",
        "created_at",
    ]
    list_filter = [
        "client_status",
        "regime_tributacao",
        "is_active",
        "recuperacao_judicial",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        "razao_social",
        "nome_fantasia",
        "cnpj",
        "email_comercial",
        "email_contato",
    ]
    readonly_fields = ["public_id", "created_at", "updated_at"]
    ordering = ["-created_at"]

    fieldsets = (
        (
            "Informações Gerais",
            {
                "fields": ("public_id", "razao_social", "nome_fantasia", "cnpj"),
            },
        ),
        (
            "Documentos e Registros",
            {
                "fields": ("inscricao_estadual", "inscricao_municipal", "tipo_empresa"),
            },
        ),
        (
            "Status e Classificação",
            {
                "fields": (
                    "client_status",
                    "regime_tributacao",
                    "is_active",
                    "recuperacao_judicial",
                ),
            },
        ),
        (
            "Endereço",
            {
                "fields": ("address_id",),
                "description": "ID do endereço associado (para vincular use o campo Address ID)",
            },
        ),
        (
            "Contatos Comerciais",
            {
                "fields": ("telefone_comercial", "email_comercial", "website"),
                "classes": ["collapse"],
            },
        ),
        (
            "Contatos Diretos",
            {
                "fields": ("telefone_contato", "email_contato"),
                "classes": ["collapse"],
            },
        ),
        (
            "Dados Fiscais",
            {
                "fields": ("cnaes", "responsavel_financeiro", "contador_responsavel"),
                "classes": ["collapse"],
            },
        ),
        (
            "Estrutura Organizacional",
            {
                "fields": ("quadro_societario", "cargos"),
                "classes": ["collapse"],
            },
        ),
        (
            "Documentos e Contratos",
            {
                "fields": (
                    "contrato_social",
                    "ultima_alteracao_contratual",
                    "rg_cpf_socios",
                    "certificado_digital",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Controles e Autorizações",
            {
                "fields": ("autorizado_para_envio", "atividades"),
                "classes": ["collapse"],
            },
        ),
        (
            "Controle",
            {
                "fields": ("created_at", "updated_at", "deleted_at"),
            },
        ),
    )

    # Add the generic inlines for annotations and files (no AddressInline due to relationship structure)
    inlines = [AnnotationInline, AttachedFileInline]

    def get_queryset(self, request):
        """Filter out soft-deleted clients by default."""
        qs = super().get_queryset(request)
        return qs.filter(deleted_at__isnull=True)

    actions = ["activate_clients", "suspend_clients", "archive_clients"]

    def activate_clients(self, request, queryset):
        """Batch action to activate clients."""
        updated = queryset.update(
            client_status=Client.ClientStatus.ACTIVE, is_active=True
        )
        self.message_user(request, f"{updated} clientes foram ativados.")

    activate_clients.short_description = "Ativar clientes selecionados"

    def suspend_clients(self, request, queryset):
        """Batch action to suspend clients."""
        updated = queryset.update(
            client_status=Client.ClientStatus.SUSPENDED, is_active=False
        )
        self.message_user(request, f"{updated} clientes foram suspensos.")

    suspend_clients.short_description = "Suspender clientes selecionados"

    def archive_clients(self, request, queryset):
        """Batch action to archive clients."""
        updated = queryset.update(
            client_status=Client.ClientStatus.ARCHIVED, is_active=False
        )
        self.message_user(request, f"{updated} clientes foram arquivados.")

    archive_clients.short_description = "Arquivar clientes selecionados"

    def get_readonly_fields(self, request, obj=None):
        """Make CNPJ readonly for existing objects to prevent accidental changes."""
        readonly_fields = list(self.readonly_fields)
        if obj and obj.pk:  # Editing existing object
            readonly_fields.append("cnpj")
        return readonly_fields
