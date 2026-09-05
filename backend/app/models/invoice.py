"""Invoice, invoice line items, and per-line tax breakdown.

Extracted-field confidence (see master spec section 14/22) is stored
alongside the normalized value in `extracted_fields` (JSONB) so the UI can
render per-field confidence without a schema migration every time OCR
extraction gains a new field.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    AuditActorMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class InvoiceDirection(StrEnum):
    SALES = "sales"  # outward supply, to a customer
    PURCHASE = "purchase"  # inward supply, from a vendor


class InvoiceStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class TransactionScope(StrEnum):
    INTRA_STATE = "intra_state"
    INTER_STATE = "inter_state"
    EXPORT = "export"
    SEZ_SUPPLY = "sez_supply"
    EXEMPT = "exempt"
    NIL_RATED = "nil_rated"


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, AuditActorMixin, TenantScopedMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_org_invoice_number", "organization_id", "invoice_number"),
    )

    direction: Mapped[InvoiceDirection] = mapped_column(
        str_enum_column(InvoiceDirection, "invoice_direction"), nullable=False
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        str_enum_column(InvoiceStatus, "invoice_status"),
        nullable=False,
        default=InvoiceStatus.UPLOADED,
    )

    # Storage reference
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Core extracted/normalized fields
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO YYYY-MM-DD
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    buyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    transaction_scope: Mapped[TransactionScope | None] = mapped_column(
        str_enum_column(TransactionScope, "transaction_scope"), nullable=True
    )

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )

    taxable_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Raw OCR output + per-field confidence, e.g. {"gstin": {"value": "...", "confidence": 0.98}}
    extracted_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    items: Mapped[list[InvoiceItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    taxes: Mapped[list[InvoiceTax]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hsn_sac: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    cess_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    cgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    sgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    igst: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cess: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class InvoiceTax(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Invoice-level tax summary (one row per tax component), independent of
    per-line detail — useful for return preparation aggregation."""

    __tablename__ = "invoice_taxes"
    __table_args__ = (UniqueConstraint("invoice_id", "tax_type", name="uq_invoice_tax_type"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    tax_type: Mapped[str] = mapped_column(String(10), nullable=False)  # cgst|sgst|igst|cess
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="taxes")
