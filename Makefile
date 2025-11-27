.PHONY: run migrate makemigrations superuser test fmt lint compile install up down logs shell dbshell check collectstatic seed setup_database import-excel import-clients import-perdcomps import-dry import-quiet

# Variáveis úteis
host ?= 127.0.0.1
port ?= 8000
app ?=
email ?=
username ?=
file ?= MieleData.xlsx

# ---- Dev / Django ----

run:
	python backend/manage.py runserver $(host):$(port)

check:
	python backend/manage.py check

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

setup_database:
	cd backend && python manage.py makemigrations
	cd backend && python manage.py migrate
	cd backend && python manage.py setup_roles
	cd backend && python manage.py create_superuser_with_role \
		--username miele-admin \
		--email compasse.mieleadm@gmail.com \
		--first-name Miele \
		--last-name Admin \
		--password mieleadminadmin
	cd backend && python manage.py setup_test_user

# ---- Data Import ----

import-excel:
	cd backend && python manage.py import_excel_data --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-clients:
	cd backend && python manage.py import_excel_data --skip-perdcomps --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-perdcomps:
	cd backend && python manage.py import_excel_data --skip-clients --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-dry:
	cd backend && python manage.py import_excel_data --dry-run --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-quiet:
	cd backend && python manage.py import_excel_data --quiet --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-clients-quiet:
	cd backend && python manage.py import_excel_data --skip-perdcomps --quiet --file "C:/Users/jvads/Compasse/miele-system/$(file)"

import-perdcomps-quiet:
	cd backend && python manage.py import_excel_data --skip-clients --quiet --file "C:/Users/jvads/Compasse/miele-system/$(file)"

# ---- Data Analysis ----

find-duplicates:
	cd backend && python manage.py find_duplicate_perdcomps --file "C:/Users/jvads/Compasse/miele-system/$(file)"

find-duplicates-quiet:
	cd backend && python manage.py find_duplicate_perdcomps --quiet --file "C:/Users/jvads/Compasse/miele-system/$(file)"

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
