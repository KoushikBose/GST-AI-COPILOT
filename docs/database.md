# Database

PostgreSQL 16, 30 tables, all UUID primary keys, `created_at`/`updated_at` on every table via `TimestampMixin`. See `backend/app/models/` — one file per domain, all imported and re-exported from `app/models/__init__.py` (required for Alembic autogenerate to see every table).

## Multi-tenancy

`TenantScopedMixin` (`app/models/mixins.py`) adds an indexed, `NOT NULL`, `ON DELETE CASCADE` `organization_id` FK to every tenant-owned table (invoices, documents' tenant variant, chat sessions, agent runs, compliance checks, ITC records, approvals, notifications, audit logs, ...). `documents.organization_id` is nullable by design — `NULL` means global/public GST knowledge, not "no tenant."

## Enum storage gotcha (already fixed, documented so it isn't reintroduced)

SQLAlchemy's `Enum(SomePythonEnum)` persists the enum **member name** (`"ORG_ADMIN"`) by default, not `.value` (`"org_admin"`) — which would silently diverge from every other layer (JWT payloads, JSON API responses, `StrEnum.__str__`) that serializes by value. Every enum column in this schema goes through `str_enum_column()` (`app/models/mixins.py`), which sets `values_callable` to persist `.value`. Use it for any new enum column instead of `sqlalchemy.Enum(...)` directly.

## Key tables

| Table | Purpose |
|---|---|
| `organizations`, `organization_members`, `gst_profiles` | Tenancy + RBAC + GST registration |
| `users` | Auth identity (credentials only; role lives on membership) |
| `documents`, `document_versions`, `document_chunks` | Knowledge base + versioning + Qdrant provenance |
| `customers`, `vendors` | Per-tenant master data |
| `invoices`, `invoice_items`, `invoice_taxes` | Invoice AI output |
| `gst_transactions`, `tax_calculations`, `itc_records` | Deterministic engine outputs, persisted for audit |
| `compliance_checks`, `compliance_issues` | Compliance Agent output |
| `chat_sessions`, `chat_messages` | Durable conversation history |
| `agent_runs`, `agent_events` | Agent observability/audit trail |
| `review_tasks` | Human-in-the-loop approval queue |
| `audit_logs` | Append-only action log |
| `notifications`, `system_settings` | Supporting tables |

## Migrations

The first migration (`0001_initial_schema`) builds the schema from `Base.metadata.create_all()` rather than hand-transcribed `op.create_table()` calls — correct and standard practice for a from-scratch initial migration since it's generated verbatim from the ORM, with zero risk of manual transcription drift. Every migration after this one must be generated the normal way against a live database: `make migrate-new name="..."`.
