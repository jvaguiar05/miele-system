# ADMIN – MIELE SYSTEM (Django Admin Backoffice)

> Especificações para o **BackOffice administrativo** do Miele System usando **Django Admin** endurecido + páginas auxiliares.  
> Foco: segurança, observabilidade, UX moderna e práticas operacionais.

---

## 1. Escopo e Objetivos

**Escopo:**  
Interface administrativa **interna** para gestão do sistema (usuários, aprovações, auditoria, supervisão de clientes e PER/DCOMPs).

**Objetivos:**

- Operar com segurança (2FA, hardening, rate limiting)
- Acelerar decisões (dashboards, filas de aprovação)
- Rastreabilidade total (auditoria detalhada, correlação por request)
- UX moderna (tema atualizado, navegação clara, filtros eficientes)

> **Nota:** Não inclui portal público, telas de uso do funcionário fora do contexto administrativo, ou front React.

---

## 2. Modelo de Acesso

### 2.1 Autenticação

- **Django Session Auth** com **2FA TOTP** obrigatório para usuários do backoffice.

### 2.2 Autorização (RBAC)

- Baseada em **Groups/Permissions** do Django.
- Pirâmide invertida: `Admin` é superset; se `Operator/Auditor` pode, `Admin` também pode.

### 2.3 Papéis e Capacidades

| Papel    | Capacidades Principais                                                                                         |
| -------- | -------------------------------------------------------------------------------------------------------------- |
| Admin    | Acesso total; gerencia usuários, papéis, aprovações, auditoria, configurações; executa ações sensíveis direto. |
| Approver | Aprova/recusa requests sensíveis; leitura de auditoria e entidades.                                            |
| Auditor  | Somente leitura de logs, auditoria, dashboards e entidades.                                                    |
| Operator | Acesso limitado às entidades (read/write não sensível); não aprova requests; sem acesso a usuários.            |

> **Regra:** Mínimo para acessar o backoffice: `is_staff=True` e pertencer a pelo menos um grupo acima.

---

## 3. Estrutura do Projeto

- **URL base:** `/admin/` (Django Admin padrão).
- **App dedicada:** `apps/admin_backoffice/` para páginas auxiliares (dashboards, filas, visões agregadas)
- **Django Admin nativo:** CRUD interno, com tema e hardening.

```
backend/
    core/
        urls.py  # path("backoffice/", admin_site.urls) + rotas auxiliares
    apps/
        admin_backoffice/
            admin.py        # registros e customizações do AdminSite/ModelAdmin
            apps.py
            urls.py         # rotas de páginas auxiliares
            views.py        # views auxiliares (somente staff)
            permissions.py  # gates de acesso por papel (decorators/mixins)
            menu.py         # definição de menu lateral/atalhos
    templates/
        admin/            # overrides de templates do Django Admin
        backoffice/       # telas auxiliares (dashboard, queue, etc.)
    static/
        backoffice/       # css/js adicionais (se necessário)
```

---

## 4. Autenticação e 2FA

- **Login:** SessionAuth + CSRF (separado do JWT da API)
- **2FA TOTP obrigatório:**
  - Onboarding: enrolment TOTP no primeiro login (QR + código)
  - Revalidação: TOTP em ações sensíveis (aprovar/deletar)
- **Sessão:**
  - `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`
  - `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`
  - Expiração inativa (ex.: 30 min) + reauth para aprovar ações
- **Rate limiting:** 5 req/5min por IP/usuário

---

## 5. Hardening e Segurança

- **URL custom:** `/backoffice/`
- **Headers:** HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- **CSP:** restritiva, permitir estáticos do próprio host
- **CORS:** desabilitado para o backoffice
- **CSRF:** obrigatório
- **Password policy:** complexidade mínima + expiração opcional para staff
- **Lockout:** bloquear após N falhas (temporário)
- **IP allowlist:** opcional em produção
- **Reauth:** senha + TOTP em ações sensíveis

---

## 6. UX e Visual

- **Tema moderno:**
  - **Django-Jazzmin** configurado com dark mode, ícones, menu lateral, breadcrumbs e navegação aprimorada
  - Interface responsiva e moderna
  - Customização de cores e branding
- **Navegação:**
  - Menu lateral por contexto (Identity, Clients, PER/DCOMPs, Common)
  - Inline editing para modelos relacionados (Address, Annotations, Files)
  - Actions personalizadas para aprovações em lote
