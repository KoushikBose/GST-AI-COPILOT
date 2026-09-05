"""Unit tests for retrieval/generation evaluation metrics."""

import pytest

from evaluation.metrics import (
    aggregate,
    citation_accuracy,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestRecallAtK:
    def test_all_relevant_found_gives_full_recall(self) -> None:
        assert recall_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0

    def test_none_found_gives_zero_recall(self) -> None:
        assert recall_at_k(["x", "y"], {"a", "b"}, k=2) == 0.0

    def test_partial_recall(self) -> None:
        assert recall_at_k(["a", "x"], {"a", "b"}, k=2) == 0.5

    def test_no_relevant_docs_returns_zero(self) -> None:
        assert recall_at_k(["a", "b"], set(), k=2) == 0.0

    def test_k_smaller_than_relevant_set_caps_recall(self) -> None:
        # Only 1 slot considered, so at most 1 of 2 relevant docs can be found.
        assert recall_at_k(["a", "x", "b"], {"a", "b"}, k=1) == 0.5


class TestPrecisionAtK:
    def test_full_precision(self) -> None:
        assert precision_at_k(["a", "b"], {"a", "b"}, k=2) == 1.0

    def test_half_precision(self) -> None:
        assert precision_at_k(["a", "x"], {"a", "b"}, k=2) == 0.5

    def test_empty_retrieved_returns_zero(self) -> None:
        assert precision_at_k([], {"a"}, k=5) == 0.0


class TestMRR:
    def test_relevant_doc_at_rank_one(self) -> None:
        assert mean_reciprocal_rank(["a", "b"], {"a"}) == 1.0

    def test_relevant_doc_at_rank_three(self) -> None:
        assert mean_reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant_doc_found(self) -> None:
        assert mean_reciprocal_rank(["x", "y"], {"a"}) == 0.0


class TestNDCG:
    def test_perfect_ranking_gives_ndcg_one(self) -> None:
        assert ndcg_at_k(["a", "b"], {"a", "b"}, k=2) == 1.0

    def test_reversed_ranking_is_less_than_one(self) -> None:
        score = ndcg_at_k(["x", "a"], {"a"}, k=2)
        assert 0 < score < 1.0

    def test_no_relevant_in_result_set(self) -> None:
        assert ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0

    def test_empty_relevant_set_is_zero(self) -> None:
        assert ndcg_at_k(["a", "b"], set(), k=2) == 0.0


class TestCitationAccuracy:
    def test_all_citations_grounded(self) -> None:
        assert citation_accuracy(["doc1", "doc2"], {"doc1", "doc2", "doc3"}) == 1.0

    def test_hallucinated_citation_reduces_accuracy(self) -> None:
        assert citation_accuracy(["doc1", "doc99"], {"doc1"}) == 0.5

    def test_no_citations_returns_zero(self) -> None:
        assert citation_accuracy([], {"doc1"}) == 0.0


class TestAggregate:
    def test_computes_mean_min_max(self) -> None:
        result = aggregate([0.5, 1.0, 0.0])
        assert result["mean"] == pytest.approx(0.5)
        assert result["min"] == 0.0
        assert result["max"] == 1.0
        assert result["count"] == 3

    def test_empty_list_returns_zeros(self) -> None:
        result = aggregate([])
        assert result == {"mean": 0.0, "min": 0.0, "max": 0.0, "count": 0}
