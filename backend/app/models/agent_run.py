"""Agent execution audit trail — one row per supervisor invocation, with
child `AgentEvent` rows for each node transition / tool call. This is what
powers the observability requirement (latency, tool failures, routing) and
is distinct from LangGraph's own checkpoint state, which is optimized for
resuming execution, not for reporting.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"  # ended in a human-review handoff


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        str_enum_column(AgentRunStatus, "agent_run_status"),
        nullable=False,
        default=AgentRunStatus.RUNNING,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    events: Mapped[list[AgentEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentEvent.created_at"
    )


class AgentEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_events"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # "node_enter" | "node_exit" | "tool_call" | "tool_result" | "error"
    node_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="events")
