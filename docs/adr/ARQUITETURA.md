# Arquitetura – Miele System

> Documento normativo das **escolhas de arquitetura** e **padrões** do backend.  
> Baseline: **Django 5.x + DRF**, **PostgreSQL**, **Redis** (opcional no MVP), **API-first**, modular por apps.

---

## 1. Princípios Orientadores

- **API-first**: contratos OpenAPI como fonte da verdade.
- **Modular por app**: baixa dependência, responsabilidades claras.
- **Simplicidade escalável**: Service Layer + ViewSets; sem DDD/CQRS pesados.
- **12-Factor**: configuração por ambiente via `.env`.
- **Segurança por padrão**: JWT + RBAC, CORS restrito, rate limit, headers seguros.
- **Observabilidade desde o início**: logs JSON, Sentry, health checks.
- **Qualidade contínua**: testes, linters, pre-commit, migrações pequenas e frequentes.

---

## 2. Estilo Arquitetural

### 2.1. Camadas (Lean)

- **Presentation (API)**: DRF ViewSets/Views, roteamento, schemas.
- **Application (Services/Use Cases)**: regras de orquestração (aprovações, validações cruzadas, side-effects).
- **Domain (Models + regras coesas)**: invariantes locais e validações do modelo.
- **Infrastructure (Adapters)**: e-mail, storage, auth, cache, fila, auditoria, integrações (CNPJ).

> **Motivação:** Mantém acoplamento baixo e curva técnica leve do Django, preservando clareza de fluxos sem a carga de DDD/CQRS completos.

### 2.2. Service Layer

- Casos de uso não triviais viram **Services** (`services/*.py`) com métodos idempotentes quando possível.
- **Transações** no nível do Service (atomic blocks).
- **Validações**:
  - Entrada: DRF serializers (request contracts)
  - Regras de negócio: Services/Models
- **Erros padronizados** (envelope de erro).

### 2.3. Repositório

- Utilização direta do ORM do Django nos Services.
- Repositório apenas para fontes externas ou mock de limites.

---

## 3. Decisões de Design

- **Autenticação:** `djangorestframework-simplejwt` com refresh rotation + blacklist.
- **Autorização:** Groups/Permissions nativos (RBAC) + `permissions.py` por recurso.
- **Aprovação de ações sensíveis:** padrão Command Request/Approve.
- **Auditoria:** tabelas dedicadas ligadas a entidades/usuários, imutáveis, com `correlation_id`.
- **Anexos:** `django-storages` (S3 em prod; local em dev). Nomeação determinística e varredura básica de tipo.
- **Integração CNPJ:** client HTTP simples (BrasilAPI) com timeout, retry e circuit breaker leve (cache curto).
- **Tasks assíncronas:** Celery + Redis (MVP se setup simples via compose). Fallback síncrono se indisponível.
- **Throttling/Rate limit:** DRF throttling + `django-ratelimit` em `/auth/*`.
- **Paginação:** `PageNumberPagination` padrão DRF.
- **OpenAPI:** `drf-spectacular` com exemplos e erros canônicos.

---

## 4. Fluxo de Request (Alto Nível)

1. Request → Middleware (X-Request-Id, segurança, logging estruturado)
2. Auth (JWT) → Permissions (RBAC)
3. ViewSet valida input (Serializer)
4. Service executa caso de uso (transação, models, integrações, storage, eventos/auditoria)
5. Serializer de saída (DTO de resposta)
6. Logger registra sucesso/erro + AuditLog se aplicável
7. Response com envelope de erro padronizado em falhas

---

## 5. Convenções de API

- **Versionamento:** `/api/v1/...`
- **Erros (envelope):**
  ```json
  {
    "error": {
      "code": "validation_error",
      "message": "Descrição curta do problema.",
      "details": { "campo": ["mensagem"] },
      "correlation_id": "uuid"
    }
  }
  ```
- **Filtros/Ordenação/Busca:** django-filter, OrderingFilter, SearchFilter.
- **Campos auditáveis:** sempre incluir `created_at`, `updated_at`, `deleted_at` (soft-delete quando aplicável).

---

## 6. Estrutura de Pastas (Base)

> Tudo que consta aqui existirá no repositório.

```text
backend/
    manage.py
    pyproject.toml
    Makefile
    docker-compose.yml
    Dockerfile
    .env.example
    core/
        asgi.py
        wsgi.py
        urls.py
        middleware.py
        settings/
            base.py
            dev.py
            prod.py
    common/
        utils/
            ids.py           # geração de UUID/correlation_id
            time.py
            validators.py
        email/
            sender.py        # abstração de envio (sync/async)
            templates/       # base templates
        storage/
            files.py         # wrapper django-storages/local
        audit/
            models.py        # AuditLog
            services.py      # gravação auditável
        observability/
            logging.py       # config de logs JSON
            health.py        # checks utilitários
        integrations/
            cnpj_client.py   # BrasilAPI client + retries/cache
    apps/
        identity/
            models.py
            serializers.py
            views.py
            services.py      # RegisterUser, ApproveUser, Login, etc.
            permissions.py
            urls.py
            tasks.py         # e-mails, etc. (Celery se habilitado)
            tests/
        clients/
            models.py
            serializers.py
            views.py
            services.py      # Create/Update + fluxo de aprovação
            permissions.py
            urls.py
            tasks.py
            tests/
        perdcomps/
            models.py
            serializers.py
            views.py
            services.py
            permissions.py
            urls.py
            tasks.py
            tests/
        admin_backoffice/
            views.py         # endpoints do backoffice
            services.py      # dashboards/consultas agregadas
            urls.py
            templates/       # (opcional) htmx/tailwind se usado
            tests/
    api/
        routers.py         # include urls das apps por namespace
        schemas/
            spectacular.py   # config drf-spectacular
    docs/
        adr/               # Architecture Decision Records
    scripts/
        load_demo_data.py
        cleanup_tmp.py
```

