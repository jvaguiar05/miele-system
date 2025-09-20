# Registrar o modelo customizado de usuário
from django.conf import settings
from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.apps.identity"


# Configuração do AUTH_USER_MODEL
settings.AUTH_USER_MODEL = "identity.User"
