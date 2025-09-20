# README – Miele System

## 📌 Visão Geral

O **Miele System** é um software de **gestão empresarial** desenvolvido pela Compasse, com foco em **Clientes** e **PER/DCOMPs** (documentos tributários).  
Ele adota uma abordagem **API-first**, com backend em **Django 5.x + DRF** e interfaces administrativas em **Django Admin Backoffice**.

- **Autenticação/Autorização:** JWT (com refresh rotation + blacklist), RBAC por grupos/permissões, suporte a 2FA TOTP.
- **Segurança por padrão:** CORS restrito, rate limit, headers seguros.
- **Observabilidade:** logs estruturados em JSON, auditoria detalhada, health checks e integração com Sentry.
- **Arquitetura modular:** separação clara em apps (`identity`, `clients`, `perdcomps`, `admin_backoffice`).

---

## 📂 Estrutura de Documentação

Toda a documentação oficial encontra-se na pasta [`/docs`](./docs):

- **[ESCOPO.md](./docs/adr/ESCOPO.md):** Função, usuários, contextos principais, integrações externas e foco do projeto.
- **[ARQUITETURA.md](./docs/adr/ARQUITETURA.md):** Princípios, camadas, decisões de design, fluxos de request, convenções de API, segurança e observabilidade.
- **[ENDPOINTS.md](./docs/adr/ENDPOINTS.md):** Lista completa de rotas REST (usuários, clientes, PER/DCOMPs e administração).
- **[ADMIN.md](./docs/adr/ADMIN.md):** Especificações do Django Admin Backoffice, papéis de acesso, segurança e UX.
- **[USE-CASES.md](./docs/adr/USE-CASES.md):** Casos de uso, matriz de acesso, ciclos de vida das entidades e fluxos end-to-end.
- **Banco de Dados:**
  - [miele-system-db.md](./docs/db/md/miele-system-db.md) – Guia de tabelas customizadas.
  - [miele-system-db.dbml](./docs/db/miele-system-db.dbml) – Definição DBML.
  - [miele-system-db.sql](./docs/db/miele-system-db.sql) – Script SQL.
  - [miele-system-db.png](./docs/db/img/miele-system-db.png) – Diagrama visual.

---

## 🏗️ Escopo Resumido

Segundo [ESCOPO.md](./docs/adr/ESCOPO.md):

- **Identity:** Autenticação JWT, refresh rotation + blacklist, RBAC, 2FA, soft-delete, rate limiting.
- **Clients:** Ciclo de vida completo, requests de aprovação para alterações sensíveis, anexos, notas, auditoria.
- **PER/DCOMPs:** Gestão de documentos tributários vinculados a clientes, anexos, notas e auditoria.
- **Admin Backoffice:** Dashboards, aprovações de usuários e requests, logs de auditoria.
- **Integrações:** Consulta CNPJ via BrasilAPI no MVP.
- **Observabilidade:** logs estruturados, Sentry, health checks (`/health/live`, `/health/ready`).
- **Tarefas assíncronas:** Celery + Redis para e-mails e jobs de limpeza.

---

## 🛠️ Comandos de Gerenciamento

O sistema possui comandos Django personalizados para facilitar a configuração e administração:

### 🔑 Criação de Superusuário com Roles

```bash
# Modo interativo (recomendado)
python manage.py create_superuser_with_role

# Modo não-interativo
python manage.py create_superuser_with_role \
    --username admin \
    --email admin@miele.com \
    --first-name "Admin" \
    --last-name "System" \
    --role admin \
    --password "senha_segura" \
    --no-input
```

**Opções disponíveis:**

- `--username`: Nome de usuário
- `--email`: Email do usuário
- `--first-name`: Primeiro nome
- `--last-name`: Sobrenome
- `--role`: Role do usuário (`admin`, `employee`, `guest`)
- `--password`: Senha (se não fornecida, será solicitada)
- `--no-input`: Não solicitar entrada interativa

### 🎭 Configuração de Roles e Permissões

```bash
# Configurar roles do sistema
python manage.py setup_roles

# Reset e reconfiguração completa
python manage.py setup_roles --reset --verbose
```

**Roles criadas:**

- **Admin**: Acesso completo ao sistema com privilégios administrativos
- **Employee**: Acesso padrão para operações de negócio
- **Guest**: Acesso limitado apenas para visualização de dados públicos

### 🔄 Migração de Usuários Existentes

```bash
# Visualizar o que seria migrado
python manage.py migrate_users --dry-run

# Migrar usuários com role padrão
python manage.py migrate_users --default-role employee

# Migrar e aprovar automaticamente
python manage.py migrate_users --auto-approve
```

