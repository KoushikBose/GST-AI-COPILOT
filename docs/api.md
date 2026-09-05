# API

Interactive OpenAPI docs: `http://localhost:8000/docs` (Swagger) / `http://localhost:8000/redoc`, disabled when `APP_ENV=production`. Raw schema: `http://localhost:8000/openapi.json`.

## Auth

All endpoints except `/health`, `/ready`, `/auth/register`, `/auth/login`, `/auth/refresh` require `Authorization: Bearer <access_token>`. Endpoints under an organization additionally accept (or default from the token) `X-Organization-ID: <uuid>` — see [docs/security.md](security.md) for how that's verified.

## Error format

Every error response:

```json
{ "success": false, "error": { "code": "INVOICE_VALIDATION_FAILED", "message": "...", "request_id": "..." } }
```

`code` is stable and machine-readable (see `app/core/errors.py` for the full `AppError` hierarchy). `request_id` matches the `X-Request-ID` response header and structured log lines, for support correlation.

## Endpoint groups

| Prefix | Purpose |
|---|---|
| `/api/v1/auth` | register, login, refresh, current user |
| `/api/v1/gst` | deterministic calculate/validate (no LLM, no agent routing) |
| `/api/v1/chat` | agent-routed conversation (`POST /chat`, session listing) |
| `/api/v1/rag` | direct grounded search, bypassing intent routing |
| `/api/v1/documents` | knowledge/tenant document upload, list, reindex, delete |
| `/api/v1/invoices` | upload (OCR+extraction), list, detail, combined analyze |
| `/api/v1/compliance` | standalone compliance check + open issues list |
| `/api/v1/itc` | standalone ITC analysis |
| `/api/v1/reconciliation` | GSTR-2A/2B CSV upload, deterministic reconciliation run, match review, CSV export |

## Rate limits

Auth endpoints are rate-limited per-IP (`slowapi`); see `@limiter.limit(...)` decorators in `app/api/v1/auth.py`. A 429 response follows the same error envelope with `code: "RATE_LIMIT_EXCEEDED"`.
