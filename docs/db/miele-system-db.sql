CREATE TYPE "user_approval_status" AS ENUM (
  'pending',
  'approved',
  'declined'
);

CREATE TYPE "client_status" AS ENUM (
  'pending',
  'active',
  'suspended',
  'archived'
);

CREATE TYPE "tax_regime" AS ENUM (
  'LucroReal',
  'LucroPresumido'
);

CREATE TYPE "perdcomp_status" AS ENUM (
  'pending',
  'active',
  'archived'
);

CREATE TYPE "request_status" AS ENUM (
  'pending',
  'approved',
  'declined'
);

CREATE TYPE "approval_subject" AS ENUM (
  'user',
  'client',
  'perdcomp'
);

CREATE TYPE "approval_action" AS ENUM (
  'user_activate',
  'user_decline',
  'client_sensitive_update',
  'client_delete',
  'perdcomp_sensitive_update',
  'perdcomp_delete'
);

CREATE TYPE "file_owner" AS ENUM (
  'client',
  'perdcomp'
);

CREATE TYPE "file_kind" AS ENUM (
  'generic',
  'recibo',
  'pedido_recebimento',
  'perdcomp_summary'
);

CREATE TYPE "storage_backend" AS ENUM (
  'local',
  's3'
);

CREATE TABLE "identity_user" (
  "id" bigserial PRIMARY KEY,
  "password" varchar(128) NOT NULL,
  "last_login" timestamptz,
  "is_superuser" boolean NOT NULL DEFAULT false,
  "username" varchar(150) UNIQUE NOT NULL,
  "first_name" varchar(150) NOT NULL DEFAULT '',
  "last_name" varchar(150) NOT NULL DEFAULT '',
  "email" varchar(254) UNIQUE NOT NULL,
  "is_staff" boolean NOT NULL DEFAULT false,
  "is_active" boolean NOT NULL DEFAULT true,
  "date_joined" timestamptz NOT NULL DEFAULT (now()),
  "approval_status" user_approval_status NOT NULL DEFAULT 'pending',
  "approval_decided_at" timestamptz,
  "suspended_at" timestamptz,
  "suspended_by_id" bigint,
  "suspension_reason" text,
  "public_id" uuid DEFAULT (gen_random_uuid()),
  "deleted_at" timestamptz,
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "updated_at" timestamptz NOT NULL DEFAULT (now())
);

CREATE TABLE "clients" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "razao_social" text NOT NULL,
  "nome_fantasia" text,
  "cnpj" varchar(14) NOT NULL,
  "inscricao_estadual" varchar(32),
  "inscricao_municipal" varchar(32),
  "tipo_de_empresa" text,
  "recuperacao_judicial" boolean NOT NULL DEFAULT false,
  "telefone_comercial" varchar(32),
  "email_comercial" varchar(254),
  "website" text,
  "telefone_contato" varchar(32),
  "email_contato" varchar(254),
  "responsavel_financeiro" text,
  "contador_responsavel" text,
  "quadro_societario" text[],
  "cargos_socios" text[],
  "cnae" text[],
  "atividades" text[],
  "rg_cpf_socios" text[],
  "regime_tributacao" tax_regime,
  "contrato_social" text,
  "ultima_alt_contratual" timestamptz,
  "certificado_digital" text,
  "status" client_status NOT NULL DEFAULT 'pending',
  "colaborador_id" bigint,
  "created_by_id" bigint NOT NULL,
  "updated_by_id" bigint,
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "updated_at" timestamptz NOT NULL DEFAULT (now()),
  "deleted_at" timestamptz
);

CREATE TABLE "client_address" (
  "id" bigserial PRIMARY KEY,
  "client_id" bigint NOT NULL,
  "logradouro" text NOT NULL,
  "numero" varchar(16),
  "complemento" text,
  "bairro" text,
  "municipio" text,
  "uf" varchar(2),
  "cep" varchar(8),
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "updated_at" timestamptz NOT NULL DEFAULT (now()),
  "deleted_at" timestamptz
);

