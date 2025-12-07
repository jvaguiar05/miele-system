from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html
from .models import Annotation, AttachedFile


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    """Admin configuration for Annotation model."""

    list_display = [
        "__str__",
        "get_user_display",
        "content_type",
        "object_id",
        "created_at",
    ]
    list_filter = ["content_type", "created_at", "updated_at"]
    search_fields = ["content", "user_id"]
    readonly_fields = ["public_id", "created_at", "updated_at"]

    fieldsets = (
        (
            "Informações Gerais",
            {
                "fields": ("public_id", "content"),
            },
        ),
        (
            "Vinculação",
            {
                "fields": ("content_type", "object_id"),
            },
        ),
        (
            "Controle",
            {
                "fields": ("user_id", "created_at", "updated_at", "deleted_at"),
            },
        ),
    )

    def get_user_display(self, obj):
        """Display user name/email instead of raw ID."""
        user = obj.user
        if user:
            return format_html(
                "<strong>{}</strong><br><small>{}</small>",
                user.get_full_name() or user.username,
                user.email,
            )
        return f"User #{obj.user_id} (não encontrado)"

    get_user_display.short_description = "Usuário"
    get_user_display.admin_order_field = "user_id"


@admin.register(AttachedFile)
class AttachedFileAdmin(admin.ModelAdmin):
    """Admin configuration for AttachedFile model."""

    list_display = [
        "file_name",
        "get_uploaded_by_display",
        "file_type",
        "mime_type",
        "file_size_human",
        "content_type",
        "created_at",
    ]
    # "sync_status" removido do list_filter
    list_filter = ["file_type", "content_type", "created_at"]
    search_fields = ["file_name", "drive_file_id", "uploaded_by_id"]
    readonly_fields = ["public_id", "file_size_human", "created_at"]

    fieldsets = (
        (
            "Informações do Arquivo",
            {
                "fields": (
                    "public_id",
                    "file_name",
                    "file_type",
                    "mime_type",
                    "file_size",
                    "file_size_human",
                ),
            },
        ),
        (
            "Google Drive",
            {
                "fields": ("drive_file_id",),
            },
        ),
        (
            "Vinculação",
            {
                "fields": ("content_type", "object_id"),
            },
        ),
        (
            "Controle",
            {
                "fields": ("uploaded_by_id", "created_at"),
            },
        ),
    )

    def get_uploaded_by_display(self, obj):
        """Display user name/email instead of raw ID."""
        user = obj.uploaded_by
        if user:
            return format_html(
                "<strong>{}</strong><br><small>{}</small>",
                user.get_full_name() or user.username,
                user.email,
            )
        return f"User #{obj.uploaded_by_id} (não encontrado)"

    get_uploaded_by_display.short_description = "Enviado por"
    get_uploaded_by_display.admin_order_field = "uploaded_by_id"


# Generic Inline classes for use in other admin configurations
class AnnotationInline(GenericTabularInline):
    """Generic inline for annotations in related models."""

    model = Annotation
    extra = 0
    fields = ["user_id", "content", "created_at"]
    readonly_fields = ["created_at"]
    verbose_name = "Anotação"
    verbose_name_plural = "Anotações"
    can_delete = True

    def get_queryset(self, request):
        """Filter out soft-deleted annotations."""
        qs = super().get_queryset(request)
        return qs.filter(deleted_at__isnull=True)


class AttachedFileInline(GenericTabularInline):
    """Generic inline for attached files in related models."""

    model = AttachedFile
    extra = 0
    fields = [
        "file_name",
        "file_type",
        "drive_file_id",
        "file_size",
        "uploaded_by_id",
        "created_at",
    ]
    readonly_fields = ["created_at"]
    verbose_name = "Arquivo Anexo"
    verbose_name_plural = "Arquivos Anexos"
    can_delete = True
