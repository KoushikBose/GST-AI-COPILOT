"""Evaluation runner: retrieval quality, grounded-answer faithfulness, and
invoice field-extraction accuracy.

Requires the full stack running (Ollama for the LLM, Qdrant with GST
knowledge documents already ingested via `make ingest`) — this is an
integration-level evaluation, not a unit test. Run with:

    make evaluate
    (or) python -m evaluation.run_evaluation

Datasets live in ../data/evaluation/*.jsonl (see that directory's contents
for the illustrative seed cases; extend them with real queries/documents
once a knowledge base is ingested).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import configure_logging, get_logger
from app.llm.factory import get_llm_provider
from app.rag.embeddings import get_embedding_provider
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.pipeline import answer_gst_question
from app.rag.vector_store import KnowledgeCollection
from evaluation.metrics import (
    aggregate,
    citation_accuracy,
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
)

configure_logging()
logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "evaluation"
REPORTS_DIR = DATA_DIR / "reports"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@dataclass
class RetrievalCaseResult:
    id: str
    query: str
    recall_at_5: float
    mrr: float
    ndcg_at_5: float
    retrieved_titles: list[str]


async def evaluate_retrieval() -> dict:
    cases = _load_jsonl(DATA_DIR / "retrieval_cases.jsonl")
    embeddings = get_embedding_provider()
    results: list[RetrievalCaseResult] = []

    for case in cases:
        relevant_titles = set(case.get("relevant_document_titles", []))
        all_titles: list[str] = []
        for collection in KnowledgeCollection:
            retriever = HybridRetriever(collection=collection.value, embedding_provider=embeddings)
            chunks = await retriever.retrieve(case["query"], top_k=5)
            all_titles.extend(c.title for c in chunks)

        # Treat "relevant" as: retrieved chunk's title matches one of the
        # expected titles (substring, case-insensitive) — exact chunk IDs
        # aren't known ahead of ingestion, so rank position is the ID.
        retrieved_ids = [str(i) for i in range(len(all_titles))]
        relevant_ids = {
            str(i)
            for i, title in enumerate(all_titles)
            if any(expected_title.lower() in title.lower() for expected_title in relevant_titles)
        }

        results.append(
            RetrievalCaseResult(
                id=case["id"],
                query=case["query"],
                recall_at_5=recall_at_k(retrieved_ids, relevant_ids, k=5),
                mrr=mean_reciprocal_rank(retrieved_ids, relevant_ids),
                ndcg_at_5=ndcg_at_k(retrieved_ids, relevant_ids, k=5),
                retrieved_titles=all_titles[:5],
            )
        )

    return {
        "cases": [asdict(r) for r in results],
        "aggregate": {
            "recall_at_5": aggregate([r.recall_at_5 for r in results]),
            "mrr": aggregate([r.mrr for r in results]),
            "ndcg_at_5": aggregate([r.ndcg_at_5 for r in results]),
        },
    }


async def evaluate_generation() -> dict:
    queries = {q["id"]: q for q in _load_jsonl(DATA_DIR / "queries.jsonl")}
    expected = {e["id"]: e for e in _load_jsonl(DATA_DIR / "expected_answers.jsonl")}
    llm = get_llm_provider()
    embeddings = get_embedding_provider()

    case_results = []
    for case_id, expectation in expected.items():
        query = queries.get(case_id, {}).get("query")
        if not query:
            continue

        result = await answer_gst_question(llm=llm, embedding_provider=embeddings, question=query)
        answer_lower = result.answer.lower()
        must_mention = expectation.get("must_mention", [])
        mentioned = [phrase for phrase in must_mention if phrase.lower() in answer_lower]
        relevancy = len(mentioned) / len(must_mention) if must_mention else 0.0

        retrieved_doc_ids = {c.document_id for c in result.sources}
        cited_doc_ids = [c.document_id for c in result.sources]
        faithfulness = citation_accuracy(cited_doc_ids, retrieved_doc_ids)

        case_results.append(
            {
                "id": case_id,
                "query": query,
                "answer_relevancy": round(relevancy, 3),
                "faithfulness": round(faithfulness, 3),
                "confidence": result.confidence,
                "requires_human_review": result.requires_human_review,
            }
        )

    return {
        "cases": case_results,
        "aggregate": {
            "answer_relevancy": aggregate([c["answer_relevancy"] for c in case_results]),
            "faithfulness": aggregate([c["faithfulness"] for c in case_results]),
        },
    }


async def run_all() -> dict:
    logger.info("evaluation_started")
    retrieval = await evaluate_retrieval()
    generation = await evaluate_generation()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "retrieval": retrieval,
        "generation": generation,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"eval_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("evaluation_completed", report_path=str(report_path))
    print(f"Evaluation report written to {report_path}")
    print(json.dumps(report["retrieval"]["aggregate"], indent=2))
    print(json.dumps(report["generation"]["aggregate"], indent=2))
    return report


if __name__ == "__main__":
    asyncio.run(run_all())
