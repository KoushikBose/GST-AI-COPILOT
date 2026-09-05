# Agents

## Supervisor graph

`app/agents/graph.py` builds a `StateGraph[GSTAgentState]` (state shape in `app/agents/state.py`):

```
START -> classify_intent -> {gst_research | gst_calculation | support} -> END
```

- **classify_intent** (`app/agents/intents.py`): LLM classification into one of 9 intents (`GST_QUERY`, `INVOICE_ANALYSIS`, `GST_CALCULATION`, `ITC_ANALYSIS`, `COMPLIANCE_CHECK`, `RETURN_PREPARATION`, `DOCUMENT_SEARCH`, `BUSINESS_ANALYTICS`, `SUPPORT`), with a regex-keyword heuristic fallback if the LLM call fails — the supervisor stays usable in degraded mode.
- **gst_research** (`app/agents/nodes/gst_research.py`): thin wrapper around the RAG pipeline (`app/rag/pipeline.py`).
- **gst_calculation** (`app/agents/nodes/gst_calculation.py`): LLM extracts parameters only; `GSTCalculator` performs the arithmetic.
- **support** (`app/agents/nodes/support.py`): honest fallback for intents without a wired specialist node yet (`INVOICE_ANALYSIS`, `ITC_ANALYSIS`, `COMPLIANCE_CHECK`, `RETURN_PREPARATION`, `BUSINESS_ANALYTICS` currently point users to the relevant dedicated page/endpoint instead of fabricating an answer inline).

Nodes are pure `state -> state` transforms with no direct DB access — persistence is the caller's job (`ConversationService`), which keeps the graph itself trivially unit-testable and reusable from any channel adapter.

## Checkpointing vs. conversation history

- **LangGraph checkpointing** (`MemorySaver`, swap point documented in `graph.py`) is short-term, in-process state for the graph's own resumability.
- **Conversation history** (`ChatSession` / `ChatMessage` tables) is the durable, queryable record shown in the UI — it survives restarts regardless of checkpointer backend.

## Tool system

Deterministic operations (`calculate_gst`, `validate_gstin`, `validate_invoice`) are plain typed Python functions in `app/rules/`, called directly by service/agent code rather than exposed as LLM-invoked "tools" — this keeps them outside the LLM's decision path entirely, which is stricter than the spec's general tool-calling pattern and intentional for anything that must be deterministic.

## Adding a new specialist node

1. Add the node function to `app/agents/nodes/`.
2. Register it in `app/agents/graph.py`'s `build_supervisor_graph()` (`add_node` + route in `_ROUTED_INTENTS`).
3. If it needs deterministic logic, put that logic in `app/rules/` and call it from the node — never inline arithmetic in the node itself.
