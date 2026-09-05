"""Cross-encoder reranking (BAAI/bge-reranker-base by default).

Dense + BM25 retrieval optimizes for recall; the reranker re-scores the
fused candidate set for actual query-passage relevance before the LLM ever
sees them, which is what keeps hallucination-by-irrelevant-context down.
Configurable/disable-able via RERANKER_ENABLED / RERANKER_MODEL.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model_name=model_name)

    async def rerank(
        self, query: str, candidates: list[str], top_k: int
    ) -> list[tuple[int, float]]:
        """Return [(original_index, score), ...] for the top_k candidates,
        sorted descending by relevance score."""
        if not candidates:
            return []

        def _run() -> list[float]:
            return list(self._model.rerank(query, candidates))

        scores = await asyncio.to_thread(_run)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


@lru_cache
def get_reranker() -> CrossEncoderReranker | None:
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    try:
        return CrossEncoderReranker(settings.reranker_model)
    except Exception as exc:  # model download/init failure must not crash retrieval
        logger.warning("reranker_init_failed", error=str(exc))
        return None
