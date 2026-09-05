"""Compliance check runs and the individual issues they surface."""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class ComplianceSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceCheck(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "compliance_checks"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    passed_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    issues: Mapped[list[ComplianceIssue]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class ComplianceIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_issues"

    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_checks.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[ComplianceSeverity] = mapped_column(
        str_enum_column(ComplianceSeverity, "compliance_severity"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    recommendation: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    check: Mapped[ComplianceCheck] = relationship(back_populates="issues")
