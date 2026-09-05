"""Celery tasks.

Each task bridges into the async service layer via `asyncio.run` — Celery
workers are synchronous by design, and this keeps a single async
implementation of each service shared between the API (called directly)
and the worker (called via `.delay()`/beat), rather than maintaining two
copies of the same logic.
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.database import db_session_context
from app.core.logging import get_logger
from app.rag.embeddings import get_embedding_provider
from app.services.compliance_service import ComplianceService
from app.services.ingestion_service import IngestionService
from app.storage.object_storage import get_object_storage
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.reindex_document_task", bind=True, max_retries=3)
def reindex_document_task(self, document_id: str) -> str:
    """Re-run OCR/chunk/embed/index for an existing document. Queued from
    the admin document UI's "Re-index" action so it doesn't block the
    request for large documents.
    """
    try:
        return asyncio.run(_reindex_document(document_id))
    except Exception as exc:
        logger.error("reindex_document_task_failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30) from exc


async def _reindex_document(document_id: str) -> str:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.document import Document

    async with db_session_context() as session:
        result = await session.execute(
            select(Document)
            .where(Document.id == uuid.UUID(document_id))
            .options(selectinload(Document.chunks))
        )
        document = result.scalar_one_or_none()
        if document is None:
            return f"document {document_id} not found"

        service = IngestionService(
            session=session,
            storage=get_object_storage(),
            embedding_provider=get_embedding_provider(),
        )
        await service.reindex_document(document)
        return f"document {document_id} reindexed (status={document.status.value})"


@celery_app.task(name="app.workers.tasks.run_scheduled_compliance_scan")
def run_scheduled_compliance_scan() -> str:
    """Re-run compliance checks for invoices that don't yet have one.
    Scheduled nightly via Celery beat (see celery_app.conf.beat_schedule).
    """
    return asyncio.run(_run_scheduled_compliance_scan())


async def _run_scheduled_compliance_scan(batch_size: int = 100) -> str:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.compliance import ComplianceCheck
    from app.models.invoice import Invoice, InvoiceStatus

    async with db_session_context() as session:
        checked_invoice_ids = select(ComplianceCheck.invoice_id)
        stmt = (
            select(Invoice)
            .where(
                Invoice.status == InvoiceStatus.EXTRACTED,
                Invoice.id.not_in(checked_invoice_ids),
            )
            .options(selectinload(Invoice.items))
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        invoices = list(result.scalars().all())

        service = ComplianceService(session)
        for invoice in invoices:
            await service.run_check(invoice)

        logger.info("scheduled_compliance_scan_completed", invoice_count=len(invoices))
        return f"checked {len(invoices)} invoice(s)"
