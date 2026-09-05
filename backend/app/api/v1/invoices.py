"""Invoice upload, listing, detail, and combined compliance+ITC analysis."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_session_context, get_db_session
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.models.approval import ApprovalRisk, ApprovalType
from app.models.compliance import ComplianceSeverity
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.rag.embeddings import get_embedding_provider
from app.schemas.compliance import ComplianceCheckOut, InvoiceAnalysisResponse, ITCRecordOut
from app.schemas.invoice import InvoiceOut, InvoiceUploadResponse
from app.security.dependencies import CurrentMembership, get_current_membership
from app.security.file_validation import validate_upload
from app.services.approval_service import ApprovalService
from app.services.compliance_service import ComplianceService
from app.services.invoice_extraction_service import InvoiceExtractionService
from app.services.itc_service import ITCService
from app.storage.object_storage import get_object_storage

router = APIRouter()
logger = get_logger(__name__)


async def _process_invoice_upload(
    *, invoice_id: uuid.UUID, content: bytes, filename: str, mime_type: str
) -> None:
    """Background task: OCR + LLM extraction + compliance for an uploaded
    invoice. Runs after the HTTP response is sent so a slow local LLM never
    holds the request open past the browser's timeout.
    """
    try:
        async with db_session_context() as session:
            result = await session.execute(
                select(Invoice)
                .where(Invoice.id == invoice_id)
                .options(selectinload(Invoice.items), selectinload(Invoice.taxes))
            )
            invoice = result.scalar_one_or_none()
            if invoice is None:
                return

            service = InvoiceExtractionService(
                llm=get_llm_provider(), storage=get_object_storage()
            )
            await service.extract_into(
                invoice, content=content, filename=filename, mime_type=mime_type
            )
            if invoice.status == InvoiceStatus.EXTRACTED:
                await ComplianceService(session).run_check(invoice)
    except Exception as exc:  # noqa: BLE001 - a failed extraction must surface on the row
        logger.error(
            "invoice_background_processing_failed",
            invoice_id=str(invoice_id),
            error=str(exc),
        )
        try:
            async with db_session_context() as session:
                invoice = await session.get(Invoice, invoice_id)
                if invoice is not None:
                    invoice.status = InvoiceStatus.FAILED
                    invoice.extracted_fields = {"error": f"Processing failed: {exc}"}
        except Exception:  # noqa: BLE001
            logger.error("invoice_failure_marking_failed", invoice_id=str(invoice_id))


@router.post("/upload", response_model=InvoiceUploadResponse, status_code=202)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    direction: InvoiceDirection = Form(InvoiceDirection.PURCHASE),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceUploadResponse:
    content = await file.read()
    validate_upload(filename=file.filename or "", content=content)

    invoice = Invoice(
        organization_id=membership.organization_id,
        direction=direction,
        status=InvoiceStatus.PROCESSING,
        created_by=membership.user_id,
        currency="INR",
    )
    session.add(invoice)
    await session.commit()
    await session.refresh(invoice, attribute_names=["items", "taxes"])

    background_tasks.add_task(
        _process_invoice_upload,
        invoice_id=invoice.id,
        content=content,
        filename=file.filename or "invoice",
        mime_type=file.content_type or "application/octet-stream",
    )

    return InvoiceUploadResponse(invoice=InvoiceOut.model_validate(invoice), validation={})


@router.get("", response_model=list[InvoiceOut])
async def list_invoices(
    direction: InvoiceDirection | None = None,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[InvoiceOut]:
    stmt = (
        select(Invoice)
        .where(Invoice.organization_id == membership.organization_id)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.created_at.desc())
    )
    if direction is not None:
        stmt = stmt.where(Invoice.direction == direction)

    result = await session.execute(stmt)
    return [InvoiceOut.model_validate(i) for i in result.scalars().all()]


async def _get_invoice_or_404(
    invoice_id: uuid.UUID, membership: CurrentMembership, session: AsyncSession
) -> Invoice:
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == membership.organization_id)
        .options(selectinload(Invoice.items), selectinload(Invoice.taxes))
    )
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found.")
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceOut:
    invoice = await _get_invoice_or_404(invoice_id, membership, session)
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/analyze", response_model=InvoiceAnalysisResponse)
async def analyze_invoice(
    invoice_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceAnalysisResponse:
    invoice = await _get_invoice_or_404(invoice_id, membership, session)

    compliance_service = ComplianceService(session)
    check = await compliance_service.run_check(invoice)

    itc_service = ITCService(
        session, llm=get_llm_provider(), embedding_provider=get_embedding_provider()
    )
    itc_record = await itc_service.analyze(invoice)

    # Route anything the deterministic rules flagged into the human review queue.
    approvals = ApprovalService(session)
    has_blocking = any(
        i.severity in (ComplianceSeverity.CRITICAL, ComplianceSeverity.HIGH)
        for i in check.issues
    )
    if has_blocking:
        await approvals.create(
            organization_id=membership.organization_id,
            approval_type=ApprovalType.COMPLIANCE_EXCEPTION,
            risk=ApprovalRisk.HIGH if has_blocking else ApprovalRisk.MEDIUM,
            entity_type="invoice",
            entity_id=str(invoice.id),
            ai_recommendation={
                "compliance_score": check.score,
                "issues": [
                    {"rule_code": i.rule_code, "severity": i.severity.value, "message": i.message}
                    for i in check.issues
                ],
            },
            confidence=None,
        )
    if itc_record.requires_human_review:
        await approvals.create(
            organization_id=membership.organization_id,
            approval_type=ApprovalType.ITC_ASSESSMENT,
            risk=ApprovalRisk.MEDIUM,
            entity_type="invoice",
            entity_id=str(invoice.id),
            ai_recommendation={
                "status": itc_record.status.value,
                "eligible_amount": str(itc_record.eligible_amount or 0),
                "open_questions": itc_record.reasons,
            },
            confidence=float(itc_record.confidence),
        )

    await session.commit()

    return InvoiceAnalysisResponse(
        compliance=ComplianceCheckOut.model_validate(check),
        itc=ITCRecordOut.model_validate(itc_record),
    )
