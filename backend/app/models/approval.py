"""Human-in-the-loop review/approval queue.

Every high-impact or low-confidence AI output that requires sign-off
(invoice extraction, compliance exception, ITC assessment, return
preparation) creates one `Approval` row. Decisions are never silent —
`decided_by`/`decision_notes` capture the human's edit/reasoning for audit.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class ApprovalType(StrEnum):
    INVOICE_EXTRACTION = "invoice_extraction"
    COMPLIANCE_EXCEPTION = "compliance_exception"
    ITC_ASSESSMENT = "itc_assessment"
    RETURN_PREPARATION = "return_preparation"
    GST_RESEARCH_ANSWER = "gst_research_answer"
    OTHER = "other"


class ApprovalRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "review_tasks"

    approval_type: Mapped[ApprovalType] = mapped_column(
        str_enum_column(ApprovalType, "approval_type"), nullable=False
    )
    risk: Mapped[ApprovalRisk] = mapped_column(
        str_enum_column(ApprovalRisk, "approval_risk"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        str_enum_column(ApprovalStatus, "approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)

    ai_recommendation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    final_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
