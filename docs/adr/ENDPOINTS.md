# ENDPOINTS – MIELE SYSTEM (v1)

## Convenções

- **Prefixo:** `/api/v1`
- **Auth:** JWT Bearer (obrigatório em todos, exceto `/auth/login`, `/auth/register`, `/auth/refresh`)
- **Papéis:** `Employee` (usuário autenticado), `Admin` (superset), `Guest` (visualização limitada)
- **Pirâmide invertida:** Se `Employee` pode acessar, **`Admin` também pode**.
- **Fluxos sensíveis:** Alterações de campos críticos geram _requests_ de aprovação para o Admin, exceto quando o próprio Admin executa diretamente.
- **Lookup:** Entidades usam `public_id` (UUID) como identificador nas URLs.

---

## 1. Usuário & Autenticação

| Nome               | Método | Permissão | Rota                                    | Descrição                                                     |
| ------------------ | ------ | --------- | --------------------------------------- | ------------------------------------------------------------- |
| Login              | POST   | Anônimo   | `/api/v1/auth/login/`                   | Autentica usuário e retorna tokens (access/refresh).          |
| Logout             | POST   | Auth      | `/api/v1/auth/logout/`                  | Invalida refresh token (blacklist) e encerra sessão.          |
| Refresh Token      | POST   | Anônimo   | `/api/v1/auth/refresh/`                 | Gera novo access token a partir do refresh válido.            |
| Register           | POST   | Anônimo   | `/api/v1/auth/register/`                | Cria usuário com **status pendente** para aprovação do Admin. |
| RBAC Info          | GET    | Auth      | `/api/v1/auth/rbac/`                    | Retorna informações de roles e permissões do usuário.         |
| TOTP Enroll        | POST   | Auth      | `/api/v1/auth/totp/enroll/`             | Configura 2FA TOTP para o usuário.                           |
| Auth Throttle Test | GET    | Auth      | `/api/v1/auth/throttle-test/`           | Endpoint para teste de rate limiting.                        |
| Get Me             | GET    | Auth      | `/api/v1/users/me/`                     | Retorna dados do próprio usuário.                             |
| Update Me          | PATCH  | Auth      | `/api/v1/users/me/`                     | Atualiza campos não sensíveis do próprio usuário.             |
| Deactivate Me      | POST   | Auth      | `/api/v1/users/deactivate/`             | Solicita desativação da própria conta.                        |
| Change My Password | POST   | Auth      | `/api/v1/users/password/`               | Altera a senha do próprio usuário (com validações).           |
| Email Change Request | POST | Auth      | `/api/v1/users/email/change-request/`   | Solicita alteração de email (requer aprovação).              |
| My Change Requests | GET    | Auth      | `/api/v1/users/my-change-requests/`     | Lista requests criadas pelo usuário autenticado.             |

---

## 2. Clientes

| Nome                              | Método | Permissão | Rota                                                        | Descrição                                                                                   |
| --------------------------------- | ------ | --------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| List Clients                      | GET    | Auth      | `/api/v1/clients/clients/`                                  | Lista paginada com filtros (is_active) e busca (cnpj, razao_social, nome_fantasia).       |
| Create Client                     | POST   | Auth      | `/api/v1/clients/clients/`                                  | Cria cliente com endereço automático (campos planos do endereço).                          |
| Get Client                        | GET    | Auth      | `/api/v1/clients/clients/{public_id}/`                      | Detalhe do cliente com endereço incluído.                                                  |
| Update Client                     | PUT    | Auth      | `/api/v1/clients/clients/{public_id}/`                      | Atualiza cliente e endereço (campos sensíveis geram approval request).                     |
| Partial Update Client             | PATCH  | Auth      | `/api/v1/clients/clients/{public_id}/`                      | Atualização parcial com aprovação automática para campos sensíveis.                       |
| Delete Client                     | DELETE | Admin     | `/api/v1/clients/clients/{public_id}/`                      | Soft-delete imediato (apenas Admin).                                                       |
| Create Client Annotation          | POST   | Auth      | `/api/v1/clients/annotations/by-client/{client_id}/`        | Cria anotação vinculada ao cliente.                                                        |
| List Client Annotations           | GET    | Auth      | `/api/v1/clients/annotations/by-client/{client_id}/`        | Lista anotações do cliente (autor vê suas; Admin vê todas).                                |
| Update Client Annotation          | PUT    | Auth      | `/api/v1/clients/annotations/{annotation_id}/`             | Atualiza anotação (apenas autor ou Admin).                                                 |
| Partial Update Client Annotation  | PATCH  | Auth      | `/api/v1/clients/annotations/{annotation_id}/`             | Atualização parcial de anotação.                                                           |
| Delete Client Annotation          | DELETE | Auth      | `/api/v1/clients/annotations/{annotation_id}/`             | Remove anotação (apenas autor ou Admin).                                                   |

