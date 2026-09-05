# Architecture

See the [README's Architecture section](../README.md#architecture) for the system diagram and the LangGraph supervisor graph diagram.

## Layering principle

```
AI Layer (RAG, Agent Reasoning, Explanation)
        │
        ▼
Deterministic Core (GST Rules, Invoice Rules, Compliance Rules)
```

The deterministic core (`backend/app/rules/`) never imports from `app/llm/` or `app/agents/`. This is enforced by convention and code review, not a lint rule — if you're adding a rule that needs the LLM to decide something numeric, it belongs in an agent node, not in `app/rules/`.

## Modular monolith, not microservices

Per the build spec's explicit instruction, this is a single deployable backend (`backend/app/`) with clearly separated domains (`api/`, `services/`, `repositories/`, `rules/`, `agents/`, `rag/`, `ingestion/`). Each domain is import-clean enough to extract into its own service later without a rewrite, but there is no premature service-per-feature split.

## Request lifecycle (chat)

1. `POST /api/v1/chat` → `app/api/v1/chat.py`
2. `ConversationService.send_message` (`app/services/chat_service.py`) loads/creates the `ChatSession`, persists the user message, invokes the compiled LangGraph.
3. The graph (`app/agents/graph.py`) classifies intent, routes to a specialist node.
4. `gst_research_node` calls `answer_gst_question` (`app/rag/pipeline.py`), which does query rewriting → hybrid retrieval (`app/rag/hybrid_retriever.py`) across the relevant Qdrant collections → reranking → grounded LLM generation with mandatory citations.
5. `gst_calculation_node` extracts structured parameters via the LLM, then calls `GSTCalculator` (`app/rules/gst_calculator.py`) for the actual arithmetic — the LLM never computes a tax figure.
6. `ConversationService` persists the assistant message + an `AgentRun` audit row and returns the response.

## Multi-tenancy

Every tenant-scoped table carries `organization_id` (see `TenantScopedMixin`, `app/models/mixins.py`). Reads/writes go through `TenantScopedRepository` (`app/repositories/base.py`) or an equivalent explicit filter. Authorization (`app/security/dependencies.py`) re-verifies the caller's membership **against the database** on every request — the JWT's embedded org/role is only a default hint, never itself sufficient for access.