CREATE TABLE "perdcomps" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "client_id" bigint NOT NULL,
  "colaborador_id" bigint NOT NULL,
  "cnpj" varchar(14) NOT NULL,
  "numero" varchar(64),
  "numero_perdcomp" varchar(64),
  "processo_protocolo" text,
  "data_transmissao" date,
  "data_vencimento" date,
  "competencia" varchar(7),
  "data_competencia" date,
  "tributo_pedido" text,
  "valor_pedido" numeric(15,2),
  "valor_compensado" numeric(15,2),
  "valor_recebido" numeric(15,2),
  "valor_saldo" numeric(15,2),
  "valor_selic" numeric(15,2),
  "status" perdcomp_status NOT NULL DEFAULT 'pending',
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "updated_at" timestamptz NOT NULL DEFAULT (now()),
  "deleted_at" timestamptz
);

CREATE TABLE "app_notes" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "content_type_id" int NOT NULL,
  "object_id" bigint NOT NULL,
  "author_id" bigint NOT NULL,
  "content" text NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "updated_at" timestamptz NOT NULL DEFAULT (now()),
  "deleted_at" timestamptz
);

CREATE TABLE "app_files" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "content_type_id" int NOT NULL,
  "object_id" bigint NOT NULL,
  "owner" file_owner NOT NULL,
  "kind" file_kind NOT NULL DEFAULT 'generic',
  "uploaded_by_id" bigint NOT NULL,
  "filename" varchar(255) NOT NULL,
  "content_type" varchar(150) NOT NULL,
  "size_bytes" bigint NOT NULL,
  "checksum_sha256" varchar(64) NOT NULL,
  "backend" storage_backend NOT NULL DEFAULT 'local',
  "storage_path" text NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "deleted_at" timestamptz
);

CREATE TABLE "app_approval_requests" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "subject" approval_subject NOT NULL,
  "content_type_id" int NOT NULL,
  "object_id" bigint NOT NULL,
  "action" approval_action NOT NULL,
  "status" request_status NOT NULL DEFAULT 'pending',
  "requested_by_id" bigint NOT NULL,
  "approved_by_id" bigint,
  "reason" text,
  "payload_diff" jsonb,
  "correlation_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "created_at" timestamptz NOT NULL DEFAULT (now()),
  "decided_at" timestamptz
);

CREATE TABLE "audit_log" (
  "id" bigserial PRIMARY KEY,
  "public_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "actor_id" bigint,
  "action" varchar(64),
  "content_type_id" int NOT NULL,
  "object_id" bigint NOT NULL,
  "payload_diff" jsonb,
  "reason" text,
  "correlation_id" uuid NOT NULL DEFAULT (gen_random_uuid()),
  "ip" varchar(45),
  "user_agent" text,
  "created_at" timestamptz NOT NULL DEFAULT (now())
);

CREATE TABLE "outbox_email" (
  "id" bigserial PRIMARY KEY,
  "to_email" varchar(254) NOT NULL,
  "subject" text,
  "body" text,
  "status" varchar(32),
  "attempts" int NOT NULL DEFAULT 0,
  "last_error" text,
  "scheduled_at" timestamptz,
  "sent_at" timestamptz,
  "created_at" timestamptz NOT NULL DEFAULT (now())
);

CREATE TABLE "cnpj_check" (
  "id" bigserial PRIMARY KEY,
  "client_id" bigint,
  "cnpj" varchar(14),
  "result_json" jsonb,
  "status" varchar(32),
  "checked_at" timestamptz NOT NULL DEFAULT (now())
);

CREATE UNIQUE INDEX ON "identity_user" ("email");

CREATE UNIQUE INDEX ON "identity_user" ("username");

CREATE INDEX ON "identity_user" ("is_active");

CREATE INDEX ON "identity_user" ("date_joined");

CREATE INDEX ON "identity_user" ("deleted_at");

CREATE UNIQUE INDEX ON "clients" ("public_id");

CREATE INDEX ON "clients" ("cnpj");

CREATE INDEX ON "clients" ("status");

CREATE INDEX ON "clients" ("created_at");

CREATE INDEX ON "clients" ("deleted_at");

CREATE INDEX ON "clients" ("colaborador_id");

CREATE INDEX ON "clients" ("created_by_id");

CREATE UNIQUE INDEX ON "client_address" ("client_id");

CREATE INDEX ON "client_address" ("cep");

CREATE INDEX ON "client_address" ("deleted_at");

CREATE UNIQUE INDEX ON "perdcomps" ("public_id");

CREATE INDEX ON "perdcomps" ("client_id");

CREATE INDEX ON "perdcomps" ("colaborador_id");

CREATE INDEX ON "perdcomps" ("cnpj");

CREATE INDEX ON "perdcomps" ("competencia");