---

## 3. PER/DCOMPs

> Observação: PER/DCOMPs são **documentos tributários**; todos os endpoints exigem **autenticação**.

| Nome                              | Método | Permissão | Rota                                                     | Descrição                                                                              |
| --------------------------------- | ------ | --------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| List PERDCOMPs                    | GET    | Auth      | `/api/v1/perdcomps/`                                     | Lista paginada com filtros (status) e busca (numero, numero_perdcomp, cnpj).          |
| Create PERDCOMP                   | POST   | Auth      | `/api/v1/perdcomps/`                                     | Cria PER/DCOMP vinculada a cliente.                                                   |
| Get PERDCOMP                      | GET    | Auth      | `/api/v1/perdcomps/{public_id}/`                         | Detalhe da PER/DCOMP com dados do cliente.                                            |
| Update PERDCOMP                   | PUT    | Auth      | `/api/v1/perdcomps/{public_id}/`                         | Atualiza PER/DCOMP (campos sensíveis geram approval request).                         |
| Partial Update PERDCOMP           | PATCH  | Auth      | `/api/v1/perdcomps/{public_id}/`                         | Atualização parcial com aprovação automática para campos sensíveis.                  |
| Delete PERDCOMP                   | DELETE | Admin     | `/api/v1/perdcomps/{public_id}/`                         | Soft-delete imediato (apenas Admin).                                                  |
| Get by Client                     | GET    | Auth      | `/api/v1/perdcomps/by_client/{client_public_id}/`        | Lista PER/DCOMPs de um cliente específico.                                            |
| Create PERDCOMP Annotation        | POST   | Auth      | `/api/v1/perdcomps/annotations/by-perdcomp/{perdcomp_id}/` | Cria anotação vinculada à PER/DCOMP.                                                |
| List PERDCOMP Annotations         | GET    | Auth      | `/api/v1/perdcomps/annotations/by-perdcomp/{perdcomp_id}/` | Lista anotações da PER/DCOMP (autor vê suas; Admin vê todas).                       |
| Update PERDCOMP Annotation        | PUT    | Auth      | `/api/v1/perdcomps/annotations/{annotation_id}/`         | Atualiza anotação (apenas autor ou Admin).                                           |
| Partial Update PERDCOMP Annotation | PATCH | Auth      | `/api/v1/perdcomps/annotations/{annotation_id}/`         | Atualização parcial de anotação.                                                     |
| Delete PERDCOMP Annotation        | DELETE | Auth      | `/api/v1/perdcomps/annotations/{annotation_id}/`         | Remove anotação (apenas autor ou Admin).                                             |

---

## 4. Administração

### 4.1. Approval Requests (Aprovações)

| Nome                      | Método | Permissão | Rota                                                | Descrição                                                             |
| ------------------------- | ------ | --------- | --------------------------------------------------- | --------------------------------------------------------------------- |
| List Change Requests      | GET    | Admin     | `/api/v1/admin/change-requests/`                   | Lista de change requests pendentes (filtros por tipo, entidade, ator, data). |
| Review Change Request     | POST   | Admin     | `/api/v1/admin/change-requests/{request_id}/review/` | Aprova ou recusa uma solicitação de mudança (com justificativa).      |

### 4.2. Arquivos Anexos

