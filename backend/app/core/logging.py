"""Structured logging setup (structlog).

Every log line is emitted as JSON in production (console-pretty in dev) and
carries a request_id / tenant_id / user_id when available via contextvars,
so logs can be correlated across the API, agents, tools and workers.

Secrets must NEVER be logged. Call `redact` on any dict that might contain
credentials, tokens or PII before logging it.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import get_settings

_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "jwt",
    "access_token",
    "refresh_token",
    "gstin",  # tax-id, mask by default in logs
}


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `data` with sensitive-looking keys masked."""
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact(value)
        else:
            redacted[key] = value
    return redacted


def configure_logging() -> None:
    settings = get_settings()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
