# ENDPOINTS – MIELE SYSTEM (v1)

## Convenções

- **Prefixo:** `/api/v1`
- **Auth:** JWT Bearer (obrigatório em todos, exceto `/auth/login`, `/auth/register`, `/auth/refresh` **e endpoints públicos de visualização**)
- **Papéis:** `Public` (guest), `Auth` (usuário autenticado), `Admin` (superset), `Anonimous` (usuario nao autenticado).
- **Pirâmide invertida:** Se `Auth` pode acessar, **`Admin` também pode**.
- **Fluxos sensíveis:** Alterações de CNPJ, exclusões e campos críticos geram _requests_ de aprovação para o Admin, exceto quando o próprio Admin executa diretamente.
- **Dados públicos:** Endpoints marcados como `Público` retornam **apenas metadados não sensíveis**. Conteúdos e anexos **nunca** são públicos.

---

## 1. Usuário & Autenticação

| Nome               | Método | Permissão | Rota                        | Descrição                                                     |
| ------------------ | ------ | --------- | --------------------------- | ------------------------------------------------------------- |
| Login              | POST   | Anônimo   | `/api/v1/auth/login`        | Autentica usuário e retorna tokens (access/refresh).          |
| Logout             | POST   | Auth      | `/api/v1/auth/logout`       | Invalida refresh token (blacklist) e encerra sessão.          |
| Refresh Token      | POST   | Anônimo   | `/api/v1/auth/refresh`      | Gera novo access token a partir do refresh válido.            |
| Register           | POST   | Anônimo   | `/api/v1/auth/register`     | Cria usuário com **status pendente** para aprovação do Admin. |
| Get Me             | GET    | Auth      | `/api/v1/users/me`          | Retorna dados do próprio usuário.                             |
| Update Me          | PATCH  | Auth      | `/api/v1/users/me`          | Atualiza campos não sensíveis do próprio usuário.             |
| Delete Me (soft)   | DELETE | Auth      | `/api/v1/users/me`          | Solicita desativação/soft-delete da própria conta.            |
| Change My Password | POST   | Auth      | `/api/v1/users/me/password` | Altera a senha do próprio usuário (com validações).           |

---

## 2. Clientes

| Nome                              | Método | Permissão | Rota                                                    | Descrição                                                                                   |
| --------------------------------- | ------ | --------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Create Client                     | POST   | Auth      | `/api/v1/clients`                                       | Cria um cliente (campos não sensíveis).                                                     |
| Update Client (não sensível)      | PATCH  | Auth      | `/api/v1/clients/{client_id}`                           | Atualiza dados não sensíveis do cliente.                                                    |
| Request Sensitive Update (Client) | POST   | Auth      | `/api/v1/clients/{client_id}/requests/sensitive-update` | Solicita alteração **sensível** (ex.: CNPJ). Fica pendente para aprovação do Admin.         |
| Request Delete (Client)           | POST   | Auth      | `/api/v1/clients/{client_id}/requests/delete`           | Solicita **soft-delete** do cliente (aprovação do Admin).                                   |
| Delete Client (direto)            | DELETE | Admin     | `/api/v1/clients/{client_id}`                           | Soft-delete imediato (sem request).                                                         |
| Attach File (Client)              | POST   | Auth      | `/api/v1/clients/{client_id}/files`                     | Upload de anexo do cliente (dev: local; prod: S3).                                          |
| List Files (Client)               | GET    | Auth      | `/api/v1/clients/{client_id}/files`                     | Lista anexos do cliente (metadados/URLs assinadas conforme permissão).                      |
| Add Note (Client)                 | POST   | Auth      | `/api/v1/clients/{client_id}/notes`                     | Cria **nota do usuário** sobre o cliente (visível por autor e Admin).                       |
| List Notes (Client)               | GET    | Auth      | `/api/v1/clients/{client_id}/notes`                     | Lista notas (padrão: do autor; Admin pode filtrar por `?userId=`).                          |
| Get Client by CNPJ                | GET    | Público   | `/api/v1/clients/cnpj/{cnpj}`                           | Busca cliente pelo CNPJ (normaliza/valida). **Retorna apenas metadados públicos.**          |
| List Clients (paged)              | GET    | Público   | `/api/v1/clients`                                       | Lista paginada. Filtros: `?q=&cnpj=&status=&createdFrom=&createdTo=&page=&pageSize=&sort=`. |
| Get Clients by Filter (alias)     | GET    | Público   | `/api/v1/clients/search`                                | Buscas avançadas (mesmos filtros de `GET /clients`). **Somente metadados não sensíveis.**   |

---

## 3. PERDCOMPs

> Observação: PER/DCOMPs são **documentos tributários**; mesmo em visualização, exigem **Auth**.

