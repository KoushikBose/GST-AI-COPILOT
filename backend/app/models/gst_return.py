"""GST return preparation.

A `GSTReturn` row is a prepared, human-reviewable draft of the figures for
one tax period (GSTR-1 outward supplies or GSTR-3B summary). It is generated
deterministically by aggregating the organization's invoices for the period
(see app/rules/return_aggregation.py) — the LLM is never in this path.

This is NOT a filing integration. Nothing here is transmitted to the GSTN;
`status` tops out at `approved`/`exported`, and `filed_externally` only
records that a human filed it through the official portal by hand.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class ReturnType(StrEnum):
    GSTR1 = "gstr1"
    GSTR3B = "gstr3b"


class ReturnStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    EXPORTED = "exported"
    FILED_EXTERNALLY = "filed_externally"


class GSTReturn(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "gst_returns"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "return_type", "period", name="uq_return_org_type_period"
        ),
    )

    return_type: Mapped[ReturnType] = mapped_column(
        str_enum_column(ReturnType, "gst_return_type"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-01"
    status: Mapped[ReturnStatus] = mapped_column(
        str_enum_column(ReturnStatus, "gst_return_status"),
        nullable=False,
        default=ReturnStatus.GENERATED,
    )

    invoice_count: Mapped[int] = mapped_column(nullable=False, default=0)
    total_taxable_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    total_tax: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)

    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)

    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    export_storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
