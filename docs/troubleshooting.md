# Troubleshooting

## Backend won't start: `ModuleNotFoundError`

Run `pip install -e ".[dev]"` from `backend/` inside your venv. If you added a new dependency, add it to `backend/pyproject.toml`'s `dependencies` (or `optional-dependencies.dev`) first.

## `email-validator is not installed`

Pydantic's `EmailStr` needs the `email` extra: already declared as `pydantic[email]` in `pyproject.toml` — re-run `pip install -e ".[dev]"` if you see this on an older venv.

## `Multiple top-level packages discovered in a flat-layout`

Happens if `[tool.setuptools.packages.find]` in `pyproject.toml` is missing/changed — it must read `include = ["app*"]` so setuptools doesn't try to also package the sibling `alembic/`, `evaluation/`, `scripts/`, and `tests/` directories.

## `alembic upgrade head` fails to connect

Check `DATABASE_URL` in `.env` points at a reachable Postgres (`docker compose up -d postgres` if running the stack piecemeal). The async engine (`asyncpg`) is used by `alembic/env.py`, so `DATABASE_URL` must be the `postgresql+asyncpg://...` form, not the sync one.

## RAG answers always say "could not establish a sufficiently reliable answer"

Almost always means the relevant Qdrant collection is empty — no documents have been ingested yet for that topic. Upload GST Acts/Rules/Notifications/FAQs via the Documents page or `POST /api/v1/documents/upload` first.

## OCR extraction returns empty/garbage text

- Tesseract (default `OCR_PROVIDER`) needs the native binary installed on the host/image (already included in `backend/Dockerfile`; for non-Docker local dev, install Tesseract separately and optionally set `TESSERACT_CMD`).
- Very low-DPI scans will produce poor OCR confidence — check `invoice.ocr_confidence` / a document chunk's OCR flag before trusting extraction on a borderline scan.

## Ollama requests time out

Increase `OLLAMA_TIMEOUT`, confirm the model is actually pulled (`docker exec gst_ollama ollama list`), and check host resources — a 7B model needs real RAM/CPU (or GPU) headroom; the first request after a pull/restart also pays a one-time model-load cost.

## `ruff check` reports import-sort issues after editing

Run `ruff format <file>` first, then `ruff check <file> --fix` — most of what looks like a style nit is actually ruff's `I001` import-block sort, which it can fix itself.
