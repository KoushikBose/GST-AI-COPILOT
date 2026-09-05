"""JWT access/refresh token issuance and verification.

Access tokens carry the active organization + role so downstream RBAC checks
don't need an extra database round-trip on every request. Refresh tokens
carry only the user identity and a token family id so they can be rotated
and revoked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from pydantic import BaseModel

from app.config import get_settings


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    sub: str  # user_id
    type: TokenType
    org_id: str | None = None
    role: str | None = None
    jti: str
    exp: datetime
    iat: datetime


class InvalidTokenError(Exception):
    pass


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: uuid.UUID, *, organization_id: uuid.UUID | None = None, role: str | None = None
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": TokenType.ACCESS.value,
        "org_id": str(organization_id) if organization_id else None,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return _encode(payload)


def create_refresh_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": TokenType.REFRESH.value,
        "org_id": None,
        "role": None,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return _encode(payload)


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    settings = get_settings()
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Token is invalid.") from exc

    payload = TokenPayload.model_validate(raw)
    if payload.type != expected_type:
        raise InvalidTokenError(f"Expected a {expected_type.value} token.")
    return payload
