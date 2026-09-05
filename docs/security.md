# Security

See also the [README's Security section](../README.md#security) for a summary.

## Authentication & authorization

- JWT access (30 min default) + refresh (14 day default) tokens, `app/security/jwt.py`.
- **Every request re-verifies organization membership against the database** (`get_current_membership`, `app/security/dependencies.py`) — the JWT's embedded `org_id`/`role` are only a default hint. This means: a role change or membership revocation takes effect on the very next request (not after token expiry), and a client cannot escalate access by sending a forged `X-Organization-ID` header, because that header only selects *which* membership to look up, never bypasses the lookup itself.
- `require_roles(*roles)` dependency for endpoint-level RBAC (e.g. document delete/reindex requires `ADMIN_ROLES`).

## Passwords

Bcrypt via `passlib` (`app/security/passwords.py`). Never logged, never returned in any API response.

## File upload validation

`app/security/file_validation.py`: extension allowlist (`ALLOWED_UPLOAD_EXTENSIONS`), max size (`MAX_UPLOAD_SIZE_MB`), and **magic-byte content sniffing** — a file's actual bytes must match its claimed extension (a `.pdf` that's actually a PNG is rejected), not just its client-supplied filename/Content-Type, which are trivially spoofable.

## GSTIN validation

`app/rules/gstin_validator.py` implements the real GSTIN structural checksum algorithm (mod-36, weighted alternating factor), verified against a publicly documented sample GSTIN in `tests/unit/test_gstin_validator.py`. It validates *format*, not live registration status with GSTN (that would require an external API integration, out of scope here).

## Rate limiting

`slowapi`, shared `Limiter` instance (`app/core/rate_limit.py`) wired into `app.state.limiter` and applied per-route via `@limiter.limit(...)` on auth endpoints.

## Logging & PII

`app/core/logging.py`'s `redact()` masks any dict key containing `password`, `secret`, `token`, `authorization`, `api_key`, `jwt`, or `gstin` before logging. Structured JSON logs carry `request_id`/`user_id`/`organization_id` via `structlog.contextvars` for correlation without needing to log the actual JWT.

## Secrets

Every credential is environment-variable driven (see `.env.example`); nothing is hard-coded. `.gitignore` excludes `.env*` except `.env.example`.

## Guardrails on AI output

- RAG answers require in-text citations; citations pointing outside the retrieved set are discarded before being shown (`app/rag/pipeline.py::_extract_cited_indices`).
- Low-confidence or zero-citation answers get the exact "could not establish a sufficiently reliable answer" disclaimer and are flagged `requires_human_review`.
- ITC assessments never assert unconditional eligibility from a single invoice — see `app/services/itc_service.py`'s module docstring for the reasoning.
- The GST calculation node extracts parameters via the LLM but always computes the actual tax through the deterministic `GSTCalculator` — never an LLM-generated number.
