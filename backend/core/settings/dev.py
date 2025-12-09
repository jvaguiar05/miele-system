from .base import *

# ==============================================================================
# AMBIENTE LOCAL
# ==============================================================================
DEBUG = True

# Permite rodar localmente sem problemas de HTTPS
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Garante que qualquer host local funcione (localhost, 127.0.0.1)
ALLOWED_HOSTS = ["*"]

# Permite CORS total para desenvolvimento local (Front Vite -> Back Django)
CORS_ALLOW_ALL_ORIGINS = True
