"""Organization settings, GST profile, member administration and audit log.

Read endpoints are open to any member; every mutation requires an org-admin
role (`ADMIN_ROLES`). `/organizations/current` always resolves to the
caller's active organization context — there is no cross-org access here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models.rbac import ADMIN_ROLES, OrganizationMember
from app.schemas.organization import (
    AddMemberRequest,
    AuditLogOut,
    MemberOut,
    OrganizationOut,
    SettingsOut,
    UpdateMemberRequest,
    UpdateOrganizationRequest,
    UpdateSettingRequest,
    UpsertGSTProfileRequest,
)
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.services.organization_service import OrganizationService

router = APIRouter()


def _member_out(member: OrganizationMember) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        role=member.role,
        is_active=member.is_active,
    )


@router.get("/current", response_model=OrganizationOut)
async def get_current_organization(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationOut:
    service = OrganizationService(session)
    org = await service.get_organization(membership.organization_id)
    return OrganizationOut.model_validate(org)


@router.patch("/current", response_model=OrganizationOut)
async def update_current_organization(
    body: UpdateOrganizationRequest,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationOut:
    service = OrganizationService(session)
    org = await service.update_organization(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        name=body.name,
        legal_name=body.legal_name,
    )
    await session.commit()
    await session.refresh(org, attribute_names=["gst_profile"])
    return OrganizationOut.model_validate(org)


@router.put("/current/gst-profile", response_model=OrganizationOut)
async def upsert_gst_profile(
    body: UpsertGSTProfileRequest,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationOut:
    service = OrganizationService(session)
    await service.upsert_gst_profile(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        gstin=body.gstin,
        legal_name=body.legal_name,
        trade_name=body.trade_name,
        state_code=body.state_code,
        registration_type=body.registration_type,
    )
    await session.commit()
    org = await service.get_organization(membership.organization_id)
    return OrganizationOut.model_validate(org)


@router.get("/current/members", response_model=list[MemberOut])
async def list_members(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberOut]:
    service = OrganizationService(session)
    members = await service.list_members(membership.organization_id)
    return [_member_out(m) for m in members]


@router.post("/current/members", response_model=MemberOut, status_code=201)
async def add_member(
    body: AddMemberRequest,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    service = OrganizationService(session)
    member = await service.add_member(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        email=body.email,
        role=body.role,
        full_name=body.full_name,
        password=body.password,
    )
    await session.commit()
    return _member_out(member)


@router.patch("/current/members/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: uuid.UUID,
    body: UpdateMemberRequest,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    service = OrganizationService(session)
    member = await service.update_member(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        member_id=member_id,
        role=body.role,
        is_active=body.is_active,
    )
    await session.commit()
    return _member_out(member)


@router.get("/current/settings", response_model=SettingsOut)
async def get_settings(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> SettingsOut:
    service = OrganizationService(session)
    settings = await service.list_settings(membership.organization_id)
    return SettingsOut(settings=settings)


@router.put("/current/settings", response_model=SettingsOut)
async def update_setting(
    body: UpdateSettingRequest,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> SettingsOut:
    service = OrganizationService(session)
    await service.set_setting(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        key=body.key,
        value=body.value,
    )
    await session.commit()
    settings = await service.list_settings(membership.organization_id)
    return SettingsOut(settings=settings)


@router.get("/current/audit", response_model=list[AuditLogOut])
async def list_audit(
    limit: int = 100,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> list[AuditLogOut]:
    service = OrganizationService(session)
    logs = await service.list_audit(organization_id=membership.organization_id, limit=limit)
    return [AuditLogOut.model_validate(log) for log in logs]
