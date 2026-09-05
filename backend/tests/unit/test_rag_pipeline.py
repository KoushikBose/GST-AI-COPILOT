"""Unit tests for the pure-function pieces of the RAG pipeline: citation
extraction and confidence estimation. No LLM, DB, or Qdrant required.
"""

from app.rag.hybrid_retriever import RetrievedChunk
from app.rag.pipeline import _estimate_confidence, _extract_cited_indices


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1",
        text="some GST provision text",
        score=score,
        document_id="doc-1",
        document_type="act",
        title="CGST Act",
        section="16",
        page=12,
        source=None,
        effective_date=None,
    )


class TestExtractCitedIndices:
    def test_extracts_valid_indices(self) -> None:
        text = "ITC is available under Section 16 [1], subject to conditions [2]."
        assert _extract_cited_indices(text, max_index=2) == {1, 2}

    def test_ignores_out_of_range_indices(self) -> None:
        text = "See [1] and [5]."
        assert _extract_cited_indices(text, max_index=2) == {1}

    def test_no_citations_returns_empty_set(self) -> None:
        assert _extract_cited_indices("No citations here.", max_index=3) == set()

    def test_deduplicates_repeated_citations(self) -> None:
        text = "As per [1], and again [1], and [2]."
        assert _extract_cited_indices(text, max_index=2) == {1, 2}


class TestEstimateConfidence:
    def test_no_chunks_yields_zero_confidence(self) -> None:
        assert _estimate_confidence([], cited_count=0) == 0.0

    def test_high_score_and_citations_yields_high_confidence(self) -> None:
        chunks = [_chunk(0.9), _chunk(0.85), _chunk(0.8)]
        confidence = _estimate_confidence(chunks, cited_count=2)
        assert confidence > 0.8

    def test_low_score_and_no_citations_yields_low_confidence(self) -> None:
        chunks = [_chunk(0.1)]
        confidence = _estimate_confidence(chunks, cited_count=0)
        assert confidence < 0.2

    def test_confidence_is_bounded_between_zero_and_one(self) -> None:
        chunks = [_chunk(5.0)]  # pathological score outside normal range
        confidence = _estimate_confidence(chunks, cited_count=10)
        assert 0.0 <= confidence <= 1.0
