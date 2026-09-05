"""Human-in-the-loop approval queue endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models.approval import ApprovalStatus
from app.models.rbac import APPROVER_ROLES
from app.schemas.approvals import (
    ApprovalCountsOut,
    ApprovalDecisionRequest,
    ApprovalOut,
)
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.services.approval_service import ApprovalService

router = APIRouter()


@router.get("", response_model=list[ApprovalOut])
async def list_review_tasks(
    status: ApprovalStatus | None = None,
    limit: int = 100,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApprovalOut]:
    service = ApprovalService(session)
    tasks = await service.list_tasks(
        organization_id=membership.organization_id, status=status, limit=limit
    )
    return [ApprovalOut.model_validate(t) for t in tasks]


@router.get("/counts", response_model=ApprovalCountsOut)
async def review_task_counts(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalCountsOut:
    service = ApprovalService(session)
    counts = await service.counts_by_status(organization_id=membership.organization_id)
    return ApprovalCountsOut(**counts)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_review_task(
    approval_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalOut:
    service = ApprovalService(session)
    approval = await service.get(
        organization_id=membership.organization_id, approval_id=approval_id
    )
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide_review_task(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    membership: CurrentMembership = Depends(require_roles(*APPROVER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalOut:
    service = ApprovalService(session)
    approval = await service.decide(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        approval_id=approval_id,
        decision=body.decision,
        notes=body.notes,
        final_payload=body.final_payload,
    )
    await session.commit()
    return ApprovalOut.model_validate(approval)