| Nome                      | Método | Permissão | Rota                                  | Descrição                                                             |
| ------------------------- | ------ | --------- | ------------------------------------- | --------------------------------------------------------------------- |
| Upload File               | POST   | Auth      | `/api/v1/shared/files/`               | Upload de arquivo para Google Drive com validações.                  |
| List Files                | GET    | Auth      | `/api/v1/shared/files/`               | Lista arquivos com filtros por tipo e entity.                        |
| Get File                  | GET    | Auth      | `/api/v1/shared/files/{public_id}/`   | Detalhe do arquivo com metadados.                                    |
| Download File             | GET    | Auth      | `/api/v1/shared/files/{public_id}/download/` | Download direto via proxy do Google Drive.                   |
| Update File               | PATCH  | Auth      | `/api/v1/shared/files/{public_id}/`   | Atualiza metadados do arquivo (apenas autor ou Admin).               |
| Delete File               | DELETE | Admin     | `/api/v1/shared/files/{public_id}/`   | Remove arquivo do Google Drive e registro local (apenas Admin).      |

### 4.3. Dashboards e Métricas

| Nome                      | Método | Permissão | Rota                                  | Descrição                                                             |
| ------------------------- | ------ | --------- | ------------------------------------- | --------------------------------------------------------------------- |
| Client Dashboard          | GET    | Auth      | `/api/v1/dashboard/clients/`          | Métricas e estatísticas de clientes.                                 |
| Activity Logs             | GET    | Auth      | `/api/v1/activities/audit-logs/`      | Logs de auditoria com filtros avançados.                             |
| Activity by Entity        | GET    | Auth      | `/api/v1/activities/audit-logs/by-entity/{entity_type}/{entity_id}/` | Logs específicos de uma entidade.                                    |

---

## 5. Utilitários

| Nome               | Método | Permissão | Rota                           | Descrição                                             |
| ------------------ | ------ | --------- | ------------------------------ | ----------------------------------------------------- |
| Ping Clients       | GET    | Público   | `/api/v1/clients/ping/`        | Health check do módulo de clientes.                  |
| Ping PERDCOMPs     | GET    | Público   | `/api/v1/perdcomps/ping/`      | Health check do módulo de PER/DCOMPs.                |
| Ping Identity      | GET    | Público   | `/api/v1/identity/ping/`       | Health check do módulo de identidade.                |

---

## 📋 Notas Importantes

### Lookup por Public ID
Todas as entidades (Client, PerDcomp, User, File, etc.) usam `public_id` (UUID) como identificador nas URLs, não o ID sequencial interno.

### Sistema de Aprovações
Campos considerados sensíveis:
- **Clients**: `cnpj`, `razao_social` e outros campos críticos
- **PERDCOMPs**: `numero`, `numero_perdcomp`, identificadores fiscais

Quando um usuário (não Admin) tenta alterar esses campos, é criado automaticamente um `ApprovalRequest` que fica pendente para revisão do Admin.

### Annotations (Notas)
- Cada usuário pode criar notas sobre clientes e PER/DCOMPs
- Por padrão, cada usuário vê apenas suas próprias notas
- Admins podem ver todas as notas de todos os usuários

### Arquivos e Google Drive
- Upload direto para Google Drive via API
- Proxy transparente para download (sem exposição de URLs do Google Drive)
- Validações de tipo de arquivo e tamanho
- Soft delete mantém referência no Google Drive

### Auditoria
- Todas as operações CUD (Create, Update, Delete) geram logs de auditoria
- Logs incluem `correlation_id` para rastreamento de requests
- Imutabilidade: logs não podem ser alterados após criação
| List Client Logs   | GET    | Admin     | `/api/v1/admin/logs/clients`                 | Lista de logs de clientes (paginado/filtrado).                           |
| View PERDCOMP Logs | GET    | Admin     | `/api/v1/admin/logs/perdcomps/{perdcomp_id}` | Logs de uma PER/DCOMP específica.                                        |
| List PERDCOMP Logs | GET    | Admin     | `/api/v1/admin/logs/perdcomps`               | Lista de logs de PER/DCOMPs (paginado/filtrado).                         |

---

## 5. Observações de Implementação

- **Paginação padrão** DRF com `page`, `pageSize`, `sort` (ex.: `-createdAt`).
- **Aprovação:** endpoints `.../requests/...` criam registros com `status=pending|approved|declined`, `requested_by`, `approved_by`, `reason`, `diff` (payload) e `correlation_id`.
- **Público vs Auth:** Endpoints `Público` retornam **somente metadados não sensíveis**. Detalhes, notas e **arquivos** (incluindo URLs de download) **exigem Auth**.
- **Files:** downloads respeitam permissões; quando sensível, use **URLs assinadas** (S3) com expiração curta.
- **Erros:** usar envelope de erro canônico do projeto.

---
