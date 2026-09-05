"""Pydantic schemas for compliance and ITC endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.models.compliance import ComplianceSeverity
from app.models.gst_transaction import ITCStatus


class ComplianceIssueOut(BaseModel):
    severity: ComplianceSeverity
    rule_code: str
    field: str | None
    message: str
    recommendation: str | None

    model_config = {"from_attributes": True}


class ComplianceCheckOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID | None
    score: int
    passed_checks: int
    total_checks: int
    rules_version: str
    issues: list[ComplianceIssueOut]

    model_config = {"from_attributes": True}


class ITCRecordOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    status: ITCStatus
    eligible_amount: Decimal | None
    confidence: Decimal
    reasons: list[str]
    missing_evidence: list[str]
    citations: list[dict]
    requires_human_review: bool

    model_config = {"from_attributes": True}


class InvoiceAnalysisResponse(BaseModel):
    compliance: ComplianceCheckOut
    itc: ITCRecordOut
