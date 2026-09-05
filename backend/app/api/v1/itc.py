"""Standalone ITC analysis endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.errors import NotFoundError
from app.llm.factory import get_llm_provider
from app.models.invoice import Invoice
from app.rag.embeddings import get_embedding_provider
from app.schemas.compliance import ITCRecordOut
from app.security.dependencies import CurrentMembership, get_current_membership
from app.services.itc_service import ITCService

router = APIRouter()


@router.post("/analyze", response_model=ITCRecordOut)
async def analyze_itc(
    invoice_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ITCRecordOut:
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == membership.organization_id)
        .options(selectinload(Invoice.items))
    )
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found.")

    service = ITCService(
        session, llm=get_llm_provider(), embedding_provider=get_embedding_provider()
    )
    record = await service.analyze(invoice)
    await session.commit()
    return ITCRecordOut.model_validate(record)
