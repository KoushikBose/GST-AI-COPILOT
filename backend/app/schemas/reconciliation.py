"""Pydantic schemas for the GSTR-2A/2B reconciliation API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.reconciliation import ReconciliationMatchStatus, ReconciliationSource


class Gstr2bUploadResponse(BaseModel):
    period: str
    source: ReconciliationSource
    records_imported: int


class RunReconciliationRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$", description="Tax period as YYYY-MM")
    source: ReconciliationSource = ReconciliationSource.GSTR2B


class ReconciliationRunOut(BaseModel):
    id: uuid.UUID
    period: str
    source: ReconciliationSource
    book_invoice_count: int
    return_record_count: int
    matched_count: int
    mismatch_count: int
    missing_in_return_count: int
    missing_in_books_count: int
    itc_at_risk: Decimal
    potential_unclaimed_itc: Decimal

    model_config = {"from_attributes": True}


class ReconciliationMatchOut(BaseModel):
    id: uuid.UUID
    status: ReconciliationMatchStatus
    invoice_id: uuid.UUID | None
    gstr2b_record_id: uuid.UUID | None
    supplier_gstin: str | None
    invoice_number: str | None
    invoice_date: str | None
    book_taxable_value: Decimal | None
    book_tax: Decimal | None
    return_taxable_value: Decimal | None
    return_tax: Decimal | None
    taxable_value_difference: Decimal
    tax_difference: Decimal
    itc_at_risk: Decimal
    reasons: list[str]

    model_config = {"from_attributes": True}
