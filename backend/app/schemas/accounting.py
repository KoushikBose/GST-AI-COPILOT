"""Pydantic schemas for the double-entry accounting API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.accounting import AccountNature, BalanceSide, VoucherType


class LedgerGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    nature: AccountNature
    classification: str
    is_system: bool

    model_config = {"from_attributes": True}


class LedgerOut(BaseModel):
    id: uuid.UUID
    name: str
    group_id: uuid.UUID
    group_name: str
    nature: AccountNature
    opening_balance: Decimal
    opening_side: BalanceSide
    gstin: str | None
    is_system: bool
    is_active: bool
    notes: str | None

    model_config = {"from_attributes": True}


class CreateLedgerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    group_id: uuid.UUID
    opening_balance: Decimal = Decimal("0")
    opening_side: BalanceSide = BalanceSide.DEBIT
    gstin: str | None = Field(default=None, max_length=15)
    notes: str | None = Field(default=None, max_length=1000)


class VoucherEntryIn(BaseModel):
    ledger_id: uuid.UUID
    side: BalanceSide
    amount: Decimal = Field(gt=0)
    narration: str | None = Field(default=None, max_length=500)


class VoucherEntryOut(BaseModel):
    ledger_id: uuid.UUID
    side: BalanceSide
    amount: Decimal
    narration: str | None

    model_config = {"from_attributes": True}


class CreateVoucherRequest(BaseModel):
    voucher_type: VoucherType
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    entries: list[VoucherEntryIn] = Field(min_length=2)
    narration: str | None = Field(default=None, max_length=2000)
    reference: str | None = Field(default=None, max_length=100)


class VoucherOut(BaseModel):
    id: uuid.UUID
    voucher_type: VoucherType
    voucher_number: str
    date: str
    narration: str | None
    reference: str | None
    total_amount: Decimal
    source_invoice_id: uuid.UUID | None
    is_auto_generated: bool
    entries: list[VoucherEntryOut]

    model_config = {"from_attributes": True}


class VoucherSummaryOut(BaseModel):
    id: uuid.UUID
    voucher_type: VoucherType
    voucher_number: str
    date: str
    narration: str | None
    total_amount: Decimal
    is_auto_generated: bool

    model_config = {"from_attributes": True}
