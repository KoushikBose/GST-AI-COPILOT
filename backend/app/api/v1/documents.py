"""Document management API: upload GST knowledge / tenant documents, list,
inspect, re-index, and delete.

Ingestion (OCR -> chunk -> embed -> Qdrant upsert -> BM25 rebuild) runs as a
FastAPI background task after the upload responds, so a slow first-run
embedding-model download or a large PDF never holds the request open. The
document is returned immediately with `status = processing` and the
frontend polls until it flips to `indexed` / `failed`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_session_context, get_db_session
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.rbac import ADMIN_ROLES
from app.schemas.document import DocumentOut, DocumentUploadMetadata
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.security.file_validation import validate_upload
from app.services.ingestion_service import IngestionService
from app.storage.object_storage import get_object_storage

router = APIRouter()
logger = get_logger(__name__)


async def _process_document_ingestion(*, document_id: uuid.UUID) -> None:
    try:
        async with db_session_context() as session:
            result = await session.execute(
                select(Document)
                .where(Document.id == document_id)
                .options(selectinload(Document.chunks))
            )
            document = result.scalar_one_or_none()
            if document is None:
                return
            service = IngestionService(session=session, storage=get_object_storage())
            await service.process_document(document)
    except Exception as exc:  # noqa: BLE001 - failure must land on the row, not vanish
        logger.error(
            "document_ingestion_task_failed", document_id=str(document_id), error=str(exc)
        )
        try:
            async with db_session_context() as session:
                document = await session.get(Document, document_id)
                if document is not None:
                    document.status = DocumentStatus.FAILED
                    document.error_message = f"Processing failed: {exc}"
        except Exception:  # noqa: BLE001
            logger.error("document_failure_marking_failed", document_id=str(document_id))


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    title: str | None = Form(None),
    jurisdiction: str = Form("India"),
    effective_date: str | None = Form(None),
    source_url: str | None = Form(None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    content = await file.read()
    validate_upload(filename=file.filename or "", content=content)

    filename = file.filename or "upload"
    # Fall back to the file's own name if the uploader left the title blank —
    # a missing title should never be the reason an upload silently fails.
    resolved_title = (title or "").strip() or filename.rsplit(".", 1)[0] or filename

    metadata = DocumentUploadMetadata(
        document_type=document_type,
        title=resolved_title,
        jurisdiction=jurisdiction,
        effective_date=effective_date,
        source_url=source_url,
    )

    service = IngestionService(session=session, storage=get_object_storage())
    document = await service.create_pending_document(
        content=content,
        filename=filename,
        mime_type=file.content_type or "application/octet-stream",
        document_type=metadata.document_type,
        title=metadata.title,
        organization_id=membership.organization_id,
        uploaded_by=membership.user_id,
        jurisdiction=metadata.jurisdiction,
        effective_date=metadata.effective_date,
        source_url=metadata.source_url,
    )
    await session.commit()
    await session.refresh(document)

    background_tasks.add_task(_process_document_ingestion, document_id=document.id)
    return DocumentOut.model_validate(document)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    document_type: DocumentType | None = None,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentOut]:
    stmt = select(Document).where(
        (Document.organization_id == membership.organization_id)
        | (Document.organization_id.is_(None)),
        Document.is_active.is_(True),
    )
    if document_type is not None:
        stmt = stmt.where(Document.document_type == document_type)
    stmt = stmt.order_by(Document.created_at.desc())

    result = await session.execute(stmt)
    return [DocumentOut.model_validate(d) for d in result.scalars().all()]


async def _get_visible_document(
    document_id: uuid.UUID, membership: CurrentMembership, session: AsyncSession
) -> Document:
    stmt = select(Document).where(
        Document.id == document_id,
        (Document.organization_id == membership.organization_id)
        | (Document.organization_id.is_(None)),
    )
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    return document


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    document = await _get_visible_document(document_id, membership, session)
    return DocumentOut.model_validate(document)


async def _reindex_document_task(*, document_id: uuid.UUID) -> None:
    try:
        async with db_session_context() as session:
            result = await session.execute(
                select(Document)
                .where(Document.id == document_id)
                .options(selectinload(Document.chunks))
            )
            document = result.scalar_one_or_none()
            if document is None:
                return
            service = IngestionService(session=session, storage=get_object_storage())
            await service.reindex_document(document)
    except Exception as exc:  # noqa: BLE001
        logger.error("document_reindex_task_failed", document_id=str(document_id), error=str(exc))
        try:
            async with db_session_context() as session:
                document = await session.get(Document, document_id)
                if document is not None:
                    document.status = DocumentStatus.FAILED
                    document.error_message = f"Re-index failed: {exc}"
        except Exception:  # noqa: BLE001
            logger.error("document_reindex_failure_marking_failed", document_id=str(document_id))


@router.post("/{document_id}/reindex", response_model=DocumentOut, status_code=202)
async def reindex_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    document = await _get_visible_document(document_id, membership, session)
    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    await session.commit()
    await session.refresh(document)

    background_tasks.add_task(_reindex_document_task, document_id=document.id)
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    membership: CurrentMembership = Depends(require_roles(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    document = await _get_visible_document(document_id, membership, session)
    document.is_active = False
    await session.commit()
