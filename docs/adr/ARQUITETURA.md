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
- **Aprovação de ações sensíveis:** padrão Command Request/Approve via `common.approvals`.
- **Auditoria:** tabelas dedicadas ligadas a entidades/usuários, imutáveis, com `correlation_id` via `common.audit`.
- **Anexos:** Google Drive API (OAuth 2.0) com proxy transparente para upload/download. Nomeação determinística e validação de tipo via `common.services.google_drive`.
- **Integração CNPJ:** client HTTP simples (BrasilAPI) com timeout, retry e circuit breaker leve (cache curto) - **não implementado no MVP atual**.
- **Tasks assíncronas:** Processamento síncrono no MVP. Celery + Redis configurados nas dependências mas não ativos.
- **Throttling/Rate limit:** DRF throttling + `django-ratelimit` em `/auth/*`.
- **Paginação:** `PageNumberPagination` padrão DRF.
- **OpenAPI:** `drf-spectacular` com exemplos e erros canônicos.
- **Interface Admin:** Django Admin com tema `django-jazzmin` moderno.
- **Arquivos estáticos:** `whitenoise` para servir em produção.

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

## 6. Estrutura de Pastas (Implementada)

> Estrutura atual do repositório conforme implementação.

```text
miele-system/
    .env.example                 # template de variáveis (raiz do repo)
    Makefile                     # comandos de DX (lint/test/migrate/up)
    render.yaml                  # configuração deploy Render.com
    requirements/
        base.in                  # deps runtime (fonte)
        dev.in                   # deps de desenvolvimento (fonte)
        requirements.txt         # gerado por pip-compile
        requirements-dev.txt     # gerado por pip-compile
    docker-compose.yml           # serviços (web, db) — raiz
    Dockerfile                   # imagem da app — raiz
    docs/
        adr/                     # Architecture Decision Records
        db/                      # database schema e diagramas
        DEPLOYMENT.md            # guia de deploy
        GIT-WORKFLOW.md          # workflow de desenvolvimento
    scripts/
        audit_approval_examples.py
    backend/
        manage.py
        core/
            asgi.py
            wsgi.py
            urls.py              # roteamento principal
            middleware.py        # correlation ID, failed login tracking
            settings/
                base.py          # configurações base
                dev.py           # desenvolvimento
                prod.py          # produção
        common/
            utils/
                ids.py           # geração de UUIDs
                time.py          # utilitários de data/hora
                validators.py    # validadores customizados
                approvals.py     # lógica de aprovação
            services/
                google_drive.py  # integração Google Drive API
            audit/               # sistema de auditoria
                models.py        # AuditLog
                services.py      # lógica de auditoria
                admin.py         # interface admin
                urls.py, views.py
            approvals/           # sistema de aprovações
                models.py        # ApprovalRequest
                services.py      # lógica de aprovação
                mixins.py        # mixins para ViewSets
                admin.py
            shared/              # modelos compartilhados
                models.py        # Annotation, AttachedFile
                admin.py         # admin com inlines
                urls.py, views.py
            observability/
                logging.py       # configuração de logs JSON
                health.py        # endpoints de health check
            permissions.py       # permissões customizadas
        apps/
            identity/            # autenticação e usuários
                models.py        # User customizado
                views.py         # auth, profile, TOTP
                serializers.py
                permissions.py
                urls/            # auth.py, users.py, admin.py
                admin.py
                management/      # comandos de setup
            clients/             # gestão de clientes
                models.py        # Client, Address
                views.py         # CRUD com aprovações
                serializers.py
                services.py
                urls.py, urls_dashboard.py
                admin.py
            perdcomps/           # documentos tributários
                models.py        # PerDcomp
                views.py         # CRUD com aprovações
                serializers.py
                services.py
                urls.py
                admin.py
        api/
            routers.py           # roteamento centralizado
            schemas/
                spectacular.py   # configuração OpenAPI
        integration/
            google-drive/        # credenciais OAuth (não versionadas)
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

- **Status MVP:** Processamento síncrono para simplificar implementação inicial.
- **Dependências configuradas:** Celery + Redis estão em `requirements/base.in` mas não ativos.
- **Planejamento futuro:**
  - Fila: envio de e-mail, limpeza, pré-processamento de anexos.
  - Retries exponenciais e DLQ simples (log).
  - Fallback: se fila indisponível, operações podem executar de forma síncrona com timeouts.
- **Comandos de management:** Limpeza via Django management commands.

---

## 11. Padrões de Dados & Migrações

- **IDs:** UUID públicos + PKs autoincrement no DB.
- **Soft-delete:** `deleted_at` nulo = ativo; querysets padrão filtrando removidos.
- **Migrações:** pequenas e frequentes; revisadas em PR; makemigrations por app.

---

## 12. Anexos & Storage

- **Dev:** Google Drive API (mesma implementação de prod para consistência).
- **Prod:** Google Drive API via OAuth 2.0 com proxy transparente implementado em `common.services.google_drive`.
- **Nomes de arquivo:** `{entity_type}/{public_id}/{timestamp}_{original_filename}.{ext}`.
- **Políticas:** tamanho máximo (100MB default), tipos permitidos, validação de MIME type.
- **Links:** Proxy transparente via API interna (`/api/v1/shared/files/{id}/download/`) sem exposição de URLs do Google Drive.
- **Configuração:** Via variáveis de ambiente (client_id, client_secret, refresh_token, folder_ids).
- **Pasta structure:** Pastas separadas por tipo de entidade (clients, perdcomps) no Google Drive.

---

## 13. Integrações

- **Google Drive (implementado):** client `common.services.google_drive`:
  - OAuth 2.0 com refresh token automático.
  - Timeout configurado, handling de erros HTTP.
  - Upload/download via proxy transparente.
  - Logs de requisição/resposta (sem dados sensíveis).
- **CNPJ (planejado):** client HTTP para validação externa:
  - Timeout curto, retry com jitter, cache curto (ex.: 5–15 min).
  - Não implementado no MVP atual.
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
