"""Fallback node for intents that don't (yet) have a dedicated specialist
node wired into the graph, and for genuinely out-of-scope requests.

Returning an honest "not available yet" message beats a fabricated answer —
this node exists specifically so unimplemented intents fail safely instead
of silently falling through to a generic chat completion.
"""

from __future__ import annotations

from app.agents.state import GSTAgentState

_NOT_YET_AVAILABLE = {
    "INVOICE_ANALYSIS": (
        "Invoice-specific analysis isn't available in this conversation yet — "
        "upload the invoice from the Invoices page to run extraction, "
        "validation and compliance checks on it."
    ),
    "ITC_ANALYSIS": (
        "ITC eligibility analysis is available from an invoice's detail page "
        "once it has been uploaded and processed."
    ),
    "COMPLIANCE_CHECK": (
        "Compliance checks run against a specific invoice or transaction — "
        "open the invoice you'd like checked and request a compliance check "
        "from there."
    ),
    "RETURN_PREPARATION": (
        "Return preparation aggregates your sales/purchase transactions for "
        "a period — start it from the Returns page."
    ),
    "BUSINESS_ANALYTICS": (
        "Business analytics are available on the Dashboard and Analytics pages."
    ),
}

_GENERIC_SUPPORT = (
    "I can help with GST law questions, GST calculations, invoice analysis, "
    "compliance checks, ITC assessments and return preparation. Could you "
    "rephrase your request around one of those?"
)


async def support_node(state: GSTAgentState) -> GSTAgentState:
    message = _NOT_YET_AVAILABLE.get(state.get("intent", ""), _GENERIC_SUPPORT)
    return {
        **state,
        "answer": message,
        "confidence": 1.0,
        "requires_human_review": False,
    }
