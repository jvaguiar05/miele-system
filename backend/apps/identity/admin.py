from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User
from common.shared.admin import AnnotationInline, AttachedFileInline


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""

    list_display = [
        "username",
        "email",
        "get_full_name",
        "role",
        "approval_status",
        "is_active",
        "date_joined",
    ]
    list_filter = [
        "role",
        "approval_status",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
        "last_login",
    ]
    search_fields = ["username", "email", "first_name", "last_name"]
    readonly_fields = ["public_id", "date_joined", "last_login"]
    ordering = ["-date_joined"]

    fieldsets = (
        (
            "Informações Pessoais",
            {
                "fields": ("public_id", "username", "email", "first_name", "last_name"),
            },
        ),
        (
            "Senha",
            {
                "fields": ("password",),
            },
        ),
        (
            "Permissões e Status",
            {
                "fields": (
                    "role",
                    "approval_status",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
        (
            "Grupos e Permissões",
            {
                "fields": ("groups", "user_permissions"),
                "classes": ["collapse"],
            },
        ),
        (
            "Datas Importantes",
            {
                "fields": ("date_joined", "last_login", "suspended_at", "deleted_at"),
            },
        ),
    )

    add_fieldsets = (
        (
            "Criar Usuário",
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "role",
                    "approval_status",
                ),
            },
        ),
    )

    filter_horizontal = ["groups", "user_permissions"]

    # Add the generic inlines for annotations and files
    inlines = [AnnotationInline, AttachedFileInline]

    def get_full_name(self, obj):
        """Display full name with formatting."""
        full_name = obj.get_full_name()
        if full_name:
            return format_html("<strong>{}</strong>", full_name)
        return "-"

    get_full_name.short_description = "Nome Completo"
    get_full_name.admin_order_field = "first_name"

    def get_queryset(self, request):
        """Filter out soft-deleted users by default."""
        qs = super().get_queryset(request)
        return qs.filter(deleted_at__isnull=True)

    actions = ["approve_users", "suspend_users", "activate_users"]

    def approve_users(self, request, queryset):
        """Batch action to approve pending users."""
        updated = queryset.filter(approval_status=User.ApprovalStatus.PENDING).update(
            approval_status=User.ApprovalStatus.APPROVED, is_active=True
        )
        self.message_user(request, f"{updated} usuários foram aprovados.")

    approve_users.short_description = "Aprovar usuários selecionados"

    def suspend_users(self, request, queryset):
        """Batch action to suspend users."""
        from django.utils import timezone

        updated = queryset.filter(is_active=True).update(
            is_active=False, suspended_at=timezone.now()
        )
        self.message_user(request, f"{updated} usuários foram suspensos.")

    suspend_users.short_description = "Suspender usuários selecionados"

    def activate_users(self, request, queryset):
        """Batch action to activate users."""
        updated = queryset.filter(is_active=False).update(
            is_active=True, suspended_at=None
        )
        self.message_user(request, f"{updated} usuários foram ativados.")

    activate_users.short_description = "Ativar usuários selecionados"
