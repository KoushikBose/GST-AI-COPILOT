"""Double-entry accounting: chart of accounts (groups + ledgers) and
vouchers (journal entries).

This is the "Tally-like" bookkeeping layer that sits under the invoice /
GST features: an invoice is *posted* to a Sales or Purchase voucher whose
entries hit the party ledger, the sales/purchase ledger and the GST duty
ledgers. The deterministic engine in ``app/rules/accounting.py`` turns the
resulting voucher entries into the Trial Balance, P&L and Balance Sheet.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    AuditActorMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class AccountNature(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"


class BalanceSide(StrEnum):
    DEBIT = "dr"
    CREDIT = "cr"


class VoucherType(StrEnum):
    SALES = "sales"
    PURCHASE = "purchase"
    RECEIPT = "receipt"
    PAYMENT = "payment"
    CONTRA = "contra"
    JOURNAL = "journal"
    DEBIT_NOTE = "debit_note"
    CREDIT_NOTE = "credit_note"


# `balance_side` is used on two tables (Ledger.opening_side, VoucherEntry.side).
# Bind the enum type to the metadata once so `create_all` emits a single
# `CREATE TYPE balance_side` instead of one per column.
_BALANCE_SIDE = SAEnum(
    BalanceSide,
    name="balance_side",
    values_callable=lambda cls: [e.value for e in cls],
    metadata=Base.metadata,
)


class LedgerGroup(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "ledger_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_ledger_group_org_name"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_groups.id", ondelete="SET NULL"), nullable=True
    )
    nature: Mapped[AccountNature] = mapped_column(
        str_enum_column(AccountNature, "account_nature"), nullable=False
    )
    # Finer bucket that drives the statements + GST mapping, e.g.
    # "sales" | "purchase" | "receivable" | "payable" | "duties_taxes" |
    # "bank" | "cash" | "capital" | "current_asset" | "fixed_asset" |
    # "current_liability" | "direct_expense" | "indirect_expense" |
    # "direct_income" | "indirect_income".
    classification: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    ledgers: Mapped[list[Ledger]] = relationship(back_populates="group")


class Ledger(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "ledgers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_ledger_org_name"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_groups.id", ondelete="RESTRICT"), nullable=False
    )
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    opening_side: Mapped[BalanceSide] = mapped_column(
        _BALANCE_SIDE, nullable=False, default=BalanceSide.DEBIT
    )
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional link back to customer/vendor master data.
    party_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # customer | vendor
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    group: Mapped[LedgerGroup] = relationship(back_populates="ledgers")


class Voucher(UUIDPrimaryKeyMixin, TimestampMixin, AuditActorMixin, TenantScopedMixin, Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "voucher_type", "voucher_number", name="uq_voucher_org_type_number"
        ),
    )

    voucher_type: Mapped[VoucherType] = mapped_column(
        str_enum_column(VoucherType, "voucher_type"), nullable=False
    )
    voucher_number: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # ISO YYYY-MM-DD
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)

    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    entries: Mapped[list[VoucherEntry]] = relationship(
        back_populates="voucher",
        cascade="all, delete-orphan",
        order_by="VoucherEntry.sort_order",
    )


class VoucherEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voucher_entries"

    voucher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vouchers.id", ondelete="CASCADE"), nullable=False
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledgers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    side: Mapped[BalanceSide] = mapped_column(_BALANCE_SIDE, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    narration: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    voucher: Mapped[Voucher] = relationship(back_populates="entries")
