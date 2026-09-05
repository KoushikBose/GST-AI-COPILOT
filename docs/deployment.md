# Deployment

## Local development

```bash
docker compose up -d --build
docker exec gst_ollama ollama pull qwen2.5:7b-instruct
docker exec gst_backend alembic upgrade head
```

See the [README](../README.md#quick-start-docker) for the full walkthrough.

## Production

The same `backend/Dockerfile` and `frontend/Dockerfile` are cloud-agnostic multi-stage builds — no code changes are needed to deploy them anywhere that runs containers. There is no Kubernetes manifest/Helm chart in this repository yet (see [README's Known Limitations](../README.md#known-limitations)); to deploy:

1. Build and push both images (`docker build -t <registry>/gst-copilot-backend ./backend`, similarly for `frontend`).
2. Provision Postgres, Redis, Qdrant, MinIO (or S3), and Ollama (or point `LLM_PROVIDER=openai` at a managed endpoint) — self-hosted or managed, your choice.
3. Set the full `.env` variable set as your platform's secrets/config (never bake secrets into the image).
4. Run `alembic upgrade head` as a one-off job before traffic is routed to a new backend version.
5. Point the backend's `/health` (liveness) and `/ready` (readiness — checks Postgres/Redis/Qdrant connectivity) at your orchestrator's health-check config.
6. Set `APP_ENV=production` (disables `/docs`/`/redoc`) and use a real, long, random `APP_SECRET_KEY`/`JWT_SECRET`.

## Scaling notes

- The backend is a stateless FastAPI app — scale horizontally behind a load balancer.
- Swap LangGraph's `MemorySaver` for a Postgres-backed checkpointer (`langgraph-checkpoint-postgres`) before running more than one backend replica — see the docstring on `get_compiled_supervisor_graph()` in `app/agents/graph.py`.
- Celery workers (`worker`, `worker-beat` in `docker-compose.yml`) scale independently of the API.
