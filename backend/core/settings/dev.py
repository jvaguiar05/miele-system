from .base import *

DEBUG = True

REST_FRAMEWORK.update(
    {
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.AllowAny",),
    }
)
