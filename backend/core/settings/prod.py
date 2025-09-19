from datetime import timedelta

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import SIMPLE_JWT, env

DEBUG = False

# ---- Security Headers ----
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "same-origin"

# ---- CORS / CSRF ----
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# ---- Sentry ----
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,  # ajuste depois
        send_default_pii=False,
    )

# ---- JWT ajustes ----
SIMPLE_JWT.update(
    {
        "ACCESS_TOKEN_LIFETIME": timedelta(
            minutes=int(env("SIMPLEJWT_ACCESS_MIN", default=15))
        ),
        "REFRESH_TOKEN_LIFETIME": timedelta(
            days=int(env("SIMPLEJWT_REFRESH_DAYS", default=14))
        ),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
    }
)