- **Componentes-chave:**
  - Filtros por status, data de criação, tipo de entidade
  - Buscas por campo chave (CNPJ, e-mail, public_id, razão social)
  - Listagens paginadas com colunas úteis (status, timestamps, creator)
  - Inlines para Annotations e AttachedFiles nas entidades principais
  - Display formatado para JSON fields e campos complexos
- **Acessibilidade e i18n:**
  - Locale `pt-br`, TZ `America/Sao_Paulo`
  - Campos readonly para metadados (public_id, timestamps)

---

## 7. Funcionalidades do BackOffice

### 7.1 Gestão de Usuários (Identity)

- **UserAdmin customizado** baseado em Django UserAdmin
- Campos de visualização: username, email, full_name, role, approval_status, is_active, date_joined
- Filtros: role, approval_status, is_active, is_staff, date_joined, last_login
- Busca: username, email, first_name, last_name
- Fieldsets organizados: Informações Pessoais, Senha, Permissões e Status, Aprovação, Controle
- Inlines: Annotations e AttachedFiles vinculados ao usuário
- Readonly fields: public_id, date_joined, last_login

### 7.2 Gestão de Clientes

- **ClientAdmin** com visualização completa do ciclo de vida
- Campos de visualização: razao_social, cnpj, nome_fantasia, status, is_active, created_at
- Filtros personalizados: is_active, created_at, updated_at, com filtros por status específico
- Busca: cnpj, razao_social, nome_fantasia
- Inline para Address (um-para-um automático)
- Inlines para Annotations e AttachedFiles
- Fieldsets: Informações Gerais, Dados Empresariais, Localização/Endereço, Controle
- Display formatado para CNPJ e campos JSON

### 7.3 Gestão de Endereços

- **AddressAdmin** separado para controle detalhado
- Campos: string representation, municipio, uf, cep, created_at
- Filtros: uf, municipio, created_at
- Busca: logradouro, numero, bairro, municipio, cep
- Fieldsets organizados por contexto geográfico

### 7.4 Supervisão de PER/DCOMPs

- **PerDcompAdmin** com foco em documentos tributários
- Campos de visualização: numero, numero_perdcomp, cliente, status, valor_pedido, data_transmissao
- Filtros: status, data_transmissao, data_vencimento, created_at, updated_at
- Date hierarchy por data_transmissao
- Busca: numero, numero_perdcomp, cnpj, processo_protocolo
- Inlines para Annotations e AttachedFiles
- Fieldsets: Informações Gerais, Vinculação, Valores e Datas, Controle
- Display customizado para cliente relacionado
- Readonly fields: todos os campos (imutabilidade)
- Display JSON formatado para payload_before/after
- Fieldsets colapsáveis para dados técnicos
- Ordenação por timestamp (mais recente primeiro)

### 7.6 Aprovações (ApprovalRequest)

- **ApprovalRequestAdmin** para gerenciar workflow de aprovações
- Filtros: StatusFilter, RequestTypeFilter  
- Campos: entity_display, change_type, status, requested_by, requested_at
- Busca: requested_by_id, reviewed_by_id
- Actions personalizadas para aprovação em lote
- Fieldsets: Request Details, Data Changes, Review Information, Metadata, Timestamps
- Display formatado para changes_requested (JSON)
- Readonly fields baseados no status da request

### 7.7 Arquivos e Anexos (Shared)

- **AttachedFileAdmin** para gestão de uploads
- Campos: filename, file_type, entity_display, uploaded_by, created_at
- Filtros: file_type, created_at
- Busca: filename, original_filename
- Link direto para download via Google Drive
- Display customizado para tamanho de arquivo e tipo MIME
- Fieldsets: File Information, Entity Link, Metadata

### 7.8 Anotações (Annotations)

- **AnnotationAdmin** para gestão de notas
- Campos: truncated_content, entity_display, created_by, created_at
- Filtros: created_at, content_type
- Busca: content, created_by__username
- Display truncado do conteúdo para visualização rápida
- Fieldsets: Content, Entity Link, Metadata
- Inline disponível em todas as entidades principais

---

## 8. Integrações

- **Google Drive API:** Gestão de arquivos anexos via proxy transparente
- **Consulta CNPJ:** ação no cliente para "Verificar CNPJ" (serviço gratuito); exibir resumo e timestamp

---

## 9. Auditoria de Ações

