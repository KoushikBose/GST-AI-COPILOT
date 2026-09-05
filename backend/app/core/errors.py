"""Application error hierarchy and FastAPI exception handlers.

Every error returned by the API follows the same envelope:

    {
        "success": false,
        "error": {
            "code": "INVOICE_VALIDATION_FAILED",
            "message": "...",
            "request_id": "..."
        }
    }

Internal stack traces are never exposed to clients. They are logged with the
request_id so they can be correlated server-side.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all application-raised errors.

    Subclass this for domain-specific errors instead of raising bare
    HTTPException, so every error carries a stable machine-readable `code`.
    """

    code: str = "APP_ERROR"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class ValidationFailedError(AppError):
    code = "VALIDATION_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = status.HTTP_403_FORBIDDEN


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = status.HTTP_409_CONFLICT


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class TenantIsolationError(AppError):
    """Raised when a request attempts to access another tenant's data."""

    code = "TENANT_ISOLATION_VIOLATION"
    status_code = status.HTTP_403_FORBIDDEN


class InvoiceValidationError(AppError):
    code = "INVOICE_VALIDATION_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class DependencyUnavailableError(AppError):
    """A downstream dependency (LLM, Qdrant, OCR, etc.) is unavailable."""

    code = "DEPENDENCY_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


def _error_body(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": {"code": code, "message": message, "request_id": request_id},
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            "app_error",
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("HTTP_ERROR", str(exc.detail), request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_body(
                "REQUEST_VALIDATION_FAILED", "The request payload is invalid.", request_id
            )
            | {"details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            request_id=request_id,
            path=request.url.path,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "INTERNAL_SERVER_ERROR",
                "An unexpected error occurred. Our team has been notified.",
                request_id,
            ),
        )
