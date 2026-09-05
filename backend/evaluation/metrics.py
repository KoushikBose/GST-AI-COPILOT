"""Retrieval and generation evaluation metrics.

Pure functions over ranked ID lists / scored candidates — no dependency on
Qdrant, an LLM, or the database, so they're fully unit-testable and reusable
from both `run_evaluation.py` and any future notebook/CI check.
"""

from __future__ import annotations

import math


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(top_k)


def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Binary-relevance NDCG@k (1 if relevant, 0 otherwise)."""
    top_k = retrieved_ids[:k]
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(top_k, start=1)
        if doc_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def citation_accuracy(cited_document_ids: list[str], retrieved_document_ids: set[str]) -> float:
    """Fraction of citations in a generated answer that actually correspond
    to a document that was retrieved (i.e. not hallucinated)."""
    if not cited_document_ids:
        return 0.0
    grounded = sum(1 for doc_id in cited_document_ids if doc_id in retrieved_document_ids)
    return grounded / len(cited_document_ids)


def aggregate(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    return {
        "mean": round(sum(values) / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "count": len(values),
    }
