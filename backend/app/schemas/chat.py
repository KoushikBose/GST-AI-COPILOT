"""Pydantic schemas for the chat/agent API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.chat import ChatChannel


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    channel: ChatChannel = ChatChannel.WEB

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message must not be blank")
        return message


class CitationOut(BaseModel):
    document: str
    document_id: str
    section: str | None
    page: int | None
    relevance_score: float


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    intent: str
    citations: list[CitationOut]
    confidence: float
    requires_human_review: bool
    calculations: dict | None = None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    intent: str | None
    citations: list[dict]
    confidence: float | None
    requires_human_review: bool

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str | None
    channel: ChatChannel
    is_archived: bool
    messages: list[ChatMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatSessionSummaryOut(BaseModel):
    id: uuid.UUID
    title: str | None
    channel: ChatChannel
    is_archived: bool

    model_config = {"from_attributes": True}
