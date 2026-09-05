"""GST return preparation endpoints.

Generate a deterministic GSTR-1 / GSTR-3B draft from the period's invoices,
review it, route it through the approval queue, and export it as CSV. No
data is transmitted to the GSTN — this prepares figures for a human.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models.rbac import ADMIN_ROLES, APPROVER_ROLES, OrgRole
from app.schemas.approvals import ApprovalOut
from app.schemas.returns import GenerateReturnRequest, GSTReturnOut, GSTReturnSummaryOut
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.services.return_service import ReturnService
from app.storage.object_storage import get_object_storage

router = APIRouter()

_PREPARER_ROLES = (
    *ADMIN_ROLES,
    OrgRole.ACCOUNTANT,
    OrgRole.FINANCE_MANAGER,
    OrgRole.ANALYST,
)


@router.get("", response_model=list[GSTReturnSummaryOut])
async def list_returns(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[GSTReturnSummaryOut]:
    service = ReturnService(session)
    returns = await service.list_returns(organization_id=membership.organization_id)
    return [GSTReturnSummaryOut.model_validate(r) for r in returns]


@router.post("/generate", response_model=GSTReturnOut, status_code=201)
async def generate_return(
    body: GenerateReturnRequest,
    membership: CurrentMembership = Depends(require_roles(*_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> GSTReturnOut:
    service = ReturnService(session)
    gst_return = await service.generate(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_type=body.return_type,
        period=body.period,
    )
    await session.commit()
    return GSTReturnOut.model_validate(gst_return)


@router.get("/{return_id}", response_model=GSTReturnOut)
async def get_return(
    return_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> GSTReturnOut:
    service = ReturnService(session)
    gst_return = await service.get(
        organization_id=membership.organization_id, return_id=return_id
    )
    return GSTReturnOut.model_validate(gst_return)


@router.post("/{return_id}/submit", response_model=ApprovalOut)
async def submit_return_for_review(
    return_id: uuid.UUID,
    membership: CurrentMembership = Depends(require_roles(*_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalOut:
    service = ReturnService(session)
    _return, approval = await service.submit_for_review(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_id=return_id,
    )
    await session.commit()
    return ApprovalOut.model_validate(approval)


@router.get("/{return_id}/export")
async def export_return(
    return_id: uuid.UUID,
    membership: CurrentMembership = Depends(require_roles(*APPROVER_ROLES, *_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    service = ReturnService(session, storage=get_object_storage())
    _return, filename, csv_text = await service.export(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_id=return_id,
    )
    await session.commit()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
