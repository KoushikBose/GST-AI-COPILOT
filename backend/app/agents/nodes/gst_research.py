"""GST Research node — thin LangGraph wrapper around the grounded RAG
pipeline (app/rag/pipeline.py). All the "answer using retrieved evidence,
cite sources, don't fabricate" logic lives in the pipeline; this node just
adapts it to/from graph state.
"""

from __future__ import annotations

from app.agents.state import GSTAgentState
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.rag.embeddings import get_embedding_provider
from app.rag.pipeline import answer_gst_question

logger = get_logger(__name__)


async def gst_research_node(state: GSTAgentState) -> GSTAgentState:
    try:
        llm = get_llm_provider()
        embeddings = get_embedding_provider()
        result = await answer_gst_question(
            llm=llm,
            embedding_provider=embeddings,
            question=state["user_query"],
            tenant_id=state.get("tenant_id"),
            conversation_history=state.get("conversation_history"),
            include_tenant_documents=False,
        )
    except Exception as exc:
        logger.warning(
            "gst_research_unavailable", error=str(exc) or repr(exc), error_type=type(exc).__name__
        )
        return {
            **state,
            "answer": (
                "I can't access the GST knowledge base right now. Please verify that Qdrant "
                "and the configured LLM service are running, then try again."
            ),
            "citations": [],
            "confidence": 0.0,
            "requires_human_review": True,
        }

    return {
        **state,
        "answer": result.answer,
        "citations": [
            {
                "document": c.document,
                "document_id": c.document_id,
                "section": c.section,
                "page": c.page,
                "relevance_score": c.relevance_score,
            }
            for c in result.sources
        ],
        "confidence": result.confidence,
        "requires_human_review": result.requires_human_review,
    }
