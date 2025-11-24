# ESCOPO – MIELE SYSTEM

## Função

O **Miele System** é um software de **gestão empresarial** cuja principal função é expor e controlar formulários relacionados a **clientes** e a **PER/DCOMPs** (documentos de análise tributária) referentes aos serviços prestados pela companhia.  
O sistema deve suportar **autenticação** e **autorização por cargos**, garantindo que somente usuários autorizados acessem e/ou alterem dados sensíveis.

---

## Usuários

- **Funcionário da empresa**: registra, consulta e manipula informações de clientes e PER/DCOMPs.
- **Administrador (Gerente/Admin do software)**: valida usuários, supervisiona logs, controla dados sensíveis e aprova/recusa ações relevantes.
- **Convidado da Empresa**: visualiza informações de clientes e PER/DCOMPs.

> Observação: o design prevê **extensibilidade futura** para perfis adicionais (ex.: acesso parcial a clientes externos), embora **fora do MVP**.

---

## Contextos Principais

### 1 Identity (Usuários + Autenticação)

**MVP**

- Aprovação de criação de usuário por **admin** via endpoints.
- Login/Logout com **JWT + refresh rotation + blacklist**.
- **2FA TOTP** com app autenticador (ex.: Google Authenticator) usando `django-otp`.
  - **Fallback**: verificação por **e-mail** caso o usuário não ative TOTP.
- **RBAC** por grupos/permissões (DRF).
- **E-mail transacional** (confirmação, reset de senha).
- **Soft-delete** de usuário.
- **Rate limiting** em `/auth/*` (ex.: `django-ratelimit`).
- **Throttling DRF** (escopos `anon`/`user` e por endpoints sensíveis).

**Futuro**

- **SMS (OTP)** (excluído do MVP por custo).

---

### 2 Clients (Clientes da Companhia)

**MVP**

- Proteção de endpoints (auth + RBAC).
- Ações únicas do admin (**Soft-Delete**).
- Ações que exigem aprovação do admin (alteração de dados sensíveis).
- Controle completo do ciclo de vida do cliente.
- **Logs de auditoria** detalhados e rastreáveis por usuário.
- **Anotações por usuário** (cada usuário mantém suas próprias notas do cliente).
- **Anexos** (recibos/docs) com armazenamento **local em dev** e **S3 em prod** (free tier ou equivalente).

---

### 3 PER/DCOMPs (por Cliente)

**MVP**

- Proteção de endpoints (auth).
- Ações únicas do admin (**Soft-Delete**).
- Ações que exigem aprovação do admin (alteração sensível).
- Controle completo do ciclo de vida da PER/DCOMP.
- **Logs de auditoria** detalhados e rastreáveis por usuário.
- **Anotações por usuário**.
- **Anexos próprios** (upload manual), reutilizando o mesmo servidor de arquivos de Clientes.

---

### 4 Admin (BackOffice)

> Detalhes em `ADMIN.md`. No escopo geral, o BackOffice deve permitir:

**MVP**

- **Dashboards**:
  - Alterações por período (logs).
  - Alterações por usuário.
  - Alterações por entidade/cliente/PERD.
- **Interface de Controle**:
  - Gerenciar ciclo de vida de todas as entidades.
  - Aprovar/recusar **usuários**.
  - Aprovar/recusar **comandos sensíveis** (ex.: alteração de CNPJ).
- **Contas temporárias read-only** (implementar por último no MVP).

---

## Integrações Externas

**MVP**

- **Consulta CNPJ** via **serviço gratuito** (ex.: BrasilAPI). Se indisponível/instável, pausar funcionalidade no MVP.

**Futuro**

- Integração com **Receita Federal**.

> **Anexação de arquivos**: sempre **manual** para clientes e PER/DCOMPs (no MVP).

---

## Observabilidade, Logs & Segurança

**MVP**

- **Logs JSON no stdout** (aplicação/infra).
- **Sentry** para **exceções** (Django + Celery se ativo).
- **Logs de Auditoria de Negócio internos** (tabelas dedicadas, com FK para entidades/usuários, imutáveis).
- Health checks: `/health/live` e `/health/ready`.
- **CORS restrito** e **headers de segurança** (HSTS, X-Content-Type-Options, etc.).

**Futuro**

- **Loki + Promtail + Grafana** para observabilidade de logs de aplicação/infra.

---

## Tarefas Assíncronas

**MVP**

- **Envio assíncrono de e-mail**.
- **Jobs de limpeza** (retenção de logs/eventos/arquivos temporários).
- **Celery + Redis** (incluir no MVP mediante **setup simples via `docker-compose`**).

**Futuro**

- Ampliar uso do Celery para fluxos adicionais (ex.: processos longos, integrações em lote).

---

## Armazenamento de Arquivos

**MVP**

- **Local** em ambiente de desenvolvimento.
- **S3 em produção** (preferir **free tier**).

**Futuro**

- **Versionamento** de arquivos e **antivírus** (ex.: clamd).

---

## Escalabilidade

**Futuro**

- **Multi-tenant** (fora do MVP, manter design preparado para evolução).

---

## Definições de Escopo Extra (MVP)

- Serviço de **e-mail** (e opcionalmente SMS no futuro).
- **Servidor de arquivos** (local dev, S3 prod).
- **Eventos** para ações assíncronas e registro de auditoria (ex.: `changeClientCnpjCommand -> Requested by userX`).
- Suporte a autenticação, autorização, **cache** (quando aplicável) e logs.
- Possível **firewall** adicional no futuro.

---

## Front-End

- Backend **API-first**.
- Frontend principal em **React** (fora do escopo do backend).
- No Django, a única interface prevista é o **Admin BackOffice**.

---

## Foco Principal

- Visualização e controle eficientes de **Clientes** e **PER/DCOMPs**.
- **Autenticação** fluída e **autorização** robusta.
- **Auditoria completa**, com rastreabilidade por usuário.
- Priorizar **performance do workflow** e **custo zero/baixo** (open-source/free tier) sempre que possível.
