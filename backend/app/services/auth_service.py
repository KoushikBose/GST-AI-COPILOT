"""Registration, login and token-refresh business logic.

Kept deliberately free of FastAPI request/response objects so it can be unit
tested and reused from non-HTTP entrypoints (e.g. a future WhatsApp/voice
channel adapter that authenticates on the user's behalf).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, UnauthorizedError, ValidationFailedError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.organization import Organization
from app.models.rbac import OrganizationMember, OrgRole
from app.models.user import User
from app.security.jwt import TokenType, create_access_token, create_refresh_token, decode_token
from app.security.passwords import hash_password, verify_password

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self, *, email: str, password: str, full_name: str, organization_name: str
    ) -> tuple[User, Organization, OrganizationMember]:
        existing = await self.session.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("An account with this email already exists.")

        base_slug = slugify(organization_name)
        slug = base_slug
        suffix = 1
        while (
            await self.session.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none() is not None:
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        user = User(
            email=email.lower(),
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        organization = Organization(name=organization_name, slug=slug, is_active=True)
        self.session.add_all([user, organization])
        await self.session.flush()  # assign IDs

        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role=OrgRole.ORG_ADMIN,
            is_active=True,
        )
        self.session.add(membership)

        self.session.add(
            AuditLog(
                organization_id=organization.id,
                actor_user_id=user.id,
                actor_type="user",
                action="auth.register",
                entity_type="organization",
                entity_id=str(organization.id),
                metadata_json={"email": email.lower()},
            )
        )
        await self.session.flush()

        # Give every new organization a Tally-style chart of accounts so the
        # accounting module works from the first login.
        from app.services.accounting_service import AccountingService

        await AccountingService(self.session).ensure_chart_of_accounts(organization.id)

        return user, organization, membership

    async def authenticate(
        self, *, email: str, password: str, organization_id: uuid.UUID | None
    ) -> tuple[User, OrganizationMember]:
        stmt = (
            select(User)
            .where(User.email == email.lower())
            .options(selectinload(User.memberships))
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password.")
        if not user.is_active:
            raise UnauthorizedError("This account has been deactivated.")

        active_memberships = [m for m in user.memberships if m.is_active]
        if not active_memberships:
            raise UnauthorizedError("This user has no active organization membership.")

        if organization_id is not None:
            membership = next(
                (m for m in active_memberships if m.organization_id == organization_id), None
            )
            if membership is None:
                raise UnauthorizedError("User is not a member of the requested organization.")
        elif len(active_memberships) == 1:
            membership = active_memberships[0]
        else:
            raise ValidationFailedError(
                "User belongs to multiple organizations; organization_id is required."
            )

        self.session.add(
            AuditLog(
                organization_id=membership.organization_id,
                actor_user_id=user.id,
                actor_type="user",
                action="auth.login",
                entity_type="user",
                entity_id=str(user.id),
                metadata_json={},
            )
        )
        await self.session.flush()
        return user, membership

    def issue_tokens(self, user: User, membership: OrganizationMember) -> tuple[str, str]:
        access = create_access_token(
            user.id, organization_id=membership.organization_id, role=membership.role.value
        )
        refresh = create_refresh_token(user.id)
        return access, refresh

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except Exception as exc:
            raise UnauthorizedError("Invalid or expired refresh token.") from exc

        user_id = uuid.UUID(payload.sub)
        stmt = (
            select(User).where(User.id == user_id).options(selectinload(User.memberships))
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise UnauthorizedError("User no longer active.")

        active_memberships = [m for m in user.memberships if m.is_active]
        if not active_memberships:
            raise UnauthorizedError("This user has no active organization membership.")
        membership = active_memberships[0]

        return self.issue_tokens(user, membership)