| Nome                                | Método | Permissão | Rota                                                        | Descrição                                                                                       |
| ----------------------------------- | ------ | --------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Create PERDCOMP                     | POST   | Auth      | `/api/v1/perdcomps`                                         | Cria uma PER/DCOMP vinculada a um cliente.                                                      |
| Update PERDCOMP (não sensível)      | PATCH  | Auth      | `/api/v1/perdcomps/{perdcomp_id}`                           | Atualiza campos não sensíveis.                                                                  |
| Request Sensitive Update (PERDCOMP) | POST   | Auth      | `/api/v1/perdcomps/{perdcomp_id}/requests/sensitive-update` | Solicita alteração **sensível** (ex.: número/identificadores).                                  |
| Request Delete (PERDCOMP)           | POST   | Auth      | `/api/v1/perdcomps/{perdcomp_id}/requests/delete`           | Solicita **soft-delete**; aguarda aprovação do Admin.                                           |
| Delete PERDCOMP (direto)            | DELETE | Admin     | `/api/v1/perdcomps/{perdcomp_id}`                           | Soft-delete imediato (sem request).                                                             |
| Attach File (PERDCOMP)              | POST   | Auth      | `/api/v1/perdcomps/{perdcomp_id}/files`                     | Upload de anexo específico da PER/DCOMP.                                                        |
| List Files (PERDCOMP)               | GET    | Auth      | `/api/v1/perdcomps/{perdcomp_id}/files`                     | Lista anexos da PER/DCOMP (metadados/URLs assinadas conforme permissão).                        |
| Add Note (PERDCOMP)                 | POST   | Auth      | `/api/v1/perdcomps/{perdcomp_id}/notes`                     | Cria **nota do usuário** sobre a PER/DCOMP.                                                     |
| List Notes (PERDCOMP)               | GET    | Auth      | `/api/v1/perdcomps/{perdcomp_id}/notes`                     | Lista notas (padrão: do autor; Admin pode filtrar).                                             |
| List PERDCOMPs (by Client Id)       | GET    | Auth      | `/api/v1/clients/{client_id}/perdcomps`                     | Lista paginada de PER/DCOMPs de um cliente.                                                     |
| List PERDCOMPs (by Client CNPJ)     | GET    | Auth      | `/api/v1/clients/cnpj/{cnpj}/perdcomps`                     | Lista paginada de PER/DCOMPs por CNPJ do cliente.                                               |
| Search PERDCOMPs                    | GET    | Auth      | `/api/v1/perdcomps`                                         | Lista paginada. Filtros: `?q=&clientId=&status=&createdFrom=&createdTo=&page=&pageSize=&sort=`. |
| Get PERDCOMP by Filter (alias)      | GET    | Auth      | `/api/v1/perdcomps/search`                                  | Buscas avançadas (mesmos filtros de `GET /perdcomps`).                                          |

---

## 4. Administração

### 4.1. Usuários

| Nome                      | Método | Permissão | Rota                                     | Descrição                              |
| ------------------------- | ------ | --------- | ---------------------------------------- | -------------------------------------- |
| List Users                | GET    | Admin     | `/api/v1/admin/users`                    | Lista usuários (paginado, filtros).    |
| Get User by Id            | GET    | Admin     | `/api/v1/admin/users/{user_id}`          | Detalhe de usuário.                    |
| Update User               | PATCH  | Admin     | `/api/v1/admin/users/{user_id}`          | Atualiza atributos (incl. papéis).     |
| Delete User (soft)        | DELETE | Admin     | `/api/v1/admin/users/{user_id}`          | Soft-delete do usuário.                |
| Suspend User              | POST   | Admin     | `/api/v1/admin/users/{user_id}/suspend`  | Suspende usuário (status = suspended). |
| Remove Suspension         | DELETE | Admin     | `/api/v1/admin/users/{user_id}/suspend`  | Remove suspensão.                      |
| Change User Password      | POST   | Admin     | `/api/v1/admin/users/{user_id}/password` | Força redefinição/alteração de senha.  |
| Approve User Registration | POST   | Admin     | `/api/v1/admin/users/{user_id}/approve`  | Aprova cadastro pendente.              |
| Decline User Registration | POST   | Admin     | `/api/v1/admin/users/{user_id}/decline`  | Recusa cadastro pendente.              |

### 4.2. Requests (Aprovações)

| Nome                      | Método | Permissão | Rota                                          | Descrição                                                             |
| ------------------------- | ------ | --------- | --------------------------------------------- | --------------------------------------------------------------------- |
| List Requests (pendentes) | GET    | Admin     | `/api/v1/admin/requests`                      | Lista de requests pendentes (filtros por tipo, entidade, ator, data). |
| Get Request by Id         | GET    | Admin     | `/api/v1/admin/requests/{request_id}`         | Detalhe de uma solicitação.                                           |
| Approve Request           | POST   | Admin     | `/api/v1/admin/requests/{request_id}/approve` | Aprova e executa a ação (transação + auditoria).                      |
| Decline Request           | POST   | Admin     | `/api/v1/admin/requests/{request_id}/decline` | Recusa a ação solicitada (log de auditoria).                          |
| List Requests by User     | GET    | Admin     | `/api/v1/admin/users/{user_id}/requests`      | Filtra requests criadas por um usuário específico.                    |

### 4.3. Logs & Auditoria

| Nome               | Método | Permissão | Rota                                         | Descrição                                                                |
| ------------------ | ------ | --------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| List System Logs   | GET    | Admin     | `/api/v1/admin/logs`                         | Logs de auditoria (paginado, filtros por período, ator, entidade, ação). |
| View User Logs     | GET    | Admin     | `/api/v1/admin/logs/users/{user_id}`         | Logs vinculados a um usuário (ações e eventos).                          |
| View User Actions  | GET    | Admin     | `/api/v1/admin/logs/users/{user_id}/actions` | Ações do usuário sobre clientes/PERDCOMPs (`?entity=client,perdcomp`).   |
| View Client Logs   | GET    | Admin     | `/api/v1/admin/logs/clients/{client_id}`     | Logs relacionados a um cliente específico.                               |
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
