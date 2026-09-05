"""Pydantic schemas for document management and RAG search."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus, DocumentType


class DocumentOut(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    status: DocumentStatus
    title: str
    filename: str
    mime_type: str
    page_count: int | None
    file_size_bytes: int | None
    jurisdiction: str
    effective_date: str | None
    source_url: str | None
    current_version: int
    error_message: str | None

    model_config = {"from_attributes": True}


class DocumentUploadMetadata(BaseModel):
    document_type: DocumentType
    title: str = Field(min_length=1, max_length=500)
    jurisdiction: str = "India"
    effective_date: str | None = None
    source_url: str | None = None


class RAGSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_type: DocumentType | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    include_tenant_documents: bool = True


class RAGSourceOut(BaseModel):
    document: str
    document_id: str
    section: str | None
    page: int | None
    relevance_score: float


class RAGSearchResponse(BaseModel):
    answer: str
    sources: list[RAGSourceOut]
    confidence: float
    disclaimer: str
