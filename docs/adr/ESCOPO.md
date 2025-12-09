# ESCOPO – MIELE SYSTEM

## Função

O **Miele System** é um software de **gestão empresarial** desenvolvido pela Compasse, cuja principal função é controlar e gerenciar **clientes** e **PER/DCOMPs** (documentos de análise tributária) referentes aos serviços prestados pela empresa.  

O sistema implementa **autenticação robusta** com JWT e 2FA, **autorização granular** por roles (RBAC), **sistema de aprovações** para mudanças sensíveis, **auditoria completa** e **interface administrativa moderna** com Django Admin + Jazzmin.

---

## Usuários

- **Employee (Funcionário)**: Registra, consulta e manipula informações de clientes e PER/DCOMPs. Pode criar anotações e fazer uploads. Alterações sensíveis geram requests de aprovação.
- **Admin (Administrador)**: Acesso total ao sistema, aprova/recusa requests, gerencia usuários, supervisiona logs de auditoria, executa ações sensíveis diretamente sem aprovação.
- **Guest (Convidado)**: Acesso limitado apenas para visualização de dados públicos não sensíveis.

> **Observação**: O sistema utiliza **Django Groups** para implementar RBAC, com roles mapeadas para permissões específicas por recurso.

---

## Contextos Principais

### 1. Identity (Usuários + Autenticação)

**Implementado**

- **Registro com aprovação**: Novos usuários ficam pendentes até aprovação do Admin.
- **Autenticação JWT**: Access tokens curtos (15min) + refresh rotation + blacklist via `djangorestframework-simplejwt`.
- **2FA TOTP**: Integração com `django-otp` para autenticação de dois fatores via apps como Google Authenticator.
- **RBAC**: Sistema baseado em Django Groups (Admin, Employee, Guest) com permissões granulares.
- **Rate limiting**: `django-ratelimit` aplicado em endpoints de autenticação.
- **Throttling**: DRF throttling para limitar requisições por usuário/IP.
- **Soft-delete**: Usuários são desativados, não removidos fisicamente.
- **Change requests**: Alterações sensíveis (email, etc.) geram approval requests.

**Comandos de gerenciamento disponíveis:**
- `create_superuser_with_role`: Criação de superusuário com role específica
- `setup_roles`: Configuração inicial de roles e permissões
- `migrate_users`: Migração de usuários existentes para novo sistema de roles

---

### 2. Clients (Clientes da Companhia)

**Implementado**

- **CRUD completo**: ViewSets DRF com lookup por `public_id` (UUID).
- **Endereço integrado**: Cada cliente tem um endereço (modelo `Address`) criado automaticamente.
- **Sistema de aprovações**: Alterações de campos sensíveis (CNPJ, razão social) geram `ApprovalRequest` para Admin.
- **Anexos via Google Drive**: Upload/download transparente com proxy interno.
- **Anotações por usuário**: Sistema de notas individuais com `Annotation` model.
- **Soft-delete**: Apenas Admin pode deletar, com `deleted_at` timestamp.
- **Auditoria completa**: Logs imutáveis de todas as operações via `AuditLog`.
- **Filtros e busca**: Por CNPJ, razão social, status, data de criação.
- **Validações**: CNPJ, campos obrigatórios, regras de negócio.

**Interface Admin disponível** com inlines para endereço, anotações e arquivos anexos.

---

### 3. PER/DCOMPs (por Cliente)

**Implementado**

- **Vinculação obrigatória**: Cada PER/DCOMP pertence a um cliente específico.
- **CRUD completo**: ViewSets com aprovações automáticas para campos sensíveis.
- **Anexos próprios**: Sistema de upload independente para documentos específicos.
- **Anotações por usuário**: Notas individuais por documento.
- **Soft-delete**: Apenas Admin pode deletar diretamente.
- **Auditoria completa**: Rastreamento de todas as alterações.
- **Campos tributários**: Números, protocolos, valores, datas de transmissão/vencimento.
- **Busca avançada**: Por número, CNPJ, protocolo, status.

**Relacionamento com clientes** permite listagem de PER/DCOMPs por cliente específico.

---

### 4. Admin (BackOffice)

**Implementado**

- **Django Admin** customizado com tema **django-jazzmin** moderno e responsivo.
- **Interfaces administrativas** completas para todas as entidades:
  - **UserAdmin**: Gerenciamento de usuários, roles, status de aprovação
  - **ClientAdmin**: Gestão de clientes com inline de endereço
  - **PerDcompAdmin**: Supervisão de documentos tributários
  - **AuditLogAdmin**: Visualização de logs com filtros avançados
  - **ApprovalRequestAdmin**: Fila de aprovações com ações em lote
- **Filtros avançados**: Por status, data, tipo de entidade, ação.
- **Inlines automáticos**: Anotações e arquivos anexos em todas as entidades principais.
- **Readonly fields**: Metadados imutáveis como `public_id`, timestamps.
- **Display customizado**: Formatação JSON, truncamento de texto, links diretos.

---

## Integrações Externas

**Implementado**

- **Google Drive API**: Integração completa via OAuth 2.0 para armazenamento de arquivos
  - Proxy transparente para upload/download
  - Pastas organizadas por tipo de entidade (clients, perdcomps)
  - Validação de tipos de arquivo e tamanhos
  - Refresh token automático para acesso contínuo

