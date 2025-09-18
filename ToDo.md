# Plano de Implementação — Miele System (10 dias)

> Roadmap prático em 10 dias corridos para levar o **Miele System** do zero ao **deploy em produção**.  
> Baseado em: `ESCOPO.md`, `ARQUITETURA.md`, `ENDPOINTS.md`, `ADMIN.md`, `USE-CASES.md` e `docs/db`.

---

## 📎 Premissas

- **Backend:** Django 5.x + DRF, Python 3.11+
- **DB:** PostgreSQL  
   **Cache/Queue:** Redis  
   **Storage:** Local (dev) / S3 (prod)
- **Auth:** SimpleJWT (access curto, refresh com rotação + blacklist), RBAC, 2FA TOTP
- **Observabilidade:** Logs JSON, Sentry, `/health/live` e `/health/ready`
- **Documentação:** drf-spectacular (OpenAPI) + exemplos e erros canônicos
- **Tarefas:** Celery + Redis (e-mail, limpeza, rotinas)
- **Integração externa:** BrasilAPI (CNPJ) (MVP)

---

## Dia 1 — Fundamentos & DevX

**Objetivo:** Repositório utilizável por qualquer dev em 1 comando.

- [ ] Estruturar `backend/` (core, apps base, common, api, scripts)
- [ ] `pyproject.toml` (ruff, black, isort, mypy opcional), `Makefile` (up/migrate/test/lint/format)
- [ ] `docker-compose.yml` (web, postgres, redis) + `Dockerfile` (prod-ready com gunicorn/uvicorn)
- [ ] `core/settings/{base,dev,prod}.py` com 12‑Factor via `.env` (django-environ)
- [ ] `common/observability/logging.py` (logs JSON) e Sentry (config, DSN via env)
- [ ] CORS, CSRF (se web), SECURE\_\* (apenas em prod), DRF throttling global
- [ ] Health endpoints: `/health/live` e `/health/ready`
- [ ] `.env.example` completo (DB, Redis, JWT, S3, Email, Sentry)
- [ ] Pre-commit (ruff/black/isort/mypy)

**Entrega do dia:** Projeto sobe com `make up` (dev), health endpoints respondem OK.

---

## Dia 2 — Identity (Modelos, JWT, RBAC, 2FA base)

**Objetivo:** Autenticar com JWT; conta pendente para aprovação.

- [ ] `apps/identity`: User custom (`AUTH_USER_MODEL`), `approval_status`, `soft-delete`
- [ ] SimpleJWT: access (~15m), refresh (7–14d) com rotação + blacklist
- [ ] Endpoints: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- [ ] RBAC: Groups/Permissions nativos; permissões DRF por viewset
- [ ] `users/me` (GET/PATCH) + `password` (POST)
- [ ] Throttling e `django-ratelimit` em `/auth/*`
- [ ] 2FA TOTP (django-otp) — modelo e enrolment endpoints esqueleto (ativação completa no Dia 7)

**Entrega do dia:** Fluxo JWT completo (login/refresh/logout), registro com status pendente.

---

## Dia 3 — Auditoria & Aprovações (Infra de domínio)

**Objetivo:** Trilhas confiáveis de ações e mecanismo de approval.

- [ ] `common/audit`: `AuditLog` (modelo + serviço), `correlation_id` middleware
- [ ] `app_approval_requests`: subject, action, status, payload_diff, reason, requested_by/approved_by
- [ ] Hooks transacionais: salvar AuditLog em mudanças críticas (signals/services)
- [ ] Endpoints admin básicos para listar/aprovar/recusar requests (sem UI)

**Entrega do dia:** Criar request e aprová-lo dispara mudança e gera AuditLog.

---

## Dia 4 — Clients (CRUD + Rules + Anexos/Notas)

**Objetivo:** Gestão de clientes com ciclos e campos sensíveis via request.

- [ ] `apps/clients`: models (`clients`, `client_address`), serializers, viewsets, services
- [ ] Regras: CNPJ único ativo (índice parcial), status: pending→active→suspended→archived
- [ ] Endpoints principais (vide ENDPOINTS.md) + filtros (django-filter)
- [ ] Notas: `app_notes` (generic via ContentType)
- [ ] Anexos: `app_files` (owner=client); backend local em dev (storage wrapper)

**Entrega do dia:** CRUD cliente com notas/anexos; request para alteração sensível (CNPJ).

---

## Dia 5 — PER/DCOMPs (CRUD + Regras + Anexos)

**Objetivo:** Documentos tributários por cliente prontos.

- [ ] `apps/perdcomps`: models, serializers, viewsets, services
- [ ] Regras: pending→active→archived; chaves `(client, cnpj, competencia)` únicas ativas
- [ ] Endpoints (vide ENDPOINTS.md), paginação padrão, filtros por cliente/CNPJ/competência
- [ ] Anexos específicos: owner=perdcomp (`recibo`, `pedido_recebimento`, `perdcomp_summary`)

