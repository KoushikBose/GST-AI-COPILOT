"""GSTR-2A/2B reconciliation.

Reconciles the organization's purchase invoices ("books") against
supplier-reported inward-supply records from an uploaded GSTR-2A/2B export
("return") for a tax period. All matching arithmetic is delegated to the
deterministic `app.rules.gstr_reconciliation` module — the LLM never decides
whether an invoice matches.

`Gstr2bRecord` rows are populated by uploading a CSV export downloaded from
the GST portal (see app/services/reconciliation_service.py). There is no
live GSTN API integration — the same boundary already drawn for GSTIN
validation (app/rules/gstin_validator.py: structural checksum only, not a
live registration-status check).
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


class ReconciliationSource(StrEnum):
    GSTR2A = "gstr2a"
    GSTR2B = "gstr2b"


class ReconciliationMatchStatus(StrEnum):
    MATCHED = "matched"
    MISMATCH = "mismatch"
    MISSING_IN_RETURN = "missing_in_return"  # in books, not in supplier's 2A/2B -> ITC at risk
    MISSING_IN_BOOKS = "missing_in_books"  # in 2A/2B, no matching purchase invoice recorded


class Gstr2bRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    """One supplier-reported inward-supply line, imported from a GSTR-2A/2B
    CSV export for a given period. Re-uploading a period+source replaces its
    records (see ReconciliationService.import_records)."""

    __tablename__ = "gstr2b_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period",
            "source",
            "row_number",
            name="uq_gstr2b_record_org_period_source_row",
        ),
    )

    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-01"
    source: Mapped[ReconciliationSource] = mapped_column(
        str_enum_column(ReconciliationSource, "reconciliation_source"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(nullable=False)

    supplier_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cess: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ReconciliationRun(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    """One reconciliation pass for a period. Re-running a period replaces
    its matches (see ReconciliationService.run)."""

    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "period", name="uq_reconciliation_run_org_period"),
    )

    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    source: Mapped[ReconciliationSource] = mapped_column(
        str_enum_column(ReconciliationSource, "reconciliation_source"), nullable=False
    )

    book_invoice_count: Mapped[int] = mapped_column(nullable=False, default=0)
    return_record_count: Mapped[int] = mapped_column(nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(nullable=False, default=0)
    mismatch_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_in_return_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_in_books_count: Mapped[int] = mapped_column(nullable=False, default=0)

    itc_at_risk: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    potential_unclaimed_itc: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=0
    )

    run_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ReconciliationMatch(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    """One row per book invoice / return record pairing (or unpaired side)
    produced by a `ReconciliationRun`."""

    __tablename__ = "reconciliation_matches"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ReconciliationMatchStatus] = mapped_column(
        str_enum_column(ReconciliationMatchStatus, "reconciliation_match_status"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    gstr2b_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gstr2b_records.id", ondelete="SET NULL"), nullable=True
    )

    supplier_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    book_taxable_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    book_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    return_taxable_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    return_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    taxable_value_difference: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0
    )
    tax_difference: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    itc_at_risk: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
