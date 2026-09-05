"""LLM-assisted query rewriting for retrieval.

Turns a conversational, possibly ambiguous user question (which may refer
to earlier turns — "what about exports?") into a self-contained search
query better suited to dense/BM25 retrieval. Falls back to the original
query verbatim if the LLM call fails, since a slightly worse search query
is far better than a hard failure of the whole research flow.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMProvider

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You rewrite a user's question into a single, self-contained search "
    "query for retrieving Indian GST law documents (Acts, Rules, "
    "Notifications, Circulars, FAQs). Resolve pronouns and references to "
    "earlier conversation turns using the provided history. Output ONLY "
    "the rewritten query text, nothing else — no quotes, no explanation."
)


async def rewrite_query(
    llm: LLMProvider, *, question: str, conversation_history: list[str] | None = None
) -> str:
    history_text = ""
    if conversation_history:
        history_text = "\n".join(conversation_history[-6:])

    user_content = (
        f"Conversation history:\n{history_text}\n\nCurrent question: {question}"
        if history_text
        else f"Current question: {question}"
    )

    try:
        response = await llm.chat(
            [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_content),
            ],
            temperature=0.0,
        )
        rewritten = response.content.strip().strip('"')
        return rewritten or question
    except Exception as exc:
        logger.warning("query_rewrite_failed", error=str(exc))
        return question
