"""Pydantic schemas for the human-in-the-loop approval queue API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.approval import ApprovalRisk, ApprovalStatus, ApprovalType


class ApprovalOut(BaseModel):
    id: uuid.UUID
    approval_type: ApprovalType
    risk: ApprovalRisk
    status: ApprovalStatus
    entity_type: str
    entity_id: str
    ai_recommendation: dict
    evidence: list
    confidence: Decimal | None
    assigned_to: uuid.UUID | None
    decided_by: uuid.UUID | None
    decision_notes: str | None
    final_payload: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "modify"]
    notes: str | None = Field(default=None, max_length=2000)
    final_payload: dict | None = None


class ApprovalCountsOut(BaseModel):
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    modified: int = 0
