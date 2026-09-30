"""Explicit local-only database configuration for maintenance commands."""
from .dev import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR.parent / ".sandbox" / "miele-sandbox.sqlite3"}}
SECRET_KEY = "miele-local-sandbox-not-for-production"
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": SECRET_KEY}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
GDRIVE_CLIENT_ID = GDRIVE_CLIENT_SECRET = GDRIVE_REFRESH_TOKEN = ""
GDRIVE_CLIENTS_FOLDER_ID = GDRIVE_PERDCOMPS_FOLDER_ID = ""
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
