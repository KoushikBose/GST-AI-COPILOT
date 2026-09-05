.PHONY: setup dev dev-backend dev-frontend run-backend stop-backend test test-backend \
        test-frontend lint format migrate migrate-new seed evaluate docker-up docker-down \
        docker-build docker-logs ingest ollama-pull

PYTHON ?= python
BACKEND_DIR := backend
FRONTEND_DIR := frontend

## Install all dependencies for local (non-Docker) development
setup:
	cd $(BACKEND_DIR) && $(PYTHON) -m venv .venv
	cd $(BACKEND_DIR) && .venv/Scripts/pip install -e ".[dev]" || .venv/bin/pip install -e ".[dev]"
	cd $(FRONTEND_DIR) && npm install

## Run backend + frontend concurrently (requires two terminals normally;
## this target just documents the two commands)
dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals."

dev-backend:
	cd $(BACKEND_DIR) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Backend WITHOUT --reload. Use this when QDRANT_LOCAL_PATH (embedded Qdrant)
## is set — the reloader leaves stray workers that then fight over the
## single-writer storage-folder lock.
run-backend:
	cd $(BACKEND_DIR) && uvicorn app.main:app --host 0.0.0.0 --port 8000

## Kill every stray uvicorn/backend process (incl. --reload spawn workers) and
## clear a stale embedded-Qdrant lock. Run this if you see "Storage folder ...
## is already accessed by another instance of Qdrant client".
stop-backend:
	powershell -NoProfile -ExecutionPolicy Bypass -File "$(BACKEND_DIR)/scripts/stop_local_backend.ps1" || \
	  (pkill -f "uvicorn app.main:app" 2>/dev/null; rm -f "$(BACKEND_DIR)/.data/qdrant/.lock")

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && pytest -v --cov=app --cov-report=term-missing

test-frontend:
	cd $(FRONTEND_DIR) && npm run test

lint:
	cd $(BACKEND_DIR) && ruff check app tests
	cd $(FRONTEND_DIR) && npm run lint

format:
	cd $(BACKEND_DIR) && ruff format app tests
	cd $(BACKEND_DIR) && ruff check --fix app tests

migrate:
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-new:
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(name)"

seed:
	cd $(BACKEND_DIR) && $(PYTHON) -m scripts.seed_sample_data

evaluate:
	cd $(BACKEND_DIR) && $(PYTHON) -m evaluation.run_evaluation

ingest:
	cd $(BACKEND_DIR) && $(PYTHON) -m scripts.ingest_gst_documents --path ../data/knowledge

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-build:
	docker compose build

docker-logs:
	docker compose logs -f

ollama-pull:
	docker exec gst_ollama ollama pull $(OLLAMA_MODEL)
