"""Strongly typed LangGraph state shared by every node in the supervisor
graph. Keeping this in one place (rather than each node inventing its own
shape) is what lets nodes be composed/reordered safely.
"""

from __future__ import annotations

from typing import Any, TypedDict


class GSTAgentState(TypedDict, total=False):
    # Identity / tenancy — every node that touches tenant data reads these,
    # never a global/ambient value, so the graph itself can't leak across
    # tenants even if a node forgets a filter.
    tenant_id: str | None
    user_id: str | None
    conversation_id: str | None

    # Input
    user_query: str
    conversation_history: list[str]

    # Routing
    intent: str

    # Working memory populated by specialist nodes
    retrieved_context: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    calculations: dict[str, Any]
    compliance_results: dict[str, Any]

    # Output
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    requires_human_review: bool
    error: str | None
