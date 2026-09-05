"""Shared rate limiter instance.

A single `Limiter` must be reused across `main.py` (where it's attached to
`app.state.limiter` and wired to the 429 handler) and every router that uses
the `@limiter.limit(...)` decorator — two separate instances would track
independent counters and the decorator would not share state with the
app-level exception handler.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    default_limits=[settings.rate_limit_default],
)
