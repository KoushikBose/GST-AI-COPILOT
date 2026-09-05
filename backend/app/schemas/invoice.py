"""Pydantic schemas for invoice upload, extraction and analysis."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.invoice import InvoiceDirection, InvoiceStatus, TransactionScope


class ExtractedField(BaseModel):
    value: Any
    confidence: float


class InvoiceItemOut(BaseModel):
    line_number: int
    description: str | None
    hsn_sac: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cess: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: uuid.UUID
    direction: InvoiceDirection
    status: InvoiceStatus
    invoice_number: str | None
    invoice_date: str | None
    supplier_name: str | None
    supplier_gstin: str | None
    buyer_name: str | None
    buyer_gstin: str | None
    place_of_supply: str | None
    currency: str
    transaction_scope: TransactionScope | None
    taxable_value: Decimal | None
    total_tax: Decimal | None
    grand_total: Decimal | None
    ocr_confidence: Decimal | None
    extracted_fields: dict[str, Any]
    items: list[InvoiceItemOut] = []

    model_config = {"from_attributes": True}


class InvoiceUploadResponse(BaseModel):
    invoice: InvoiceOut
    validation: dict[str, Any]
