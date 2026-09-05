"""Organization settings + member administration service.

All mutations here are org-admin actions; the router enforces the role, this
layer enforces the invariants (an org can never be left with zero active
admins) and writes an audit record for every change.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.notification import SystemSetting
from app.models.organization import GSTProfile, Organization
from app.models.rbac import OrganizationMember, OrgRole
from app.models.user import User
from app.rules.gstin_validator import validate_gstin
from app.rules.org_membership import MemberView, would_remove_last_admin
from app.security.passwords import hash_password, verify_password

logger = get_logger(__name__)

_MIN_PASSWORD_LEN = 10


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- organization ----

    async def get_organization(self, organization_id: uuid.UUID) -> Organization:
        result = await self.session.execute(
            select(Organization)
            .where(Organization.id == organization_id)
            .options(selectinload(Organization.gst_profile))
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org

    async def update_organization(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        name: str | None = None,
        legal_name: str | None = None,
    ) -> Organization:
        org = await self.get_organization(organization_id)
        if name is not None:
            org.name = name
        if legal_name is not None:
            org.legal_name = legal_name
        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="organization.update",
                entity_type="organization",
                entity_id=str(organization_id),
                metadata_json={"name": org.name},
            )
        )
        await self.session.flush()
        return org

    async def upsert_gst_profile(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        gstin: str,
        legal_name: str,
        trade_name: str | None,
        state_code: str,
        registration_type: str,
    ) -> GSTProfile:
        gstin_result = validate_gstin(gstin)
        if not gstin_result.is_valid:
            raise ValidationFailedError(
                f"GSTIN is not valid: {'; '.join(gstin_result.errors)}"
            )

        result = await self.session.execute(
            select(GSTProfile).where(GSTProfile.organization_id == organization_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = GSTProfile(
                organization_id=organization_id, gstin=gstin, legal_name=legal_name
            )
            self.session.add(profile)

        profile.gstin = gstin
        profile.legal_name = legal_name
        profile.trade_name = trade_name
        profile.state_code = state_code or (gstin_result.state_code or "")
        profile.registration_type = registration_type
        profile.is_verified = False

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="organization.gst_profile.upsert",
                entity_type="gst_profile",
                entity_id=str(organization_id),
                metadata_json={"gstin": gstin},
            )
        )
        await self.session.flush()
        return profile

    # ---- members ----

    async def list_members(self, organization_id: uuid.UUID) -> list[OrganizationMember]:
        result = await self.session.execute(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .options(selectinload(OrganizationMember.user))
            .order_by(OrganizationMember.created_at)
        )
        return list(result.scalars().all())

    async def _member_views(self, organization_id: uuid.UUID) -> list[MemberView]:
        members = await self.list_members(organization_id)
        return [
            MemberView(member_id=str(m.id), role=m.role, is_active=m.is_active) for m in members
        ]

    async def add_member(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        email: str,
        role: OrgRole,
        full_name: str | None = None,
        password: str | None = None,
    ) -> OrganizationMember:
        email = email.lower().strip()
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            if not full_name or not password:
                raise ValidationFailedError(
                    "full_name and password are required to create a new user account."
                )
            if len(password) < _MIN_PASSWORD_LEN:
                raise ValidationFailedError(
                    f"Password must be at least {_MIN_PASSWORD_LEN} characters."
                )
            user = User(
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                is_active=True,
            )
            self.session.add(user)
            await self.session.flush()

        existing = await self.session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user.id,
            )
        )
        member = existing.scalar_one_or_none()
        if member is not None:
            if member.is_active:
                raise ConflictError("This user is already a member of the organization.")
            member.is_active = True
            member.role = role
        else:
            member = OrganizationMember(
                organization_id=organization_id, user_id=user.id, role=role, is_active=True
            )
            self.session.add(member)

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="organization.member.add",
                entity_type="organization_member",
                entity_id=str(user.id),
                metadata_json={"email": email, "role": role.value},
            )
        )
        await self.session.flush()
        await self.session.refresh(member, attribute_names=["user"])
        return member

    async def update_member(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        member_id: uuid.UUID,
        role: OrgRole | None = None,
        is_active: bool | None = None,
    ) -> OrganizationMember:
        result = await self.session.execute(
            select(OrganizationMember)
            .where(
                OrganizationMember.id == member_id,
                OrganizationMember.organization_id == organization_id,
            )
            .options(selectinload(OrganizationMember.user))
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise NotFoundError("Member not found.")

        if would_remove_last_admin(
            await self._member_views(organization_id),
            target_member_id=str(member_id),
            new_role=role,
            new_is_active=is_active,
        ):
            raise ValidationFailedError(
                "This change would leave the organization with no active administrator."
            )

        if role is not None:
            member.role = role
        if is_active is not None:
            member.is_active = is_active

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="organization.member.update",
                entity_type="organization_member",
                entity_id=str(member_id),
                metadata_json={"role": member.role.value, "is_active": member.is_active},
            )
        )
        await self.session.flush()
        return member

    # ---- settings ----

    async def list_settings(self, organization_id: uuid.UUID) -> dict[str, dict]:
        result = await self.session.execute(
            select(SystemSetting).where(SystemSetting.organization_id == organization_id)
        )
        return {s.key: s.value for s in result.scalars().all()}

    async def set_setting(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        key: str,
        value: dict,
    ) -> None:
        result = await self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id, SystemSetting.key == key
            )
        )
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = SystemSetting(organization_id=organization_id, key=key, value=value)
            self.session.add(setting)
        else:
            setting.value = value

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="organization.setting.update",
                entity_type="system_setting",
                entity_id=key,
                metadata_json={"key": key},
            )
        )
        await self.session.flush()

    # ---- audit ----

    async def list_audit(
        self, *, organization_id: uuid.UUID, limit: int = 100
    ) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ---- current user profile ----

    async def update_profile(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None = None,
        current_password: str | None = None,
        new_password: str | None = None,
    ) -> User:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found.")

        if full_name is not None:
            user.full_name = full_name

        if new_password is not None:
            if not current_password or not verify_password(current_password, user.hashed_password):
                raise ValidationFailedError("Current password is incorrect.")
            if len(new_password) < _MIN_PASSWORD_LEN:
                raise ValidationFailedError(
                    f"New password must be at least {_MIN_PASSWORD_LEN} characters."
                )
            user.hashed_password = hash_password(new_password)

        await self.session.flush()
        return user