**Opções disponíveis:**

- `--dry-run`: Mostra o que seria feito sem fazer alterações
- `--default-role`: Role padrão para usuários sem role explícita
- `--auto-approve`: Aprova automaticamente usuários migrados

---

## 🧩 Arquitetura e Padrões

Conforme [ARQUITETURA.md](./docs/adr/ARQUITETURA.md):

- **Camadas:** Presentation (API), Application (Services/Use Cases), Domain (Models), Infrastructure (adapters).
- **Service Layer:** Casos de uso encapsulados em serviços, com atomicidade e validações.
- **Autorização:** RBAC via grupos/permissões do Django.
- **Auditoria:** Tabelas dedicadas, imutáveis, com correlation_id.
- **Anexos:** `django-storages` (S3 em produção, local em dev).
- **Integrações:** Cliente HTTP resiliente para BrasilAPI (CNPJ).
- **Qualidade:** pytest, factory_boy/model_bakery, ruff, black, isort, pre-commit.

---

## 🗄️ Banco de Dados

Esquema detalhado em [miele-system-db.md](./docs/db/md/miele-system-db.md).

### Principais Tabelas Customizadas

- `identity_user`: Usuários com aprovação, suspensão, soft-delete.
- `clients` + `client_address`: Gestão de clientes e endereço único.
- `perdcomps`: Documentos tributários vinculados a clientes.
- `app_notes`: Anotações por usuário ligadas a entidades.
- `app_files`: Uploads e anexos com owner/kind/backend.
- `app_approval_requests`: Requests de aprovação (user, client, perdcomp).
- `audit_log`: Registro imutável de auditoria.

Enums suportam status e fluxos (ex.: `user_approval_status`, `client_status`, `request_status`, `file_owner`, `file_kind`).

---

## 🌐 Endpoints

Listados em [ENDPOINTS.md](./docs/adr/ENDPOINTS.md).

### Exemplos

- **Auth:** `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`
- **Usuário:** `/api/v1/users/me`
- **Clientes:** `/api/v1/clients`, `/api/v1/clients/{id}`, `/api/v1/clients/{id}/requests/sensitive-update`
- **PER/DCOMPs:** `/api/v1/perdcomps`, `/api/v1/clients/{id}/perdcomps`
- **Admin:** `/api/v1/admin/users`, `/api/v1/admin/requests`, `/api/v1/admin/logs`

---

## ⚙️ Casos de Uso

Definidos em [USE-CASES.md](./docs/adr/USE-CASES.md):

- Login e sessão segura (JWT + refresh).
- Atualização de perfil.
- Cadastro e gestão de clientes.
- Alteração sensível de CNPJ via request/approval.
- Gestão de PER/DCOMPs com anexos.
- Aprovação/recusa de requests.

Cada entidade possui **ciclo de vida formalizado** (User, Client, PER/DCOMP, Request, File).

---

## 🖥️ Admin Backoffice

Definido em [ADMIN.md](./docs/adr/ADMIN.md):

- **URL base:** `/backoffice/` (não `/admin/`).
- **Autenticação:** Session + 2FA TOTP obrigatório.
- **Papéis:** Admin, Approver, Auditor, Operator.
- **Funcionalidades:** Dashboards, fila de approvals, logs de auditoria, gestão de usuários, clientes e PER/DCOMPs.
- **Segurança extra:** lockout após falhas, reautenticação para ações sensíveis, CSP restritiva.

---

## 🛠️ Tecnologias

- **Backend:** Python 3.11+, Django 5.x, Django REST Framework.
- **Banco:** PostgreSQL.
- **Cache/Queue:** Redis (cache, throttling, Celery).
- **Asynchronous:** Celery + Redis.
- **Storage:** Local (dev), AWS S3 (prod).
- **Email:** SMTP ou Anymail.
- **Infra:** Docker + docker-compose.
- **Observabilidade:** Logs JSON, Sentry, health checks.
- **Docs:** OpenAPI (drf-spectacular).

---

## 🚀 Execução Básica

1. Clone o repositório:

   ```bash
   git clone <repo-url>
   cd miele-system
   ```

2. Crie um `.env` baseado em `.env.example`.

3. Suba os serviços com Docker Compose:

   ```bash
   make up
   ```

4. Execute migrações e testes:
   ```bash
   make migrate
   make test
   ```

---

## 📜 Licença

Este software é **proprietário** e de uso **interno**.  
Não são aceitas contribuições externas (pull requests).
