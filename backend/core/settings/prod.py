from .base import *  # Importa tudo do base.py

# ==============================================================================
# SEGURANÇA E DEBUG
# ==============================================================================
DEBUG = False

# Evita que cookies sejam vazados em conexões não-HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True  # Força redirecionamento para HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Começa com uma janela curta e reversível. Depois da estabilização do
# domínio oficial, este valor pode ser elevado gradualmente.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

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
