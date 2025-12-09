from .base import *  # Importa tudo do base.py

# ==============================================================================
# SEGURANÇA E DEBUG
# ==============================================================================
DEBUG = False

# Evita que cookies sejam vazados em conexões não-HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True  # Força redirecionamento para HTTPS

# ==============================================================================
# ARQUIVOS ESTÁTICOS (WHITENOISE)
# ==============================================================================
# O Render não serve estáticos nativamente, precisamos injetar o Whitenoise
# Inserimos logo após o SecurityMiddleware para máxima performance

try:
    # Tenta achar a posição do SecurityMiddleware
    security_index = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    MIDDLEWARE.insert(security_index + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
except ValueError:
    # Se não achar, coloca no topo
    MIDDLEWARE.insert(0, "whitenoise.middleware.WhiteNoiseMiddleware")

# Configuração de compressão e cache para produção
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
