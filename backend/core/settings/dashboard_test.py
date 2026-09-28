"""Ephemeral SQLite database for dashboard tests; never uses the configured DB."""
from .base import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
SECRET_KEY = "isolated-dashboard-tests"
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": SECRET_KEY}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
GDRIVE_CLIENT_ID = GDRIVE_CLIENT_SECRET = GDRIVE_REFRESH_TOKEN = ""
GDRIVE_CLIENTS_FOLDER_ID = GDRIVE_PERDCOMPS_FOLDER_ID = ""
