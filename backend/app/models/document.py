"""Document management: uploaded files, ingestion versions, and the chunks
that get embedded into Qdrant.

`KnowledgeSource` distinguishes public/global GST knowledge (Acts, Rules,
Notifications, Circulars, FAQs — organization_id is NULL) from
tenant-private documents (organization_id set, indexed only into the
`tenant_documents` Qdrant collection and filtered by tenant on retrieval).
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import AuditActorMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class DocumentType(StrEnum):
    ACT = "act"
    RULE = "rule"
    NOTIFICATION = "notification"
    CIRCULAR = "circular"
    FAQ = "faq"
    CASE_KNOWLEDGE = "case_knowledge"
    INTERNAL_POLICY = "internal_policy"
    INVOICE = "invoice"
    SUPPORTING = "supporting"
    OTHER = "other"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    ARCHIVED = "archived"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "documents"

    # NULL organization_id => global/public GST knowledge document.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )

    document_type: Mapped[DocumentType] = mapped_column(
        str_enum_column(DocumentType, "document_type"), nullable=False
    )
    status: Mapped[DocumentStatus] = mapped_column(
        str_enum_column(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    jurisdiction: Mapped[str] = mapped_column(String(50), default="India", nullable=False)
    effective_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata mirror of what's embedded into Qdrant.

    The chunk *text* and *vector* live in Qdrant; this row exists so we can
    join chunk provenance back to relational data (e.g. list all chunks for
    a document, or invalidate/re-index on document update) without a Qdrant
    scroll query.
    """

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    qdrant_collection: Mapped[str] = mapped_column(String(100), nullable=False)
    qdrant_point_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
