"""End-to-end grounded RAG pipeline: the thing that turns a GST question into
a cited, confidence-scored answer.

    question -> rewrite -> hybrid retrieve (multi-collection) -> compress ->
    LLM (context-only) -> parse citations -> confidence -> guardrail

This is deliberately the *only* place that constructs the "answer GST
questions from retrieved evidence" prompt — the GST Research Agent (Phase 7)
is a thin LangGraph wrapper around `answer_gst_question`, not a second
implementation of the same logic.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMProvider
from app.rag.embeddings import EmbeddingProvider
from app.rag.hybrid_retriever import HybridRetriever, RetrievedChunk
from app.rag.query_rewriter import rewrite_query
from app.rag.vector_store import KnowledgeCollection

logger = get_logger(__name__)

LOW_CONFIDENCE_DISCLAIMER = (
    "I could not establish a sufficiently reliable answer from the available "
    "GST sources. Please review the cited material or escalate for "
    "professional verification."
)

STANDARD_DISCLAIMER = (
    "This response is generated from indexed GST reference material and is "
    "provided for informational purposes only. It does not constitute legal "
    "or tax advice — please verify against the cited sources or a qualified "
    "GST professional before relying on it for compliance or filing."
)

_CONFIDENCE_THRESHOLD = 0.35
_MAX_CONTEXT_CHUNKS = 8
_KNOWLEDGE_COLLECTIONS = (
    KnowledgeCollection.GST_ACTS,
    KnowledgeCollection.GST_RULES,
    KnowledgeCollection.GST_NOTIFICATIONS,
    KnowledgeCollection.GST_CIRCULARS,
    KnowledgeCollection.GST_FAQ,
    KnowledgeCollection.GST_CASE_KNOWLEDGE,
)

_SYSTEM_PROMPT = """You are the GST Research Agent inside GST AI Copilot, answering \
questions about Indian GST law using ONLY the numbered source excerpts provided below.

