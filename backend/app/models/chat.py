"""Conversation persistence.

This is the long-term-memory counterpart to LangGraph's short-term
checkpointing (see app/agents/checkpointer.py, added in Phase 7): every
message that crosses the API is durably stored here regardless of which
LangGraph thread produced it, so conversation history survives checkpoint
pruning and is queryable for the UI's session list.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum_column,
)


class ChatChannel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    VOICE = "voice"
    API = "api"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[ChatChannel] = mapped_column(
        str_enum_column(ChatChannel, "chat_channel"), nullable=False, default=ChatChannel.WEB
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    langgraph_thread_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_archived: Mapped[bool] = mapped_column(default=False, nullable=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        str_enum_column(MessageRole, "message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
