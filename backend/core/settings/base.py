from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "dev-insecure-secret"),
    ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    CORS_ALLOW_ALL_ORIGINS=(bool, True),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    TIME_ZONE=(str, "America/Sao_Paulo"),
    LANGUAGE_CODE=(str, "pt-br"),
    SENTRY_DSN=(str, ""),
    SIMPLEJWT_ACCESS_MIN=(int, 15),
    SIMPLEJWT_REFRESH_DAYS=(int, 14),
)

ENV_FILE = BASE_DIR.parent / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(str(ENV_FILE))

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

# Applications
INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    # Local apps
    "apps.identity",
    "apps.clients",
    "apps.perdcomps",
    "apps.admin_backoffice",
    # Common modules
    "common.audit",
    "common.approvals",
    "common.shared",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.FailedLoginTrackingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CorrelationIdMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = env("LANGUAGE_CODE")
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
MEDIA_URL = "media/"
MEDIA_ROOT = str(BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "identity.User"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "api.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # 🔒 Throttling global (baseline)
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10/minute",
        "user": "100/minute",
        # Auth-specific throttling
        "auth_login": "5/min",
        "auth_register": "3/hour",
        "auth_password_reset": "2/hour",
        "auth_refresh": "30/hour",
        "auth_per_user": "20/min",
        "sensitive_action": "10/hour",
        "failed_login": "5/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("SIMPLEJWT_ACCESS_MIN", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("SIMPLEJWT_REFRESH_DAYS", default=14)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Miele System API",
    "DESCRIPTION": "Sistema de gestão empresarial com foco em Clientes e PER/DCOMPs. API REST completa com autenticação JWT, RBAC e recursos administrativos.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
    "TAGS": [
        {
            "name": "Autenticação",
            "description": "Endpoints de autenticação e autorização",
        },
        {
            "name": "Admin",
            "description": "Endpoints administrativos que requerem privilégios de admin",
        },
        {
            "name": "Usuários",
            "description": "Endpoints de gerenciamento de usuários",
        },
        {
            "name": "Clientes",
            "description": "Endpoints relacionados a clientes",
        },
        {
            "name": "Endereços",
            "description": "Endpoints relacionados a endereços de clientes",
        },
        {
            "name": "Clientes - Anotações",
            "description": "Endpoints relacionados às anotações feitas por usuários em clientes",
        },
        {
            "name": "Clientes - Arquivos",
            "description": "Endpoints relacionados aos arquivos anexados a clientes",
        },
        {
            "name": "PER/DCOMPs",
            "description": "Endpoints relacionados a PER/DCOMPs (Perdas e Compensações)",
        },
        {
            "name": "PER/DCOMPs - Anotações",
            "description": "Endpoints relacionados às anotações dos PER/DCOMPs",
        },
        {
            "name": "PER/DCOMPs - Arquivos",
            "description": "Endpoints relacionados aos arquivos anexados aos PER/DCOMPs",
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "defaultModelExpandDepth": 2,
        "defaultModelsExpandDepth": 1,
    },
    "REDOC_SETTINGS": {
        "LAZY_RENDERING": False,
    },
}

# CORS
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# Logging JSON (basic)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s","request_id":"%(request_id)s"}'
        }
    },
    "filters": {
        "correlation": {
            "()": "common.observability.logging.RequestIdFilter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation"],
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Configuração de campos sensíveis que requerem aprovação
SENSITIVE_FIELDS_CONFIG = {
    "identity.User": ["role", "is_active", "email", "approval_status"],
    "clients.Client": ["cnpj", "razao_social", "status", "is_active"],
    "perdcomps.LossCompensation": [
        "reference_number",
        "loss_amount",
        "compensation_amount",
        "status",
        "loss_type",
        "loss_date",
        "approval_deadline",
        "is_active",
    ],
}
