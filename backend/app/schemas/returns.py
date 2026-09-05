"""Pydantic schemas for the return-preparation API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.gst_return import ReturnStatus, ReturnType


class GenerateReturnRequest(BaseModel):
    return_type: ReturnType
    period: str = Field(pattern=r"^\d{4}-\d{2}$", description="Tax period as YYYY-MM")


class GSTReturnOut(BaseModel):
    id: uuid.UUID
    return_type: ReturnType
    period: str
    status: ReturnStatus
    invoice_count: int
    total_taxable_value: Decimal
    total_tax: Decimal
    summary: dict
    rules_version: str
    review_notes: str | None = None
    export_storage_key: str | None = None

    model_config = {"from_attributes": True}


class GSTReturnSummaryOut(BaseModel):
    id: uuid.UUID
    return_type: ReturnType
    period: str
    status: ReturnStatus
    invoice_count: int
    total_taxable_value: Decimal
    total_tax: Decimal

    model_config = {"from_attributes": True}
