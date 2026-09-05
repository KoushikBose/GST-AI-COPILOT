"""Vercel entrypoint shim.

Vercel's FastAPI detection runs from the repository root, but the application
package lives in ``backend/`` and imports itself as ``app.*``. Put ``backend/``
on ``sys.path`` and re-export the real ASGI app so those imports resolve.

The clean alternative is to set the Vercel project's Root Directory to
``backend/``; this file exists for the case where that setting can't be changed.
"""

from __future__ import annotations

import os
import sys

_BACKEND = os.path.join(os.path.dirname(__file__), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.main import app  # noqa: E402

__all__ = ["app"]