- Toda ação relevante gera **AuditLog**:
  - Campos: `actor_id`, `actor_role`, `entity_type`, `entity_id`, `action`, `payload_diff`, `reason`, `correlation_id`, `ip`, `user_agent`, `ts`
- Imutabilidade: registros não podem ser alterados; apenas retificações anexadas
- Retenção: políticas de limpeza conforme `ARQUITETURA.md`

---

## 10. Desempenho e Dados

- Querysets otimizados: `select_related/prefetch_related` em `ModelAdmin.get_queryset`
- Paginação padrão (50–100 itens)
- Campos indexados: CNPJ, status, `created_at`, `updated_at`, `requested_by`
- Uploads: Google Drive API (OAuth 2.0) com proxy transparente

---

## 11. Observabilidade

- Logs: ações administrativas em JSON (stdout)
- Health: endpoints `/health/live` e `/health/ready` visíveis apenas para Admin (ou IP allowlist)
- Métricas (futuro): page views, volume de approvals por período

---

## 12. Checklists de Implementação

### 12.1 Infra e Settings

- [ ] Definir `BACKOFFICE_URL_PATH=/backoffice/`
- [ ] Ativar HTTPS e `SECURE_*` flags em prod
- [ ] Configurar Sentry DSN e logging JSON
- [ ] CSP, HSTS, headers de segurança
- [ ] `SESSION_COOKIE_SECURE/HTTPONLY`, expiração
- [ ] Rate limit de login backoffice
- [ ] Lockout após N falhas

### 12.2 Autorização e 2FA

- [ ] `is_staff=True` para acessantes
- [ ] Criar grupos: Admin, Approver, Auditor, Operator
- [ ] Mapear permissões por app/model/ação
- [ ] Enforce 2FA TOTP para staff (middleware + gate)
- [ ] Fluxo de reauth (senha + TOTP) para ações sensíveis

### 12.3 Django Admin

- [ ] Customizar AdminSite (branding, título, index)
- [ ] Registrar ModelAdmins com list_display, list_filter, search_fields
- [ ] `save_model/delete_model` → gravar AuditLog
- [ ] Ações administrativas (mass actions) apenas para Admin
- [ ] Overrides de templates (logo, cores, breadcrumbs)

### 12.4 Páginas Auxiliares (`admin_backoffice`)

- [ ] Dashboard: cards, gráficos, fila de approvals
- [ ] Requests: listagem e detalhe com diff + aprovar/recusar
- [ ] Logs: listagem com filtros + export
- [ ] Widgets: status CNPJ, erros recentes (Sentry)

### 12.5 QA e Operação

- [ ] Testes de permissão (cada papel) e de 2FA
- [ ] Testes de aprovações (happy path, recusa, reauth)
- [ ] Testes de auditoria (campos obrigatórios, imutabilidade)
- [ ] Monitorar Sentry (release/tag de ambiente)
- [ ] Treinamento breve para Admins (fluxos e responsabilidades)

---

## 13. Itens de Configuração (Resumo)

- **URLs:** `BACKOFFICE_URL_PATH=/backoffice/`
- **Sessão:** `SESSION_COOKIE_SECURE/HTTPONLY`, expiração inativa
- **2FA:** TOTP obrigatório para `is_staff`
- **Login:** rate limit + lockout
- **Headers:** HSTS, CSP, etc.
- **Storage:** Google Drive API (OAuth 2.0)
- **Logs:** JSON stdout; Sentry habilitado em prod
- **Locale:** `LANG=pt-br`, `TZ=America/Sao_Paulo`

---

## 14. Menu do BackOffice (Proposta)

1. Dashboard
2. Requests (pendentes, todas, por tipo)
3. Usuários (listagem, grupos, 2FA)
4. Clientes (listagem, detalhes, notas, anexos)
5. PER/DCOMPs (listagem, detalhes, notas, anexos)
6. Logs & Auditoria (consulta, export)
7. Configurações (somente Admin)

---

## 15. Políticas Operacionais

- Menor privilégio: conceder o papel mínimo necessário
- Justificativa obrigatória em todas as aprovações/recusas
- Segregação de funções: quem solicita não aprova
- Revisões periódicas de acessos (trimestral)
- Retenção e limpeza de logs conforme política

---

## Anexo A — Glossário

- **Request:** solicitação de ação sensível que requer aprovação
- **AuditLog:** trilha imutável de eventos/ações com correlação
- **TOTP:** Time-based One-Time Password (2FA)
- **CSP:** Content Security Policy

---
