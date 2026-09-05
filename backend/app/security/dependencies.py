"""FastAPI dependencies for authentication and role-based authorization.

Design note: the JWT's embedded organization_id/role are treated only as a
*default* org context, never as authorization by themselves. Every request
that touches tenant data re-verifies active membership (and current role)
against the database via `get_current_membership`. This means a role change
or membership revocation takes effect immediately instead of waiting for
token expiry, and a client cannot escalate access by sending an
`X-Organization-ID` header for an org it isn't a member of.

`CurrentMembership` is bound into structlog context so every log line for a
request is tagged with user_id/organization_id — required for auditability
and for correlating agent/tool activity back to the acting tenant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.models.rbac import OrganizationMember, OrgRole
from app.security.jwt import InvalidTokenError, TokenType, decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: uuid.UUID
    default_organization_id: uuid.UUID | None


@dataclass(frozen=True)
class CurrentMembership:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: OrgRole


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    return AuthenticatedUser(
        user_id=uuid.UUID(payload.sub),
        default_organization_id=uuid.UUID(payload.org_id) if payload.org_id else None,
    )


async def get_current_membership(
    auth_user: AuthenticatedUser = Depends(get_authenticated_user),
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentMembership:
    """Resolve and DB-verify the active org membership for this request.

    Falls back to the org embedded in the access token when no
    X-Organization-ID header is supplied; either way, membership is looked
    up fresh so a stale/forged header can never grant access to an org the
    user does not belong to.
    """
    requested_org_id = (
        uuid.UUID(x_organization_id) if x_organization_id else auth_user.default_organization_id
    )
    if requested_org_id is None:
        raise UnauthorizedError("An active organization context is required.")

    stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == auth_user.user_id,
        OrganizationMember.organization_id == requested_org_id,
        OrganizationMember.is_active.is_(True),
    )
    result = await session.execute(stmt)
    membership = result.scalar_one_or_none()
    if membership is None:
        raise ForbiddenError("You are not an active member of this organization.")

    principal = CurrentMembership(
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        role=membership.role,
    )
    structlog.contextvars.bind_contextvars(
        user_id=str(principal.user_id),
        organization_id=str(principal.organization_id),
        role=principal.role.value,
    )
    return principal


def require_roles(*allowed_roles: OrgRole):
    async def _checker(
        membership: CurrentMembership = Depends(get_current_membership),
    ) -> CurrentMembership:
        if membership.role not in allowed_roles:
            raise ForbiddenError("You do not have permission to perform this action.")
        return membership

    return _checker