Rules you must follow:
1. Answer using ONLY the provided sources. Do not use outside knowledge of GST law.
2. Cite every factual claim with the source number(s) in square brackets, e.g. [1] or [2][3].
3. If the sources do not contain enough information to answer confidently, say so \
explicitly instead of guessing.
4. Never invent a section, rule number, or provision that is not present in the sources.
5. Clearly separate what the sources state from any reasoning/inference you add.
6. Keep the answer concise and directly responsive to the question.
"""


@dataclass
class Citation:
    index: int
    document_id: str
    document: str
    section: str | None
    page: int | None
    relevance_score: float


@dataclass
class RAGAnswer:
    answer: str
    sources: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    disclaimer: str = STANDARD_DISCLAIMER
    requires_human_review: bool = False


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        location = f"{chunk.title}"
        if chunk.section:
            location += f", Section {chunk.section}"
        if chunk.page:
            location += f", Page {chunk.page}"
        lines.append(f"[{i}] ({location})\n{chunk.text}")
    return "\n\n".join(lines)


def _extract_cited_indices(answer_text: str, max_index: int) -> set[int]:
    found = {int(n) for n in re.findall(r"\[(\d+)\]", answer_text)}
    return {n for n in found if 1 <= n <= max_index}


def _estimate_confidence(chunks: list[RetrievedChunk], cited_count: int) -> float:
    if not chunks:
        return 0.0
    top_scores = [c.score for c in chunks[:3]]
    avg_top_score = sum(top_scores) / len(top_scores)
    # Normalize: RRF+rerank scores aren't a clean 0-1 probability, so clamp
    # and blend with a citation-coverage signal (did the model actually
    # ground its answer in what we gave it?).
    normalized_retrieval = min(max(avg_top_score, 0.0), 1.0)
    citation_signal = min(cited_count / 2, 1.0)  # 2+ citations = full credit
    return round(0.6 * normalized_retrieval + 0.4 * citation_signal, 3)


async def answer_gst_question(
    *,
    llm: LLMProvider,
    embedding_provider: EmbeddingProvider,
    question: str,
    tenant_id: str | None = None,
    conversation_history: list[str] | None = None,
    include_tenant_documents: bool = False,
) -> RAGAnswer:
    search_query = await rewrite_query(
        llm, question=question, conversation_history=conversation_history
    )

    collections = list(_KNOWLEDGE_COLLECTIONS)
    if include_tenant_documents and tenant_id:
        collections.append(KnowledgeCollection.TENANT_DOCUMENTS)

    all_chunks: list[RetrievedChunk] = []
    for collection in collections:
        retriever = HybridRetriever(
            collection=collection.value, embedding_provider=embedding_provider
        )
        is_tenant_collection = collection == KnowledgeCollection.TENANT_DOCUMENTS
        chunks = await retriever.retrieve(
            search_query,
            top_k=4,
            tenant_id=tenant_id if is_tenant_collection else None,
        )
        all_chunks.extend(chunks)

    all_chunks.sort(key=lambda c: c.score, reverse=True)
    top_chunks = all_chunks[:_MAX_CONTEXT_CHUNKS]

    if not top_chunks:
        logger.info("rag_no_evidence_found", question=question)
        return RAGAnswer(
            answer=LOW_CONFIDENCE_DISCLAIMER,
            sources=[],
            confidence=0.0,
            disclaimer=LOW_CONFIDENCE_DISCLAIMER,
            requires_human_review=True,
        )

    context_block = _build_context_block(top_chunks)
    messages = [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=f"Sources:\n\n{context_block}\n\nQuestion: {question}",
        ),
    ]

    response = await llm.chat(messages, temperature=0.1)
    answer_text = response.content.strip()

    cited_indices = _extract_cited_indices(answer_text, max_index=len(top_chunks))
    confidence = _estimate_confidence(top_chunks, cited_count=len(cited_indices))

    sources = [
        Citation(
            index=i,
            document_id=chunk.document_id,
            document=chunk.title,
            section=chunk.section,
            page=chunk.page,
            relevance_score=round(chunk.score, 3),
        )
        for i, chunk in enumerate(top_chunks, start=1)
    ]

    requires_review = confidence < _CONFIDENCE_THRESHOLD or not cited_indices
    disclaimer = LOW_CONFIDENCE_DISCLAIMER if requires_review else STANDARD_DISCLAIMER

    return RAGAnswer(
        answer=answer_text,
        sources=sources,
        confidence=confidence,
        disclaimer=disclaimer,
        requires_human_review=requires_review,
    )


async def _retrieve_for_question(
    *,
    llm: LLMProvider,
    embedding_provider: EmbeddingProvider,
    question: str,
    tenant_id: str | None,
    conversation_history: list[str] | None,
    include_tenant_documents: bool,
) -> list[RetrievedChunk]:
    search_query = await rewrite_query(
        llm, question=question, conversation_history=conversation_history
    )
    collections = list(_KNOWLEDGE_COLLECTIONS)
    if include_tenant_documents and tenant_id:
        collections.append(KnowledgeCollection.TENANT_DOCUMENTS)

    all_chunks: list[RetrievedChunk] = []
    for collection in collections:
        retriever = HybridRetriever(
            collection=collection.value, embedding_provider=embedding_provider
        )
        is_tenant_collection = collection == KnowledgeCollection.TENANT_DOCUMENTS
        chunks = await retriever.retrieve(
            search_query,
            top_k=4,
            tenant_id=tenant_id if is_tenant_collection else None,
        )
        all_chunks.extend(chunks)

    all_chunks.sort(key=lambda c: c.score, reverse=True)
    return all_chunks[:_MAX_CONTEXT_CHUNKS]


async def stream_gst_answer(
    *,
    llm: LLMProvider,
    embedding_provider: EmbeddingProvider,
    question: str,
    tenant_id: str | None = None,
    conversation_history: list[str] | None = None,
    include_tenant_documents: bool = False,
) -> AsyncIterator[dict]:
    """Token-streaming variant of `answer_gst_question`.

    Yields ``{"type": "delta", "text": ...}`` events as the model produces
    the answer, then a single ``{"type": "final", ...}`` event carrying the
    citations, confidence and human-review flag — computed from the fully
    accumulated answer using the exact same logic as the non-streaming path.
    """
    top_chunks = await _retrieve_for_question(
        llm=llm,
        embedding_provider=embedding_provider,
        question=question,
        tenant_id=tenant_id,
        conversation_history=conversation_history,
        include_tenant_documents=include_tenant_documents,
    )

    if not top_chunks:
        yield {"type": "delta", "text": LOW_CONFIDENCE_DISCLAIMER}
        yield {
            "type": "final",
            "answer": LOW_CONFIDENCE_DISCLAIMER,
            "citations": [],
            "confidence": 0.0,
            "requires_human_review": True,
        }
        return

    context_block = _build_context_block(top_chunks)
    messages = [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(
            role="user", content=f"Sources:\n\n{context_block}\n\nQuestion: {question}"
        ),
    ]

    parts: list[str] = []
    async for token in llm.stream_chat(messages, temperature=0.1):
        parts.append(token)
        yield {"type": "delta", "text": token}

    answer_text = "".join(parts).strip()
    cited_indices = _extract_cited_indices(answer_text, max_index=len(top_chunks))
    confidence = _estimate_confidence(top_chunks, cited_count=len(cited_indices))
    requires_review = confidence < _CONFIDENCE_THRESHOLD or not cited_indices

    yield {
        "type": "final",
        "answer": answer_text,
        "citations": [
            {
                "document": chunk.title,
                "document_id": chunk.document_id,
                "section": chunk.section,
                "page": chunk.page,
                "relevance_score": round(chunk.score, 3),
            }
            for chunk in top_chunks
        ],
        "confidence": confidence,
        "requires_human_review": requires_review,
    }
