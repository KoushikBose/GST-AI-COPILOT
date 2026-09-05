"""BM25 lexical retrieval, backed by `rank_bm25` and persisted per-collection
in Redis so the index survives process restarts without needing a dedicated
search engine (Elasticsearch/OpenSearch) for the MVP.

The tokenized corpus (not the constructed `BM25Okapi` object, which holds
numpy arrays and isn't safely round-trippable through Redis's text
protocol) is what's persisted, as JSON; `BM25Okapi` itself is rebuilt
in-memory on load. This intentionally stays a simple, swappable component:
`BM25Index` is the only thing the hybrid retriever talks to, so a future
move to a real search engine only touches this file.
"""

from __future__ import annotations

from dataclasses import dataclass

import orjson
from rank_bm25 import BM25Okapi

from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

_REDIS_KEY_PREFIX = "bm25_index"


def _tokenize(text: str) -> list[str]:
    return [tok for tok in text.lower().split() if tok]


@dataclass
class BM25Document:
    chunk_id: str
    text: str


class BM25Index:
    """One BM25 index per Qdrant collection name."""

    def __init__(self, collection: str) -> None:
        self.collection = collection
        self._bm25: BM25Okapi | None = None
        self._doc_ids: list[str] = []

    def _redis_key(self) -> str:
        return f"{_REDIS_KEY_PREFIX}:{self.collection}"

    async def build(self, documents: list[BM25Document]) -> None:
        """Rebuild the index from scratch (called after ingestion)."""
        tokenized = [_tokenize(d.text) for d in documents]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None
        self._doc_ids = [d.chunk_id for d in documents]

        payload = orjson.dumps({"tokenized": tokenized, "doc_ids": self._doc_ids})
        try:
            redis = get_redis()
            await redis.set(self._redis_key(), payload.decode("utf-8"))
        except Exception as exc:
            # Redis is optional MVP infrastructure — persisting the index is a
            # best-effort optimization. Losing it just means the index is
            # rebuilt on next ingestion; it must never fail ingestion itself.
            logger.warning(
                "bm25_index_persist_failed", collection=self.collection, error=str(exc)
            )
            return
        logger.info("bm25_index_built", collection=self.collection, doc_count=len(documents))

    async def _load(self) -> bool:
        if self._bm25 is not None:
            return True
        try:
            redis = get_redis()
            raw = await redis.get(self._redis_key())
        except Exception as exc:
            # Redis is optional infrastructure for the MVP — when it's
            # unavailable, lexical retrieval simply drops out and the hybrid
            # retriever falls back to dense-only search rather than failing
            # the whole RAG request.
            logger.warning("bm25_index_unavailable", collection=self.collection, error=str(exc))
            return False
        if raw is None:
            return False
        data = orjson.loads(raw)
        tokenized: list[list[str]] = data["tokenized"]
        self._doc_ids = data["doc_ids"]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None
        return True

    async def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return [(chunk_id, bm25_score), ...] sorted descending by score."""
        loaded = await self._load()
        if not loaded or self._bm25 is None:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._doc_ids, scores, strict=True), key=lambda x: x[1], reverse=True)
        return [(doc_id, float(score)) for doc_id, score in ranked[:top_k] if score > 0]