**Planejado (não implementado no MVP)**

- **Consulta CNPJ**: Via serviços gratuitos como BrasilAPI
- **Integração Receita Federal**: Para validações tributárias

---

## Observabilidade, Logs & Segurança

**Implementado**

- **Logs estruturados JSON**: Configuração via `common.observability.logging`
- **AuditLog system**: Rastreamento imutável de todas as operações CUD
  - Correlation ID para rastreamento de requests
  - Payload before/after para mudanças
  - Metadados completos (usuário, IP, timestamp, ação)
- **Health checks**: Endpoints `/health/live` e `/health/ready`
- **CORS restrito**: Configuração específica por ambiente
- **Headers de segurança**: HSTS, X-Content-Type-Options, CSP
- **Middleware custom**: Correlation ID, failed login tracking
- **JWT Security**: Blacklist de tokens, rotação automática

---

## Tarefas Assíncronas

**Status MVP**

- **Processamento síncrono**: Para simplificar implementação inicial
- **Dependências preparadas**: Celery + Redis estão em requirements mas não ativados
- **Management commands**: Limpeza de dados via comandos Django

**Planejamento futuro**

- **Celery + Redis**: Para envio de emails, processamento de arquivos
- **Jobs automatizados**: Limpeza de logs antigos, validações em lote

---

## Armazenamento de Arquivos

**Implementado**

- **Google Drive API**: Única solução de storage implementada
  - OAuth 2.0 com refresh token
  - Proxy transparente via API (`/api/v1/shared/files/{id}/download/`)
  - Organização em pastas por entidade
  - Validações de segurança e tipo

**Configuração via variáveis de ambiente:**
- `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET`
- `GDRIVE_REFRESH_TOKEN`
- `GDRIVE_CLIENTS_FOLDER_ID`, `GDRIVE_PERDCOMPS_FOLDER_ID`

---

## Escalabilidade

**Arquitetura atual**: Single-tenant com design preparado para multi-tenant futuro.

**Tecnologias implementadas**:
- PostgreSQL para produção (via Render.com)
- SQLite para desenvolvimento
- WhiteNoise para arquivos estáticos
- Django 5.x com DRF para API

---

## Front-End

**Arquitetura API-first** implementada:
- **OpenAPI/Swagger**: Documentação completa via `drf-spectacular`
- **Endpoints RESTful**: Padronizados com filtros, paginação, busca
- **CORS configurado**: Para integração com frontend React futuro

**Interface atual**: Django Admin como única interface visual.

---

## Foco Principal Realizado

✅ **Visualização e controle eficientes** de Clientes e PER/DCOMPs  
✅ **Autenticação fluída** com JWT + 2FA TOTP  
✅ **Autorização robusta** via RBAC com Django Groups  
✅ **Auditoria completa** com rastreabilidade por usuário e correlation ID  
✅ **Sistema de aprovações** para mudanças sensíveis  
✅ **Interface administrativa moderna** com django-jazzmin  
✅ **Integração Google Drive** para armazenamento de arquivos  
✅ **Deploy automatizado** no Render.com  

---

## Tecnologias Implementadas vs Planejadas

### ✅ Implementadas
- Django 5.x + DRF
- PostgreSQL (prod) + SQLite (dev) 
- JWT Authentication (djangorestframework-simplejwt)
- Google Drive API (OAuth 2.0)
- django-jazzmin (admin theme)
- WhiteNoise (static files)
- drf-spectacular (OpenAPI)
- django-otp (2FA)
- Render.com (deploy)

### ❌ Removidas/Não implementadas no MVP
- **~~Redis/Celery~~**: Dependências presentes mas não ativadas
- **~~Sentry~~**: Configurado mas opcional via `SENTRY_DSN`
- **~~AWS S3~~**: Substituído por Google Drive API
- **~~SMTP Email~~**: Não implementado no MVP
- **~~BrasilAPI CNPJ~~**: Planejado para versões futuras

### 🔄 Configuradas mas não ativas
- Celery + Redis (em requirements, não configurado)
- Sentry (configurado, ativação via ENV)
- Email backends (configuração presente, não utilizada)

---

## Comandos de Desenvolvimento

O sistema inclui comandos personalizados para facilitar setup e manutenção:

```bash
# Setup inicial
make up                    # Docker containers
make migrate               # Aplicar migrações
make setup-roles           # Configurar roles
make superuser             # Criar superusuário com role

# Comandos diretos Django
python manage.py create_superuser_with_role
python manage.py setup_roles
python manage.py migrate_users
```

---

## Observações de Implementação

- **Public IDs**: Todas as entidades usam UUIDs como identificadores públicos
- **Soft Delete**: Implementado em User, Client, PerDcomp
- **Approval System**: Funciona via decorators e mixins em ViewSets
- **Google Drive**: Integração transparente com validações de segurança
- **Admin Interface**: Completamente customizado com inlines e filtros
- **API Documentation**: Gerada automaticamente com exemplos
- **Health Monitoring**: Endpoints para liveness e readiness checks

O sistema está **funcionalmente completo** para gestão de clientes e documentos tributários, com todas as features de segurança, auditoria e aprovação implementadas.