**Entrega do dia:** CRUD PER/DCOMP com anexo e vínculo ao cliente; requests sensíveis funcionando.

---

## Dia 6 — OpenAPI, Erros Canônicos & Testes

**Objetivo:** Contratos estáveis e qualidade mínima garantida.

- [ ] `drf-spectacular` configurado (schemas, exemplos de erro, segurança)
- [ ] Envelope de erro único (exception handler)
- [ ] Testes: pytest + pytest-django; factories (model_bakery/factory_boy)
- [ ] Cobrir: auth básico, approvals, clients e perdcomps (happy path + erros)
- [ ] Scripts `scripts/load_demo_data.py` (seed dev)

**Entrega do dia:** `/api/docs` e `/api/schema` ok; suíte de testes inicial verde.

---

## Dia 7 — Admin Backoffice (seguro) & 2FA completo

**Objetivo:** Operação/administração via Django Admin endurecido.

- [ ] URL custom `/backoffice/`, `is_staff=True`, grupos (Admin/Approver/Auditor/Operator)
- [ ] Tema/UX (Jazzmin ou overrides essenciais), list_display, filtros, buscas
- [ ] Páginas auxiliares: dashboard (cards + gráfico simples), fila de approvals, logs
- [ ] Reautenticação+TOTP para ações sensíveis (middleware/gate)
- [ ] Lockout e rate-limit do login do backoffice

**Entrega do dia:** Backoffice utilizável (aprovações, visão de logs, gestão básica).

---

## Dia 8 — Assíncrono, E-mail & CNPJ

**Objetivo:** Operações robustas e integrações essenciais.

- [ ] Celery + Redis (compose + config) — worker e beat
- [ ] Tasks: envio de e-mail (outbox), limpeza (retenção de logs/tmp), rotinas diárias
- [ ] Integração BrasilAPI CNPJ: client com timeout, retry, cache curto
- [ ] Notificações por e-mail em eventos-chave (ex.: aprovação/recusa)

**Entrega do dia:** Worker rodando; consulta CNPJ disponível; e-mails sendo despachados em dev.

---

## Dia 9 — Produção (S3, Gunicorn, Hardening, CI/CD)

**Objetivo:** Preparar e validar o deploy real.

- [ ] Storage prod: S3 via `django-storages`; URLs assinadas, tipos e limites
- [ ] Gunicorn + Uvicorn workers; `SECURE_*` (HSTS, CSP, etc.)
- [ ] Sentry habilitado em prod; níveis de log por ambiente
- [ ] GitHub Actions: lint, test, build; publicar artefatos (schema OpenAPI, por ex.)
- [ ] Variáveis de ambiente para prod (templates e secrets)

**Entrega do dia:** Build de produção ok; pipeline CI básico rodando.

---

## Dia 10 — Staging, Smoke Tests & Go‑Live

**Objetivo:** Hardening final e validação ponta‑a‑ponta.

- [ ] Provisionar staging (mesma infra da prod): Postgres, Redis, S3 (bucket dev)
- [ ] Migrar + seed mínimo; criar Admin; validar backoffice e fluxos críticos
- [ ] Smoke tests (postman/pytest e2e) nos principais endpoints
- [ ] Checklist de segurança: CORS restrito, headers, rate limit, rotação de tokens
- [ ] Observabilidade: health OK, Sentry recebendo eventos, logs JSON legíveis
- [ ] Plano de rollback e backups; Go‑Live

**Entrega do dia:** Release production‑ready validada em staging.

---

## ✅ Checklist Final de Prontidão (DoD)

- [ ] JWT + refresh rotation + blacklist; 2FA ativo para staff
- [ ] RBAC aplicado por viewset/ação; approvals idempotentes
- [ ] Clients e PER/DCOMPs com notas, anexos e auditoria
- [ ] Integração CNPJ funcionando com fallback/timeout
- [ ] Celery/Redis operacionais; e-mails enviados
- [ ] OpenAPI publicada; erros canônicos; testes passando
- [ ] Backoffice seguro (`/backoffice/`) com dashboards e fila de approvals
- [ ] Storage S3 em prod, URLs assinadas e limites de upload
- [ ] CI/CD (lint/test/build) ativo; smoke tests OK em staging
- [ ] Observabilidade: health, logs JSON, Sentry; políticas SECURE\_\* em prod

---

## 🧭 Dicas de Execução Diária

- No início de cada dia: abrir issues/tarefas curtas e branch específica
- Ao fim: PR pequeno, revisão rápida, merge para `main` + tag de versão (semver)
- Atualize `CHANGELOG.md` e publique schema OpenAPI a cada release
