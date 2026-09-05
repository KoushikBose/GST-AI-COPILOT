"""Pydantic schemas for the deterministic GST calculation/validation API."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.rules.gst_calculator import TransactionType


class GSTCalculateRequest(BaseModel):
    taxable_value: Decimal = Field(gt=-1)
    gst_rate: Decimal = Field(ge=0, le=100)
    transaction_type: TransactionType
    cess_rate: Decimal = Field(default=Decimal("0"), ge=0)


class GSTCalculateResponse(BaseModel):
    rules_version: str
    transaction_type: TransactionType
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cess: Decimal
    total_tax: Decimal
    grand_total: Decimal
    warnings: list[str]


class GSTINValidateRequest(BaseModel):
    gstin: str


class GSTINValidateResponse(BaseModel):
    is_valid: bool
    gstin: str
    state_code: str | None
    pan: str | None
    errors: list[str]
