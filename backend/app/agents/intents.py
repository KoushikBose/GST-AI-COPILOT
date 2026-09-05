"""Intent taxonomy and classification for the Supervisor Agent."""

from __future__ import annotations

import re
from enum import StrEnum

from app.core.logging import get_logger
from app.llm.base import LLMProvider

logger = get_logger(__name__)


class Intent(StrEnum):
    GST_QUERY = "GST_QUERY"
    INVOICE_ANALYSIS = "INVOICE_ANALYSIS"
    GST_CALCULATION = "GST_CALCULATION"
    ITC_ANALYSIS = "ITC_ANALYSIS"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    RETURN_PREPARATION = "RETURN_PREPARATION"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    BUSINESS_ANALYTICS = "BUSINESS_ANALYTICS"
    SUPPORT = "SUPPORT"


_INTENT_DESCRIPTIONS = {
    Intent.GST_QUERY: "General GST law questions, rates, concepts, definitions, procedures",
    Intent.INVOICE_ANALYSIS: "Questions about a specific uploaded invoice's extracted fields",
    Intent.GST_CALCULATION: "Requests to compute CGST/SGST/IGST/CESS for a given amount",
    Intent.ITC_ANALYSIS: "Input Tax Credit eligibility questions",
    Intent.COMPLIANCE_CHECK: "Requests to check invoice/transaction compliance",
    Intent.RETURN_PREPARATION: "Requests related to preparing GST return data",
    Intent.DOCUMENT_SEARCH: "Requests to find/search GST knowledge documents",
    Intent.BUSINESS_ANALYTICS: "Dashboard/analytics/reporting questions about the business's data",
    Intent.SUPPORT: "Anything unrelated to GST, or a request the assistant cannot fulfil",
}

_SYSTEM_PROMPT = (
    "Classify the user's message into exactly one of these intents:\n"
    + "\n".join(f"- {i.value}: {desc}" for i, desc in _INTENT_DESCRIPTIONS.items())
    + "\n\nRespond with ONLY the intent label, nothing else."
)

# Cheap heuristic fallback used when the LLM is unavailable or returns an
# unparseable response — keeps the supervisor usable in degraded mode.
_KEYWORD_RULES: list[tuple[re.Pattern[str], Intent]] = [
    (re.compile(r"\bitc\b|input tax credit", re.I), Intent.ITC_ANALYSIS),
    (
        re.compile(r"\bcalculate\b|\bcgst\b|\bsgst\b|\bigst\b|\bcess\b", re.I),
        Intent.GST_CALCULATION,
    ),
    (re.compile(r"\bcompliance\b|\bcompliant\b", re.I), Intent.COMPLIANCE_CHECK),
    (re.compile(r"\breturn\b|\bgstr\b|\bfiling\b", re.I), Intent.RETURN_PREPARATION),
    (re.compile(r"\binvoice\b", re.I), Intent.INVOICE_ANALYSIS),
    (re.compile(r"\bdashboard\b|\banalytic|\breport\b", re.I), Intent.BUSINESS_ANALYTICS),
    (re.compile(r"\bsearch\b|\bfind\b|\bdocument\b", re.I), Intent.DOCUMENT_SEARCH),
]


def _heuristic_classify(query: str) -> Intent:
    for pattern, intent in _KEYWORD_RULES:
        if pattern.search(query):
            return intent
    return Intent.GST_QUERY


async def classify_intent(llm: LLMProvider, query: str) -> Intent:
    """Route requests without making a model call on the critical path.

    Every currently implemented route is covered by the deterministic rules
    above. This avoids a model outage delaying the calculator or preventing a
    clear knowledge-base availability message from reaching the user.
    """

    del llm  # Kept in the public interface so graph call sites stay stable.
    return _heuristic_classify(query)
