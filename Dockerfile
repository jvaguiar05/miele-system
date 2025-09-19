# ===== Miele System — Dockerfile =====
# Multi-stage build for smaller images and faster installs
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     PIP_DISABLE_PIP_VERSION_CHECK=1     POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     libpq-dev     curl     ca-certificates     && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first (better caching)
COPY requirements/requirements.txt requirements.txt
COPY requirements/requirements-dev.txt requirements-dev.txt

# Install prod deps by default (dev file is present for flexibility)
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY backend backend
COPY backend/scripts scripts

# Expose
EXPOSE 8000

# Default envs (can be overridden by compose)
ENV DJANGO_SETTINGS_MODULE=core.settings.prod     PORT=8000

# Collect static in production (optional; only if STATIC_ROOT is set)
# Uncomment if/when you add static pipeline:
# RUN python backend/manage.py collectstatic --noinput || true

# Default command uses gunicorn; compose overrides when needed
CMD gunicorn core.wsgi:application --bind 0.0.0.0:${PORT} --workers 3 --timeout 120 --access-logfile -
