"""Liveness / readiness / health endpoints.

- /health  — liveness: process is up. Used by Docker HEALTHCHECK.
- /ready   — readiness: all critical dependencies are reachable.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.core.database import check_database_health
from app.core.redis_client import check_redis_health
from app.rag.vector_store import check_qdrant_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, object]:
    settings = get_settings()

    db_ok = await check_database_health()
    redis_ok = await check_redis_health()
    qdrant_ok = await check_qdrant_health()

    checks = {
        "database": db_ok,
        "redis": redis_ok,
        "qdrant": qdrant_ok,
    }
    overall = all(checks.values())

    return {
        "status": "ready" if overall else "degraded",
        "environment": settings.app_env,
        "checks": checks,
    }
