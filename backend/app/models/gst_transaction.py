"""GST transactions, persisted tax calculations, and ITC assessments.

`TaxCalculation` persists the exact output of `GSTCalculator` (see
app/rules/gst_calculator.py) so a figure shown to a user is always traceable
back to the deterministic engine call that produced it, including the
`rules_version` that was active at the time.
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


class GSTTransaction(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "gst_transactions"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)  # sales|purchase
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-01"
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class TaxCalculation(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "tax_calculations"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ITCStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REVIEW_REQUIRED = "review_required"


class ITCRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "itc_records"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ITCStatus] = mapped_column(
        str_enum_column(ITCStatus, "itc_status"), nullable=False
    )
    eligible_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(default=True, nullable=False)
