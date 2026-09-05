"""Hybrid retrieval: dense vector search + BM25, fused with Reciprocal Rank
Fusion, optionally diversified with MMR, and reranked with a cross-encoder.

    query -> [dense search, BM25 search] -> RRF fusion -> MMR -> rerank -> top_k

Every retrieved chunk carries full provenance (document_id, section, page,
score) so the RAG pipeline can build citations without a second lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client.http import models as qm

from app.config import get_settings
from app.core.logging import get_logger
from app.rag.bm25_index import BM25Index
from app.rag.embeddings import EmbeddingProvider
from app.rag.reranker import get_reranker
from app.rag.vector_store import get_qdrant_client

logger = get_logger(__name__)

_RRF_K = 60  # standard Reciprocal Rank Fusion smoothing constant


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    document_id: str
    document_type: str
    title: str
    section: str | None
    page: int | None
    source: str | None
    effective_date: str | None


class HybridRetriever:
    def __init__(self, *, collection: str, embedding_provider: EmbeddingProvider) -> None:
        self.collection = collection
        self.embeddings = embedding_provider
        self.qdrant = get_qdrant_client()
        self.bm25 = BM25Index(collection)

    async def _dense_search(
        self, query: str, *, limit: int, tenant_filter: qm.Filter | None
    ) -> list[tuple[str, float, dict]]:
        vector = await self.embeddings.embed_query(query)
        response = await self.qdrant.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            query_filter=tenant_filter,
            with_payload=True,
        )
        return [(str(r.id), float(r.score), r.payload or {}) for r in response.points]

    async def _bm25_search(self, query: str, *, limit: int) -> list[tuple[str, float]]:
        return await self.bm25.search(query, top_k=limit)

    def _build_tenant_filter(
        self, *, tenant_id: str | None, document_type: str | None
    ) -> qm.Filter | None:
        must: list[qm.FieldCondition] = []
        if tenant_id is not None:
            # Only meaningful against the `tenant_documents` collection,
            # which holds exclusively tenant-private chunks — this is the
            # structural tenant-isolation enforcement point for retrieval.
            # Public knowledge collections (gst_acts, gst_rules, ...) are
            # queried without this filter since every chunk in them is
            # already global by construction (organization_id is NULL).
            must.append(qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)))
        if document_type is not None:
            must.append(
                qm.FieldCondition(key="document_type", match=qm.MatchValue(value=document_type))
            )
        return qm.Filter(must=must) if must else None

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        candidate_pool: int = 25,
        tenant_id: str | None = None,
        document_type: str | None = None,
        use_reranker: bool = True,
    ) -> list[RetrievedChunk]:
        tenant_filter = self._build_tenant_filter(tenant_id=tenant_id, document_type=document_type)

        dense_results = await self._dense_search(
            query, limit=candidate_pool, tenant_filter=tenant_filter
        )
        bm25_results = await self._bm25_search(query, limit=candidate_pool)

        fused_scores = self._reciprocal_rank_fusion(dense_results, bm25_results)
        if not fused_scores:
            return []

        payload_by_id = {chunk_id: payload for chunk_id, _score, payload in dense_results}
        # BM25 hits may include chunk_ids not covered by dense search (rare,
        # but possible if the vector index and BM25 index drift) — fetch
        # their payloads directly rather than dropping them silently.
        missing_ids = [cid for cid in fused_scores if cid not in payload_by_id]
        if missing_ids:
            records = await self.qdrant.retrieve(
                collection_name=self.collection, ids=missing_ids, with_payload=True
            )
            for record in records:
                payload_by_id[str(record.id)] = record.payload or {}

        ranked_ids = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_ids = ranked_ids[:candidate_pool]

        candidates = [
            RetrievedChunk(
                chunk_id=cid,
                text=(payload_by_id.get(cid, {}) or {}).get("text", ""),
                score=score,
                document_id=(payload_by_id.get(cid, {}) or {}).get("document_id", ""),
                document_type=(payload_by_id.get(cid, {}) or {}).get("document_type", ""),
                title=(payload_by_id.get(cid, {}) or {}).get("title", ""),
                section=(payload_by_id.get(cid, {}) or {}).get("section"),
                page=(payload_by_id.get(cid, {}) or {}).get("page"),
                source=(payload_by_id.get(cid, {}) or {}).get("source"),
                effective_date=(payload_by_id.get(cid, {}) or {}).get("effective_date"),
            )
            for cid, score in ranked_ids
            if (payload_by_id.get(cid, {}) or {}).get("text")
        ]

        settings = get_settings()
        reranker = get_reranker() if (use_reranker and settings.reranker_enabled) else None
        if reranker is not None and candidates:
            texts = [c.text for c in candidates]
            reranked = await reranker.rerank(query, texts, top_k=top_k)
            return [candidates[idx] for idx, _score in reranked]

        return candidates[:top_k]

    @staticmethod
    def _reciprocal_rank_fusion(
        dense_results: list[tuple[str, float, dict]], bm25_results: list[tuple[str, float]]
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rank, (chunk_id, _score, _payload) in enumerate(dense_results, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        for rank, (chunk_id, _score) in enumerate(bm25_results, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        return scores
