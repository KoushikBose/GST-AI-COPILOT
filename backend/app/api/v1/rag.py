"""Direct RAG search endpoint — bypasses intent routing for callers (or UI
surfaces like a "Search GST Documents" page) that want a grounded answer
without going through the chat/agent flow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.llm.factory import get_llm_provider
from app.rag.embeddings import get_embedding_provider
from app.rag.pipeline import answer_gst_question
from app.schemas.document import RAGSearchRequest, RAGSearchResponse, RAGSourceOut
from app.security.dependencies import CurrentMembership, get_current_membership

router = APIRouter()


@router.post("/search", response_model=RAGSearchResponse)
async def search_gst_knowledge(
    body: RAGSearchRequest,
    membership: CurrentMembership = Depends(get_current_membership),
) -> RAGSearchResponse:
    result = await answer_gst_question(
        llm=get_llm_provider(),
        embedding_provider=get_embedding_provider(),
        question=body.query,
        tenant_id=str(membership.organization_id),
        include_tenant_documents=body.include_tenant_documents,
    )
    return RAGSearchResponse(
        answer=result.answer,
        sources=[
            RAGSourceOut(
                document=c.document,
                document_id=c.document_id,
                section=c.section,
                page=c.page,
                relevance_score=c.relevance_score,
            )
            for c in result.sources
        ],
        confidence=result.confidence,
        disclaimer=result.disclaimer,
    )