CREATE INDEX ON "perdcomps" ("status", "created_at");

CREATE INDEX ON "perdcomps" ("created_at");

CREATE INDEX ON "perdcomps" ("deleted_at");

CREATE UNIQUE INDEX ON "app_notes" ("public_id");

CREATE INDEX ON "app_notes" ("content_type_id", "object_id");

CREATE INDEX ON "app_notes" ("author_id");

CREATE INDEX ON "app_notes" ("created_at");

CREATE INDEX ON "app_notes" ("deleted_at");

CREATE UNIQUE INDEX ON "app_files" ("public_id");

CREATE INDEX ON "app_files" ("content_type_id", "object_id");

CREATE INDEX ON "app_files" ("owner", "kind");

CREATE INDEX ON "app_files" ("uploaded_by_id");

CREATE INDEX ON "app_files" ("checksum_sha256");

CREATE INDEX ON "app_files" ("created_at");

CREATE INDEX ON "app_files" ("deleted_at");

CREATE UNIQUE INDEX ON "app_approval_requests" ("public_id");

CREATE INDEX ON "app_approval_requests" ("subject", "status", "created_at");

CREATE INDEX ON "app_approval_requests" ("content_type_id", "object_id");

CREATE INDEX ON "app_approval_requests" ("requested_by_id");

CREATE INDEX ON "app_approval_requests" ("approved_by_id");

CREATE UNIQUE INDEX ON "app_approval_requests" ("correlation_id");

CREATE UNIQUE INDEX ON "audit_log" ("public_id");

CREATE INDEX ON "audit_log" ("actor_id");

CREATE INDEX ON "audit_log" ("content_type_id", "object_id");

CREATE INDEX ON "audit_log" ("created_at");

CREATE INDEX ON "audit_log" ("correlation_id");

COMMENT ON TABLE "identity_user" IS 'Custom User (AUTH_USER_MODEL="identity.User").';

COMMENT ON TABLE "clients" IS 'Make CNPJ unique among active records via partial UNIQUE (WHERE deleted_at IS NULL) in SQL migration.';

COMMENT ON TABLE "client_address" IS 'No branch concept in MVP; 1 address per client.';

COMMENT ON TABLE "perdcomps" IS 'Make (client_id, cnpj, competencia) unique among active records via partial UNIQUE (WHERE deleted_at IS NULL) in SQL migration.';

COMMENT ON TABLE "app_notes" IS 'Generic notes via ContentTypes.';

COMMENT ON TABLE "app_files" IS 'Generic files with type and owner.';

COMMENT ON TABLE "app_approval_requests" IS 'Generic approval requests for user/client/perdcomp.';

COMMENT ON TABLE "audit_log" IS 'Immutable by policy; corrections are new records.';

COMMENT ON TABLE "cnpj_check" IS 'Store results of CNPJ checks from external services.';

ALTER TABLE "clients" ADD FOREIGN KEY ("colaborador_id") REFERENCES "identity_user" ("id");

ALTER TABLE "clients" ADD FOREIGN KEY ("created_by_id") REFERENCES "identity_user" ("id");

ALTER TABLE "clients" ADD FOREIGN KEY ("updated_by_id") REFERENCES "identity_user" ("id");

ALTER TABLE "client_address" ADD FOREIGN KEY ("client_id") REFERENCES "clients" ("id");

ALTER TABLE "perdcomps" ADD FOREIGN KEY ("client_id") REFERENCES "clients" ("id");

ALTER TABLE "perdcomps" ADD FOREIGN KEY ("colaborador_id") REFERENCES "identity_user" ("id");

ALTER TABLE "app_notes" ADD FOREIGN KEY ("author_id") REFERENCES "identity_user" ("id");

ALTER TABLE "app_files" ADD FOREIGN KEY ("uploaded_by_id") REFERENCES "identity_user" ("id");

ALTER TABLE "app_approval_requests" ADD FOREIGN KEY ("requested_by_id") REFERENCES "identity_user" ("id");

ALTER TABLE "app_approval_requests" ADD FOREIGN KEY ("approved_by_id") REFERENCES "identity_user" ("id");

ALTER TABLE "audit_log" ADD FOREIGN KEY ("actor_id") REFERENCES "identity_user" ("id");

ALTER TABLE "cnpj_check" ADD FOREIGN KEY ("client_id") REFERENCES "clients" ("id");
