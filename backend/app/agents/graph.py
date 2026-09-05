"""Supervisor Agent — LangGraph StateGraph that classifies intent and routes
to the appropriate specialist node.

    START -> classify_intent -> {gst_research | gst_calculation | support} -> END

Node functions are pure `state -> state` transforms (see app/agents/nodes/)
with no direct DB access, which keeps the graph itself trivially testable
and reusable across channels (web, WhatsApp, voice — see app/channels/).
Persistence (AgentRun/AgentEvent rows, chat message history) is the calling
service's responsibility, not the graph's.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.intents import Intent, classify_intent
from app.agents.nodes.gst_calculation import gst_calculation_node
from app.agents.nodes.gst_research import gst_research_node
from app.agents.nodes.support import support_node
from app.agents.state import GSTAgentState
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider

logger = get_logger(__name__)

_ROUTED_INTENTS = {
    Intent.GST_QUERY.value: "gst_research",
    Intent.DOCUMENT_SEARCH.value: "gst_research",
    Intent.GST_CALCULATION.value: "gst_calculation",
}


async def _classify_intent_node(state: GSTAgentState) -> GSTAgentState:
    llm = get_llm_provider()
    intent = await classify_intent(llm, state["user_query"])
    logger.info("intent_classified", intent=intent.value, query=state["user_query"][:200])
    return {**state, "intent": intent.value}


def _route_after_classification(state: GSTAgentState) -> str:
    return _ROUTED_INTENTS.get(state.get("intent", ""), "support")


def build_supervisor_graph() -> StateGraph:
    graph = StateGraph(GSTAgentState)

    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("gst_research", gst_research_node)
    graph.add_node("gst_calculation", gst_calculation_node)
    graph.add_node("support", support_node)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_classification,
        {
            "gst_research": "gst_research",
            "gst_calculation": "gst_calculation",
            "support": "support",
        },
    )
    graph.add_edge("gst_research", END)
    graph.add_edge("gst_calculation", END)
    graph.add_edge("support", END)

    return graph


@lru_cache
def get_compiled_supervisor_graph():
    """Compiled graph with in-memory checkpointing.

    `MemorySaver` gives short-term (within-process) conversation-state
    persistence for LangGraph's own resumability. It is NOT the durable
    conversation history — that's `ChatSession`/`ChatMessage` in Postgres
    (see app/models/chat.py), which survives restarts and process
    recycling. Swap in a Postgres-backed checkpointer
    (`langgraph-checkpoint-postgres`) here for multi-process deployments
    without touching any node or the graph topology.
    """
    graph = build_supervisor_graph()
    return graph.compile(checkpointer=MemorySaver())
