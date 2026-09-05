"""FastAPI application entrypoint / app factory.

Run locally with:
    uvicorn app.main:app --reload

The app factory wires together configuration, logging, database, security
middleware, rate limiting, observability and all API routers. Business logic
lives in services/agents/rules — this module only assembles infrastructure.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.config import Settings, get_settings
from app.core.database import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import limiter
from app.core.redis_client import close_redis

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("app_startup", environment=settings.app_env, role=settings.service_role)

    # Best-effort: create the Qdrant knowledge collections if they don't
    # exist yet. A vector-store outage must not stop the API from booting —
    # ingestion will surface the problem per-request instead.
    try:
        from app.rag.vector_store import ensure_collections

        await ensure_collections()
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_bootstrap_failed", error=str(exc))

    yield
    logger.info("app_shutdown")
    await dispose_engine()
    await close_redis()

    # Release the embedded-Qdrant folder lock (no-op in server mode) so a
    # restart doesn't collide with the outgoing process.
    try:
        from app.rag.vector_store import close_qdrant

        await close_qdrant()
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_shutdown_close_failed", error=str(exc))


def _cors_allowed_origins(settings: Settings) -> list[str]:
    """Origins the browser is allowed to call this API from.

    `localhost` and `127.0.0.1` are different origins under the CORS spec
    even though they resolve to the same machine — a frontend opened at one
    and configured (or defaulting) to the other gets silently blocked with
    no server-side error, which just looks like "the API is unreachable".
    Worse, `next dev` silently moves to the next free port (3001, 3002, ...)
    whenever something else already holds 3000 — an easy thing to end up
    with with more than one terminal open. In non-production, allow both
    hostnames across a small range of likely dev ports so that class of
    mismatch can't manifest as "the API is unreachable" at all. In
    production, only the exact configured origin is allowed — no widening.
    """
    origins = [settings.frontend_base_url]
    if settings.is_production:
        return origins

    parsed = urlparse(settings.frontend_base_url)
    if parsed.hostname in ("localhost", "127.0.0.1") and parsed.port:
        for host in ("localhost", "127.0.0.1"):
            for port in range(parsed.port, parsed.port + 5):
                origin = f"{parsed.scheme}://{host}:{port}"
                if origin not in origins:
                    origins.append(origin)
    return origins


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "GST AI Copilot API — agentic AI, RAG, deterministic GST rules, "
            "invoice intelligence and compliance automation."
        ),
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SlowAPIMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix="/api/v1")

    if settings.prometheus_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    if settings.otel_enabled:
        _configure_otel(app, settings)

    return app


def _configure_otel(app: FastAPI, settings) -> None:  # noqa: ANN001
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={SERVICE_NAME: settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover - observability must never break the app
        logger.warning("otel_setup_failed", error=str(exc))


app = create_app()
