from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common.audit"
    verbose_name = "Auditoria"

    def ready(self):
        """Importar signals quando a app estiver pronta."""
        # Importar signals aqui para evitar problemas de importação circular
        from . import signals
