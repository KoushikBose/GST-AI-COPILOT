"""Standalone compliance endpoints (invoice-level checks also run inline
from POST /invoices/{id}/analyze — this router is for re-running a check
and for listing outstanding issues across the organization).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.errors import NotFoundError
from app.models.compliance import ComplianceCheck, ComplianceIssue
from app.models.invoice import Invoice
from app.schemas.compliance import ComplianceCheckOut, ComplianceIssueOut
from app.security.dependencies import CurrentMembership, get_current_membership
from app.services.compliance_service import ComplianceService

router = APIRouter()


@router.post("/check", response_model=ComplianceCheckOut)
async def check_invoice_compliance(
    invoice_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ComplianceCheckOut:
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == membership.organization_id)
        .options(selectinload(Invoice.items))
    )
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found.")

    service = ComplianceService(session)
    check = await service.run_check(invoice)
    await session.commit()
    return ComplianceCheckOut.model_validate(check)


@router.get("/issues", response_model=list[ComplianceIssueOut])
async def list_open_compliance_issues(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
    limit: int = 100,
) -> list[ComplianceIssueOut]:
    stmt = (
        select(ComplianceIssue)
        .join(ComplianceCheck, ComplianceIssue.check_id == ComplianceCheck.id)
        .where(ComplianceCheck.organization_id == membership.organization_id)
        .order_by(ComplianceIssue.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [ComplianceIssueOut.model_validate(i) for i in result.scalars().all()]
