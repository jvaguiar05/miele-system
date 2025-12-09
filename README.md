# Miele System Backend

Sistema de **gestão empresarial** especializado em clientes e documentos tributários (PER/DCOMP), desenvolvido em **Django 5.x + DRF** com arquitetura **API-first**, oferecendo autenticação robusta, sistema de aprovações, auditoria completa e interface administrativa moderna.

## 📋 Roadmap de Navegação

### 📊 **Para Gestores e Executivos**

- [🎯 Visão Geral do Produto](#-visão-geral-do-produto) - Por que existe e qual o valor
- [🌟 Showcase de Funcionalidades](#-showcase-de-funcionalidades) - Demonstração das capacidades
- [💼 Benefícios Executivos](#-benefícios-executivos) - Valor por cargo (CFO, Head Fiscal, CTO)

### 👨‍💻 **Para Desenvolvedores**

- [🚀 Tecnologias](#-tecnologias) - Stack completo e dependências
- [🏗️ Arquitetura](#️-arquitetura) - Padrões de design e estrutura modular
- [📋 Funcionalidades Principais](#-funcionalidades-principais) - Features técnicas detalhadas
- [🔧 Configuração de Desenvolvimento](#-configuração-de-desenvolvimento) - Setup local
- [📚 Documentação Técnica](#-documentação-técnica) - ADRs e referências

### 🚀 **Para DevOps e Infraestrutura**

- [🏭 Configuração de Produção](#-configuração-de-produção) - Deploy e variáveis
- [🔍 Monitoramento & Debugging](#-monitoramento--debugging) - Health checks e logs
- [📈 Comandos de Gerenciamento](#-comandos-de-gerenciamento) - Setup e manutenção

### 👤 **Sobre o Projeto**

- [👤 Sobre o Desenvolvedor](#-sobre-o-desenvolvedor) - Contato e informações

---

## 🎯 Visão Geral do Produto

### Por que o Miele System Backend foi criado?

O Miele System Backend nasceu da necessidade de **modernizar e centralizar** a gestão de clientes e documentos tributários (PER/DCOMP) para empresas de contabilidade e consultorias fiscais. Tradicionalmente, esses processos eram gerenciados através de:

- **Planilhas dispersas** e sistemas legados desconectados
- **Falta de auditoria** e rastreabilidade de mudanças
- **Aprovações manuais** sem workflow estruturado
- **Armazenamento inseguro** de documentos sensíveis
- **Ausência de controle de acesso** granular por usuário

O Miele resolve esses problemas oferecendo uma **API robusta e escalável** que centraliza toda a operação em uma plataforma **segura, auditável e moderna**.

### Valor para o Negócio

- **🔒 Segurança Corporativa**: Autenticação JWT + 2FA, RBAC granular, auditoria completa
- **⚡ Eficiência Operacional**: APIs RESTful para integração, workflow de aprovações automatizado
- **📊 Rastreabilidade Total**: Logs imutáveis de auditoria com correlation IDs
- **🌐 Escalabilidade**: Arquitetura modular preparada para crescimento
- **🛡️ Compliance**: Headers de segurança, CORS restrito, soft-delete para retenção

### Público-Alvo

- **Equipes de TI Corporativas** - Empresas que precisam de backend confiável para gestão fiscal
- **Desenvolvedores Frontend** - Integração com React, Vue, Angular via APIs REST
- **Escritórios de Contabilidade** - Gestão centralizada de múltiplos clientes
- **Consultorias Tributárias** - Controle detalhado de documentos e processos

---

## 🌟 Showcase de Funcionalidades

### 🔐 Sistema de Autenticação Enterprise

**Segurança multicamadas para ambiente corporativo**

- **JWT Authentication** com refresh rotation automática e blacklist de tokens
- **2FA TOTP** obrigatório via Google Authenticator ou apps compatíveis
- **RBAC granular** com roles Admin, Employee, Guest e permissões específicas
- **Rate limiting** agressivo em endpoints de auth para prevenir ataques
- **Failed login tracking** com bloqueio temporário automático

### 🏢 Gestão Empresarial Completa

**Central unificada para clientes corporativos**

- **Base de clientes** com dados empresariais completos (CNPJ, razão social, natureza jurídica)
- **Endereços integrados** com criação automática e validação
- **Soft delete** para retenção de dados históricos e compliance
- **Sistema de anotações** individual por usuário com controle de visibilidade
- **Upload de arquivos** via Google Drive API com proxy transparente
- **Busca avançada** por CNPJ, razão social, status e período

### 📊 Motor de Documentos Tributários

**Gestão completa de PER/DCOMPs**

- **Vinculação automática** cliente-documento com validação de CNPJ
- **Controle de status** completo (rascunho, transmitido, processado, deferido)
- **Campos tributários** especializados: números, protocolos, valores, competências
- **Anotações contextuais** por documento para observações técnicas
- **Anexos específicos** com categorização por tipo de documento
- **Auditoria detalhada** de todas as alterações com timestamp

### ⚖️ Sistema de Aprovações

**Workflow empresarial para mudanças sensíveis**

- **Approval requests** automáticas para alterações de campos críticos
- **Diferenciação de permissões**: Employees criam requests, Admins aprovam diretamente
- **Justificativas obrigatórias** para aprovações e recusas
- **Timeline completa** de aprovações com histórico de decisões
- **Notificações de status** para solicitantes e aprovadores

### 🔍 Auditoria e Observabilidade

**Rastreabilidade total para compliance corporativo**

- **Logs imutáveis** de todas as operações CUD (Create, Update, Delete)
- **Correlation IDs** para rastreamento de requests end-to-end
- **Metadados completos**: usuário, IP, timestamp, ação, payload before/after
- **Health checks** para monitoramento de infraestrutura (`/health/live`, `/health/ready`)
- **Logs estruturados JSON** para integração com ferramentas de observabilidade

### 🛠️ Interface Administrativa Moderna

**Django Admin turbinado para gestão operacional**

- **Tema django-jazzmin** moderno e responsivo
- **Dashboards especializados** por domínio (Identity, Clients, PER/DCOMPs)
- **Filtros avançados** por status, período, tipo de entidade
- **Inlines automáticos** para anotações e arquivos em todas as entidades
- **Actions personalizadas** para aprovações em lote
- **Display formatado** para campos JSON e metadados complexos

### 🌐 APIs REST Completas

**Integração perfeita para frontends modernos**

- **OpenAPI/Swagger** com documentação viva e exemplos
- **Versionamento de API** com namespace `/api/v1/`
- **Filtros DRF** padronizados com paginação e ordenação
- **Lookup por UUID** (public_id) em todas as entidades
- **Error handling** padronizado com correlation IDs
- **CORS configurável** para ambientes de desenvolvimento e produção

---

## 💼 Benefícios Executivos

### Para o CFO (Chief Financial Officer)

- **Controle de Custos**: Infraestrutura otimizada com Google Drive (sem custos de S3) e Render.com (PaaS eficiente)
- **Compliance Financeiro**: Auditoria completa para atender exigências de SOX e regulamentações locais
- **ROI Mensurável**: Redução de custos operacionais com automação de workflows manuais
- **Visibilidade de Processos**: APIs que alimentam dashboards executivos com métricas de performance fiscal

### Para o Head de TI / CTO

- **Arquitetura Moderna**: Django 5.x + DRF, PostgreSQL, deploy em container Docker
- **Segurança por Design**: JWT + 2FA, RBAC, headers seguros, rate limiting nativo
- **Escalabilidade**: Arquitetura modular preparada para crescimento e novas funcionalidades
- **Observabilidade**: Logs estruturados, health checks, correlation IDs para debugging
- **Integração Fácil**: APIs RESTful padronizadas com OpenAPI para frontends React/Vue/Angular

### Para o Responsável pela Segurança da Informação

- **Autenticação Multicamadas**: JWT + refresh rotation + 2FA TOTP obrigatório
- **Controle de Acesso Granular**: RBAC com permissões específicas por recurso e ação
- **Auditoria Imutável**: Logs de todas as ações com rastreabilidade completa
- **Proteção de Dados**: Soft delete para retenção, proxy para Google Drive sem exposição de URLs
- **Compliance LGPD**: Estrutura preparada para proteção de dados pessoais

### Para o Head Fiscal / Operações

- **Workflow de Aprovações**: Sistema estruturado para mudanças sensíveis em dados fiscais
- **Rastreabilidade Total**: Histórico completo de alterações em clientes e documentos PER/DCOMP
- **Produtividade da Equipe**: Interface administrativa moderna reduz tempo de operações manuais
- **Qualidade de Dados**: Validações automáticas e sistema de anotações para controle de qualidade

---

## 🚀 Tecnologias

### Stack Backend Principal

- **Django 5.x** - Framework web Python com ORM robusto
- **Django REST Framework (DRF) 3.15+** - APIs REST com serialização, paginação e filtros
- **PostgreSQL 15+** - Banco de dados relacional para produção
- **Python 3.11+** - Linguagem com typing estático e performance otimizada

### Autenticação & Segurança

- **djangorestframework-simplejwt 5.3+** - JWT authentication com refresh rotation
- **django-otp 1.4+** - 2FA TOTP via Google Authenticator
- **django-ratelimit 4.1+** - Rate limiting para proteção de endpoints
- **django-cors-headers 4.4+** - Configuração CORS para frontends

### Armazenamento & Integração

- **google-api-python-client 2.0+** - Integração Google Drive API
- **google-auth-oauthlib 1.0+** - OAuth 2.0 flow com refresh tokens
- **psycopg[binary] 3.2+** - Driver PostgreSQL otimizado
- **whitenoise 6.6+** - Servidor de arquivos estáticos

### Documentação & API

- **drf-spectacular 0.27+** - OpenAPI/Swagger schema generation
- **django-filter 24.2+** - Filtros avançados para APIs
- **django-jazzmin 3.0+** - Tema moderno para Django Admin

### Infraestrutura & Deploy

- **gunicorn 22.0+** - WSGI server para produção
- **uvicorn[standard] 0.30+** - ASGI workers para performance
- **dj-database-url 2.1+** - Configuração de banco via URL
- **docker + docker-compose** - Containerização para desenvolvimento

### Observabilidade (Configurado)

- **sentry-sdk 2.8+** - Error tracking (opcional via SENTRY_DSN)
- **django-prometheus 2.3+** - Métricas de performance (futuro)

### Preparado para Escala (Não ativo no MVP)

- **celery 5.4+** - Tasks assíncronas (configurado, não ativo)
- **redis 5.0+** - Cache e message broker (configurado, não ativo)

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

## 🏗️ Arquitetura

### Padrões de Design

- **API-First Architecture** - Contratos OpenAPI como fonte da verdade
- **Modular App Design** - Separação clara de responsabilidades (`identity`, `clients`, `perdcomps`, `common`)
- **Service Layer Pattern** - Lógica de negócio em services com transações atômicas
- **Repository Pattern** - Abstração de dados via ORM Django com querysets otimizados
- **Command/Request Pattern** - Aprovações via `ApprovalRequest` model

### Estrutura Modular

```
backend/
├── apps/                    # Domínios de negócio
│   ├── identity/           # Autenticação, usuários, RBAC
│   ├── clients/            # Gestão de clientes e endereços
│   ├── perdcomps/          # Documentos tributários PER/DCOMP
│   └── admin_backoffice/   # Dashboards administrativos
├── common/                  # Módulos compartilhados
│   ├── audit/              # Sistema de auditoria
│   ├── approvals/          # Workflow de aprovações
│   ├── shared/             # Models compartilhados (Annotation, File)
│   ├── services/           # Integrações (Google Drive)
│   ├── observability/      # Logs, health checks
│   └── utils/              # Utilitários (IDs, validadores)
├── core/                    # Configurações Django
│   ├── settings/           # Por ambiente (base, dev, prod)
│   ├── middleware.py       # Correlation ID, failed login
│   └── urls.py             # Roteamento principal
└── api/                     # Camada de API
    ├── routers.py          # Roteamento centralizado
    └── schemas/            # OpenAPI configuration
```

### Segurança por Camadas

- **Network Level**: CORS restrito, headers seguros (HSTS, CSP)
- **Authentication**: JWT + 2FA TOTP obrigatório
- **Authorization**: RBAC granular com Django Groups/Permissions
- **Application**: Rate limiting, validação de inputs, soft delete
- **Data**: Auditoria imutável, correlation IDs, proxy para storage

### Padrões de API

- **RESTful Design** - Recursos com CRUD completo via ViewSets
- **Lookup por UUID** - `public_id` em todas as entidades (não IDs sequenciais)
- **Error Handling** - Envelopes padronizados com correlation IDs
- **Paginação** - `PageNumberPagination` com filtros DRF
- **Versionamento** - Namespace `/api/v1/` para evolução controlada

---

## 🗄️ Banco de Dados

Esquema detalhado em [miele-system-db.md](./docs/db/md/miele-system-db.md).

### Principais Tabelas Customizadas

- `identity_user`: Usuários com aprovação, suspensão, soft-delete.
- `clients` + `client_address`: Gestão de clientes e endereço único.
- `perdcomps`: Documentos tributários vinculados a clientes.
- `app_notes`: Anotações por usuário ligadas a entidades (via ContentTypes).
- `app_files`: Uploads e anexos com metadados e referência para Google Drive.
- `app_approval_requests`: Requests de aprovação (user, client, perdcomp).
- `audit_log`: Registro imutável de auditoria.

Enums suportam status e fluxos (ex.: `user_approval_status`, `client_status`, `request_status`, `file_type`).

---

## 🌐 Endpoints

Listados em [ENDPOINTS.md](./docs/adr/ENDPOINTS.md).

### Exemplos

- **Auth:** `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`
- **Usuário:** `/api/v1/users/me`
- **Clientes:** `/api/v1/clients`, `/api/v1/clients/{id}`, `/api/v1/clients/{id}/requests/sensitive-update`
- **PER/DCOMPs:** `/api/v1/perdcomps`, `/api/v1/clients/{id}/perdcomps`
- **Admin:** `/api/v1/admin/users`, `/api/v1/admin/requests`, `/api/v1/admin/logs`
- **Arquivos:** `/api/v1/files/` (proxy para Google Drive)

---

## ⚙️ Casos de Uso

Definidos em [USE-CASES.md](./docs/adr/USE-CASES.md):

- Login e sessão segura (JWT + refresh).
- Atualização de perfil.
- Cadastro e gestão de clientes.
- Alteração sensível de CNPJ via request/approval.
- Gestão de PER/DCOMPs com anexos.
- Aprovação/recusa de requests.
- Upload/download de arquivos via Google Drive.

Cada entidade possui **ciclo de vida formalizado** (User, Client, PER/DCOMP, Request, File).

---

## 🖥️ Admin Backoffice

Definido em [ADMIN.md](./docs/adr/ADMIN.md):

- **URL base:** `/admin/` (Django Admin padrão).
- **Tema:** **django-jazzmin** com interface moderna e responsiva.
- **Autenticação:** Session auth integrada com sistema de usuários.
- **Papéis:** Admin, Approver, Auditor, Operator.
- **Funcionalidades:** 
  - Gestão de usuários com aprovações em lote
  - Fila de aprovações para mudanças sensíveis
  - Logs de auditoria com visualização JSON formatada
  - Gestão de clientes e PER/DCOMPs com inlines para notas e anexos
- **Segurança:** Permissões baseadas em grupos, logs de todas as ações.

---

## 🛠️ Tecnologias Implementadas

### Backend
- **Python 3.11+**, **Django 5.x**, **Django REST Framework**
- **PostgreSQL** (produção), **SQLite** (desenvolvimento)
- **Google Drive API** (OAuth 2.0) para armazenamento de arquivos
- **django-jazzmin** para interface administrativa moderna
- **WhiteNoise** para servir arquivos estáticos
- **JWT Authentication** com refresh rotation e blacklist

### Infraestrutura
- **Docker + docker-compose** para ambiente local
- **Render.com** configurado para deploy automático
- **Health checks** para monitoramento (`/health/live`, `/health/ready`)
- **Logs JSON estruturados** para observabilidade

### Documentação e API
- **OpenAPI/Swagger** via drf-spectacular
- **Documentação viva** com exemplos e schemas detalhados

---

## 🔧 Configuração de Desenvolvimento

### Pré-requisitos

- **Python 3.11+** instalado
- **Docker + Docker Compose** (recomendado)
- **PostgreSQL** (local ou via Docker)
- **Google Cloud Console** - Projeto com Drive API habilitada

### Instalação

```bash
# Clone o repositório
git clone <repo-url>
cd miele-system

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas configurações
```

### Configuração do Google Drive (necessário para arquivos)

- Configure OAuth 2.0 no Google Cloud Console
- Adicione as credenciais no `.env`:
  ```env
  GDRIVE_CLIENT_ID=your_client_id
  GDRIVE_CLIENT_SECRET=your_client_secret  
  GDRIVE_REFRESH_TOKEN=your_refresh_token
  GDRIVE_CLIENTS_FOLDER_ID=folder_id_for_clients
  GDRIVE_PERDCOMPS_FOLDER_ID=folder_id_for_perdcomps
  ```

### Inicialização Rápida

```bash
# Inicie os serviços
make up

# Execute migrações e configuração inicial
make migrate
make setup-roles
make superuser  # ou use create_superuser_with_role
```

### Acesso à Aplicação

- **API:** http://localhost:8000/api/docs/
- **Admin:** http://localhost:8000/admin/
- **Health:** http://localhost:8000/health/live

### Comandos Úteis

```bash
# Executar aplicação local
make run

# Executar testes
make test

# Aplicar migrações
make migrate

# Criar superusuário
make superuser

# Linting e formatação
make lint
make fmt

# Docker
make up     # Subir containers
make down   # Parar containers
make logs   # Ver logs
```

---

---

## 🏭 Configuração de Produção

### Variáveis de Ambiente Essenciais

```env
# Aplicação
DEBUG=false
SECRET_KEY=seu-secret-key-seguro
ALLOWED_HOSTS=seu-dominio.com

# Banco de dados
DATABASE_URL=postgres://user:pass@host:port/dbname

# Google Drive
GDRIVE_CLIENT_ID=your_google_client_id
GDRIVE_CLIENT_SECRET=your_google_client_secret
GDRIVE_REFRESH_TOKEN=your_refresh_token
GDRIVE_CLIENTS_FOLDER_ID=your_clients_folder_id
GDRIVE_PERDCOMPS_FOLDER_ID=your_perdcomps_folder_id

# Segurança
CORS_ALLOWED_ORIGINS=https://seu-frontend.com
SECURE_SSL_REDIRECT=true
```

### Deploy no Render.com

O projeto está configurado para deploy automático no Render.com:

1. Conecte seu repositório ao Render
2. Configure as variáveis de ambiente no dashboard
3. O deploy será automático a cada push na branch `develop`

Consulte [DEPLOYMENT.md](./docs/DEPLOYMENT.md) para instruções detalhadas.

---

## 🔍 Monitoramento & Debugging

### Health Checks

- **`/health/live`** - Verifica se a aplicação está rodando
- **`/health/ready`** - Verifica aplicação + dependências (DB, Google Drive)

### Logs Estruturados

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "logger": "django.request",
  "message": "Request completed",
  "request_id": "req-123",
  "user_id": "user-456", 
  "method": "POST",
  "path": "/api/v1/clients/",
  "status": 201,
  "latency_ms": 45
}
```

### Correlation IDs

Todas as requisições recebem um `X-Request-ID` automático para rastreamento end-to-end em logs e audit trails.

### Error Tracking

- **Sentry** configurado (ativar via `SENTRY_DSN`)
- **Audit Logs** para todas as operações CUD
- **Failed Login Tracking** com bloqueio automático

---

## 🔧 Features Principais

### ✅ Implementadas

- **Autenticação JWT** com refresh rotation e blacklist
- **Sistema de aprovações** para mudanças sensíveis
- **Google Drive Integration** para armazenamento de arquivos
- **Django Admin** com tema Jazzmin moderno
- **Sistema de auditoria** completo e imutável  
- **API REST** completa com documentação OpenAPI
- **Health checks** para monitoramento
- **Logs estruturados** em JSON
- **Sistema de roles** e permissões (RBAC)
- **Soft delete** para entidades principais

### 📝 Notas sobre Features Removidas

Durante o desenvolvimento, algumas features planejadas foram removidas ou substituídas:

- **~~Redis/Celery~~**: Removidos para simplificar MVP (dependências ainda presentes mas não configuradas)
- **~~Sentry~~**: Configurado mas não ativo (pode ser habilitado via `SENTRY_DSN`)
- **~~AWS S3~~**: Substituído pela integração Google Drive API
- **~~Email SMTP~~**: Removido do MVP (pode ser adicionado posteriormente)

---

## 📜 Licença

Este software é **proprietário** e de uso **interno**.  
Não são aceitas contribuições externas (pull requests).

---

## 🤝 Desenvolvimento

### Workflow de Git

- `main`: Produção (releases estáveis)
- `develop`: Staging/Desenvolvimento (integração contínua) 
- `develop/feature-*`: Features em desenvolvimento

Consulte [GIT-WORKFLOW.md](./docs/GIT-WORKFLOW.md) para detalhes do processo.

### Estrutura do Projeto

```
miele-system/
├── backend/           # Aplicação Django
│   ├── core/         # Configurações principais
│   ├── apps/         # Apps Django (identity, clients, perdcomps)
│   ├── common/       # Módulos compartilhados
│   └── scripts/      # Scripts de utilidade
├── docs/             # Documentação detalhada
├── requirements/     # Dependências Python
├── docker-compose.yml
├── Dockerfile
├── render.yaml       # Configuração Render.com
└── Makefile         # Comandos de desenvolvimento
```

---

## 📚 Documentação Técnica

### Documentação Oficial

Toda a documentação oficial encontra-se na pasta [`/docs`](./docs):

- **[ESCOPO.md](./docs/adr/ESCOPO.md)** - Função, usuários, contextos principais e foco do projeto
- **[ARQUITETURA.md](./docs/adr/ARQUITETURA.md)** - Princípios, camadas, decisões de design e padrões
- **[ENDPOINTS.md](./docs/adr/ENDPOINTS.md)** - Lista completa de rotas REST com exemplos
- **[ADMIN.md](./docs/adr/ADMIN.md)** - Especificações do Django Admin Backoffice
- **[DEPLOYMENT.md](./docs/DEPLOYMENT.md)** - Guia completo de deploy no Render.com
- **[GIT-WORKFLOW.md](./docs/GIT-WORKFLOW.md)** - Estratégia de branches e workflow

### Banco de Dados

- **[Guia Completo](./docs/db/md/miele-system-db.md)** - Tabelas, relacionamentos e exemplos
- **[Schema DBML](./docs/db/miele-system-db.dbml)** - Definição estruturada
- **[Diagrama Visual](./docs/db/img/miele-system-db.png)** - ERD completo

### Integração com APIs

- **OpenAPI/Swagger** - Documentação viva em `/api/docs/`
- **Schemas de Request/Response** - Exemplos completos com validação
- **Authentication Flow** - JWT + 2FA implementação completa
- **Error Handling** - Padronização de erros com correlation IDs

### Padrões de Código

- **Django Best Practices** - Structure, naming, patterns
- **DRF Standards** - ViewSets, serializers, permissions
- **Security Guidelines** - Authentication, authorization, validation
- **Testing Strategy** - Unit tests, integration tests, fixtures

---

**Desenvolvido para Compasse** | Sistema especializado em gestão tributária brasileira

---

## 👤 Sobre o Desenvolvedor

### João Vítor Aguiar da Silva

Desenvolvedor Full Stack com experiência em Django/Python e React/TypeScript, especializado em desenvolvimento de sistemas corporativos e soluções de gestão empresarial. Apaixonado por arquiteturas modernas, segurança de aplicações e APIs escaláveis.

**Especialidades:**
- Backend: Django, DRF, PostgreSQL, APIs REST
- Frontend: React, TypeScript, Next.js
- DevOps: Docker, CI/CD, Deploy automatizado
- Segurança: JWT, 2FA, RBAC, Auditoria

**Contatos:**
- **LinkedIn**: [linkedin.com/in/joaovads](https://www.linkedin.com/in/joão-vítor-aguiar-da-silva-9349b6305/)
- **Email**: [jvads2005@gmail.com](mailto:jvads2005@gmail.com)
- **GitHub**: [github.com/jvaguiar05](https://github.com/jvaguiar05)

Sempre em busca de novos desafios e oportunidades para contribuir com projetos inovadores e soluções tecnológicas que geram valor real para o negócio.
