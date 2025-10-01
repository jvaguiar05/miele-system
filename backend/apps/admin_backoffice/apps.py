from django.apps import AppConfig


class Admin_backofficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_backoffice"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out
        from django.contrib.auth import get_user_model
        from common.audit.services import AuditService

        User = get_user_model()

        def log_user_login(sender, request, user, **kwargs):
            metadata = {}
            ip_address = request.META.get("REMOTE_ADDR") if request else None
            if ip_address:
                metadata["ip"] = ip_address

            # Determine login type based on request path and headers
            if request:
                if "/admin/" in request.path:
                    metadata["login_type"] = "admin"
                elif "/api/" in request.path:
                    metadata["login_type"] = "api"
                else:
                    metadata["login_type"] = "unknown"
            else:
                metadata["login_type"] = "unknown"

            AuditService.log_action(
                action="LOGIN", content_object=user, user=user, metadata=metadata
            )

        def log_user_logout(sender, request, user, **kwargs):
            metadata = {}
            ip_address = request.META.get("REMOTE_ADDR") if request else None
            if ip_address:
                metadata["ip"] = ip_address

            # Determine logout type based on request path
            if request:
                if "/admin/" in request.path:
                    metadata["logout_type"] = "admin"
                elif "/api/" in request.path:
                    metadata["logout_type"] = "api"
                else:
                    metadata["logout_type"] = "unknown"
            else:
                metadata["logout_type"] = "unknown"

            AuditService.log_action(
                action="LOGOUT", content_object=user, user=user, metadata=metadata
            )

        user_logged_in.connect(log_user_login, sender=User)
        user_logged_out.connect(log_user_logout, sender=User)