---

## 7. Configurações por Ambiente

- **core/settings/base.py:** DRF, JWT (simplejwt), CORS, throttle, logging JSON, Sentry (desabilitado por padrão).
- **dev.py:** Debug ON (restrito), DB local, storage local, e-mail console, throttle leve.
- **prod.py:** Debug OFF, S3, Sentry ON, CORS restrito, headers seguros (SECURE\_\*), SimpleJWT ajustado.

---

## 8. Segurança

- **JWT:** access curto (~15 min), refresh 7–14 dias, rotation + blacklist.
- **RBAC:** grupos/permissões por ViewSet/ação.
- **CORS:** apenas domínios do front.
- **Headers:** HSTS, X-Content-Type-Options, X-Frame-Options, etc.
- **Rate limit:** agressivo em `/auth/*`.
- **CSRF:** ativo para rotas web (se existirem templates).
- **Secrets:** .env/secret manager; nunca em VCS.

---

## 9. Observabilidade

- **Logs:** JSON no stdout; campos padrão: ts, level, logger, request_id, user_id, path, method, status, latency_ms.
- **Sentry:** exceções (Django + Celery).
- **Health:**
  - `/health/live` (app up)
  - `/health/ready` (DB/Storage/Redis ok)
- **Métricas (futuro):** Prometheus/Grafana.

---

## 10. Tarefas Assíncronas

- **Celery + Redis (MVP se compose simples):**
  - Fila: envio de e-mail, limpeza, pré-processamento de anexos.
  - Retries exponenciais e DLQ simples (log).
  - Fallback: se fila indisponível, e-mail pode cair para execução síncrona com timeouts.

---

## 11. Padrões de Dados & Migrações

- **IDs:** UUID públicos + PKs autoincrement no DB.
- **Soft-delete:** `deleted_at` nulo = ativo; querysets padrão filtrando removidos.
- **Migrações:** pequenas e frequentes; revisadas em PR; makemigrations por app.

---

## 12. Anexos & Storage

- **Dev:** filesystem local (pasta versionada fora do repo).
- **Prod:** S3 via django-storages.
- **Nomes de arquivo:** `{entidade}/{public_id}/{timestamp}_{slug}.{ext}`.
- **Políticas:** tamanho máximo, tipos permitidos, varredura básica (futuro: clamd).
- **Links:** URL assinada quando sensível.

---

## 13. Integrações

- **CNPJ (MVP):** client `common.integrations.cnpj_client`:
  - Timeout curto, retry com jitter, cache curto (ex.: 5–15 min).
  - Logs de requisição/resposta (sem dados sensíveis).
- **Receita Federal:** futuro.

---

## 14. Testes & Qualidade

- **pytest + pytest-django**
- **factory_boy/model_bakery** para factories.
- **Linters/Format:** ruff, black, isort.
- **pre-commit:** hooks de ruff/black/isort/mypy (mypy gradual opcional).
- **Cobertura:** serviços e permissões prioridade alta.

---

## 15. CI/CD & DevX

- **Makefile (exemplos):**
  - `make up` (compose up)
  - `make migrate` (migrações)
  - `make test` (pytest)
  - `make lint` (ruff/black/isort)
  - `make format` (black/isort)
- **GitHub Actions:**
  - Lint + Test + Build (deploy opcional).
  - OpenAPI: publicar schema estático a cada build (artefato).

---

## 16. Evolução & Multi-tenant (Futuro)

- Começo single-tenant com FK “cliente” nas entidades.
- Evolução: django-tenants se necessário → separar schema por tenant.
- Isolar `tenant_id` em claims JWT e nos querysets base.

---

## 17. Roteiro de Implementação (Ordem Sugerida)

1. Core + Settings + Observabilidade (logs, Sentry, health)
2. Identity (JWT, RBAC, aprovação de usuário, 2FA TOTP, rate/throttle)
3. Clients (CRUD + aprovação + anexos + auditoria)
4. PER/DCOMPs (CRUD + anexos + auditoria)
5. Admin BackOffice (dashboards/consultas)
6. Integração CNPJ (client resiliente)
7. Celery/Redis (e-mail assíncrono + limpezas)
8. Polish (OpenAPI, exemplos, envelopes de erro, documentação)
