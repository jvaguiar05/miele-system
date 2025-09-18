# Miele System Database Tables Guide

This document provides a comprehensive overview of the custom database tables for the **Miele System**. These tables are designed to reflect the system's models and core business logic. The complete database schema also includes essential Django library tables, such as:

- **Django ContentTypes**
- **Django Permissions/Groups**
- **SimpleJWT Blacklist**
- **django-otp** (TOTP + static codes)
- **Django Admin Log** (basic)
- **DRF API Key** (basic)

> **Note:** Library tables are referenced but not defined here. Only custom tables are detailed below.

---

## Table of Contents

1. [Enums](#enums)
2. [Custom Tables](#custom-tables)
   - [identity_user](#identity_user)
   - [clients](#clients)
   - [client_address](#client_address)
   - [perdcomps](#perdcomps)
   - [app_notes](#app_notes)
   - [app_files](#app_files)
   - [app_approval_requests](#app_approval_requests)
   - [audit_log](#audit_log)
   - [Optional Tables](#optional-tables)
     - [outbox_email](#outbox_email)
     - [cnpj_check](#cnpj_check)

---

## Enums

Custom enums used for table fields:

```dbml
Enum user_approval_status { pending, approved, declined }
Enum client_status { pending, active, suspended, archived }
Enum tax_regime { LucroReal, LucroPresumido }
Enum perdcomp_status { pending, active, archived }
Enum request_status { pending, approved, declined }
Enum approval_subject { user, client, perdcomp }
Enum approval_action {
  user_activate, user_decline,
  client_sensitive_update, client_delete,
  perdcomp_sensitive_update, perdcomp_delete
}
Enum file_owner { client, perdcomp }
Enum file_kind { generic, recibo, pedido_recebimento, perdcomp_summary }
Enum storage_backend { local, s3 }
```

---

## Custom Tables

### identity_user

Custom user model (`AUTH_USER_MODEL="identity.User"`).

- Stores authentication and profile data.
- Tracks approval status, suspension, and soft deletion.

**Key Fields:**

- `id`, `username`, `email`, `password`
- `approval_status`, `suspended_at`, `deleted_at`
- Timestamps: `created_at`, `updated_at`, `date_joined`

**Indexes:**

- Unique: `email`, `username`
- Others: `is_active`, `date_joined`, `deleted_at`

---

### clients

Represents client organizations.

- Identification, contacts, and legal attributes.
- Supports multiple attributes via arrays.
- Tracks regime, documents, and authorship.

**Key Fields:**

- `id`, `public_id`, `razao_social`, `cnpj`
- `regime_tributacao`, `status`
- Authorship: `colaborador_id`, `created_by_id`, `updated_by_id`
- Timestamps: `created_at`, `updated_at`, `deleted_at`

**Indexes:**

- Unique: `public_id`
- Others: `cnpj`, `status`, `colaborador_id`

> **Note:** CNPJ uniqueness enforced among active records via partial unique index.

---

### client_address

Stores a single address per client (no branches in MVP).

**Key Fields:**

- `id`, `client_id`
- Address: `logradouro`, `numero`, `bairro`, `municipio`, `uf`, `cep`
- Timestamps: `created_at`, `updated_at`, `deleted_at`

**Indexes:**

- Unique: `client_id` (1:1 relationship)
- Others: `cep`, `deleted_at`

---

### perdcomps

Represents Perdcomp requests.

- Linked to clients and collaborators.
- Tracks identification, dates, values, and status.

**Key Fields:**

- `id`, `public_id`, `client_id`, `colaborador_id`
- Tax info: `cnpj`, `competencia`, `valor_pedido`, etc.
- Timestamps: `created_at`, `updated_at`, `deleted_at`

**Indexes:**

- Unique: `public_id`
- Others: `client_id`, `colaborador_id`, `cnpj`, `competencia`

> **Note:** Uniqueness for `(client_id, cnpj, competencia)` among active records.

---

### app_notes

Generic notes linked via Django ContentTypes.

**Key Fields:**

- `id`, `public_id`, `content_type_id`, `object_id`
- `author_id`, `content`
- Timestamps: `created_at`, `updated_at`, `deleted_at`

**Indexes:**

- Unique: `public_id`
- Others: `(content_type_id, object_id)`, `author_id`

---

### app_files

Generic files with type and owner.

**Key Fields:**

- `id`, `public_id`, `content_type_id`, `object_id`
- `owner`, `kind`, `uploaded_by_id`
- File info: `filename`, `content_type`, `size_bytes`, `checksum_sha256`, `backend`, `storage_path`
- Timestamps: `created_at`, `deleted_at`

**Indexes:**

- Unique: `public_id`
- Others: `(content_type_id, object_id)`, `(owner, kind)`, `uploaded_by_id`, `checksum_sha256`

---

### app_approval_requests

Tracks approval requests for users, clients, and perdcomps.

**Key Fields:**

- `id`, `public_id`, `subject`, `content_type_id`, `object_id`
- `action`, `status`, `requested_by_id`, `approved_by_id`
- `reason`, `payload_diff`, `correlation_id`
- Timestamps: `created_at`, `decided_at`

**Indexes:**

- Unique: `public_id`, `correlation_id`
- Others: `(subject, status, created_at)`, `(content_type_id, object_id)`

---

### audit_log

Immutable audit log for system actions.

**Key Fields:**

- `id`, `public_id`, `actor_id`, `action`
- `content_type_id`, `object_id`, `payload_diff`, `reason`, `correlation_id`
- `ip`, `user_agent`
- Timestamp: `created_at`

**Indexes:**

- Unique: `public_id`
- Others: `actor_id`, `(content_type_id, object_id)`, `created_at`, `correlation_id`

---

## Optional Tables

### outbox_email

Tracks outgoing emails.

**Key Fields:**

- `id`, `to_email`, `subject`, `body`, `status`, `attempts`, `last_error`
- Timestamps: `scheduled_at`, `sent_at`, `created_at`

---

### cnpj_check

Stores results of CNPJ checks from external services.

**Key Fields:**

- `id`, `client_id`, `cnpj`, `result_json`, `status`
- Timestamp: `checked_at`

---

## Integration with Django Library Tables

The full database schema includes references to Django's built-in tables for authentication, permissions, content types, API keys, and audit logging. These are essential for system integrity, security, and extensibility.

---

## Notes

- All custom tables support soft deletion via `deleted_at` where applicable.
- Timestamps (`created_at`, `updated_at`) are used for audit and tracking.
- Partial unique indexes are used for business rules (e.g., CNPJ uniqueness).
- Array fields are used for multi-value attributes (e.g., `quadro_societario`).

---

## Appendix

For details on Django library tables, refer to the official [Django documentation](https://docs.djangoproject.com/en/stable/topics/db/models/).
