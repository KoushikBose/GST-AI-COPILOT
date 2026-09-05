# RAG

## Pipeline

```
query -> rewrite (LLM) -> hybrid retrieve per collection
       -> RRF fusion (dense + BM25) -> cross-encoder rerank
       -> context assembly -> LLM (context-only) -> citation extraction
       -> confidence scoring -> guardrail (low-confidence disclaimer)
```

Implementation: `app/rag/query_rewriter.py`, `app/rag/hybrid_retriever.py`, `app/rag/reranker.py`, `app/rag/pipeline.py`.

## Collections

Defined in `app/rag/vector_store.py` (`KnowledgeCollection`):

| Collection | Contents |
|---|---|
| `gst_acts` | CGST/IGST/SGST Acts |
| `gst_rules` | GST Rules |
| `gst_notifications` | Notifications |
| `gst_circulars` | Circulars |
| `gst_faq` | FAQs |
| `gst_case_knowledge` | Case knowledge |
| `tenant_documents` | Tenant-private documents (filtered by `tenant_id` payload) |

`answer_gst_question` (`app/rag/pipeline.py`) fans out across all public knowledge collections plus, optionally, `tenant_documents` scoped to the caller's org.

## Grounding and citation enforcement

The system prompt in `app/rag/pipeline.py` requires every factual claim to carry a `[n]` citation referencing the numbered source block. `_extract_cited_indices` parses the model's actual citations back out of the answer text — indices outside the retrieved set are discarded, so a citation can never point at a source that wasn't actually retrieved. Confidence blends retrieval score with citation coverage (`_estimate_confidence`); below `_CONFIDENCE_THRESHOLD` (0.35) or with zero citations, the response is marked `requires_human_review` and gets the low-confidence disclaimer verbatim from the spec.

## Embeddings and reranking

- **Embeddings**: `fastembed` running `BAAI/bge-small-en-v1.5` locally (no network call, no API key) by default; `EMBEDDING_PROVIDER=ollama` is available as an alternative. Swap point: `app/rag/embeddings.py`.
- **Reranker**: `fastembed`'s cross-encoder (`BAAI/bge-reranker-base`), optional (`RERANKER_ENABLED`), fails soft (logs a warning, retrieval continues unranked) if the model can't load.
- **BM25**: `rank_bm25`, index persisted per-collection in Redis as the tokenized corpus (not the constructed object, which isn't safely round-trippable through Redis's text protocol) — see `app/rag/bm25_index.py`.

## Adding a new knowledge source

Upload via `POST /api/v1/documents/upload` with the right `document_type` — the ingestion pipeline (`app/services/ingestion_service.py`) handles OCR fallback, chunking, embedding, Qdrant upsert, and BM25 rebuild automatically. No RAG-layer code changes needed for a new document.
