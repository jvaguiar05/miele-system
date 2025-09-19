.PHONY: run migrate makemigrations superuser test fmt lint compile install up down logs shell dbshell check collectstatic seed

# Variáveis úteis
host ?= 127.0.0.1
port ?= 8000
app ?=
email ?=
username ?=

# ---- Dev / Django ----

run:
	python backend/manage.py runserver $(host):$(port)

migrate:
	python backend/manage.py migrate

makemigrations:
ifeq ($(app),)
	python backend/manage.py makemigrations
else
	python backend/manage.py makemigrations $(app)
endif

superuser:
ifeq ($(and $(email),$(username)),)
	python backend/manage.py createsuperuser
else
	python backend/manage.py createsuperuser --email $(email) --username $(username)
endif

shell:
	python backend/manage.py shell

dbshell:
	python backend/manage.py dbshell

collectstatic:
	python backend/manage.py collectstatic --noinput

seed:
	python backend/manage.py runscript load_demo_data

# ---- Quality ----

test:
	pytest -q

# ---- Dependencies ----

compile:
	pip-compile requirements/base.in --output-file=requirements/requirements.txt
	pip-compile requirements/dev.in --output-file=requirements/requirements-dev.txt

install:
	pip install -r requirements/requirements-dev.txt

# ---- Docker ----

compose:
	docker compose

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f
