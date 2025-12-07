from django.apps import AppConfig


class SharedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common.shared"
    verbose_name = "Shared Models"

    def ready(self):
        # Importar sinais aqui para registrar os receivers
        try:
            import common.shared.signals
        except ImportError:
            pass
