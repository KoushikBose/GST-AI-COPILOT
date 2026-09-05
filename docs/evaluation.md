# Evaluation

## Unit-level (no live services required)

```bash
cd backend
pytest tests/unit/test_evaluation_metrics.py -v
```

`backend/evaluation/metrics.py` implements Recall@k, Precision@k, MRR, NDCG@k, and a citation-accuracy/faithfulness proxy as pure functions — 20 unit tests cover them directly.

## Integration-level (requires the full stack)

```bash
make evaluate
```

Runs `backend/evaluation/run_evaluation.py`, which:

1. Loads `data/evaluation/retrieval_cases.jsonl` and runs each query through `HybridRetriever` across every knowledge collection, scoring Recall@5/MRR/NDCG@5 against the case's `relevant_document_titles` (matched by substring on the retrieved chunk's title, since exact chunk IDs aren't known ahead of ingestion).
2. Loads `data/evaluation/queries.jsonl` + `expected_answers.jsonl`, runs each through `answer_gst_question`, and scores answer relevancy (fraction of `must_mention` phrases present) and citation faithfulness.
3. Writes a timestamped JSON report to `data/evaluation/reports/`.

**Requires**: Ollama running with the configured model, and a Qdrant knowledge base with documents actually ingested (the seed datasets in `data/evaluation/` are illustrative — they reference document titles like "CGST Act" that only produce non-zero scores once you've ingested a document with that title). Not executed as part of this build since Docker was unavailable in the development environment — see [README's Known Limitations](../README.md#known-limitations).

## Extending the datasets

Add new cases to the four `.jsonl` files in `data/evaluation/` (one JSON object per line — see existing entries for the schema). No code changes needed; `run_evaluation.py` reads them directly.
