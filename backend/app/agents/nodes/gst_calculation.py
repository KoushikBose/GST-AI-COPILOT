"""GST Calculation node.

The LLM's only job here is to *extract* structured parameters (taxable
value, rate, transaction type) from the user's natural-language request —
it never performs the arithmetic itself. `GSTCalculator` (the deterministic
core) does the actual math, and its output is what gets shown to the user.
This is the architectural boundary called out repeatedly in the spec:
LLM reasoning/extraction vs. deterministic calculation must never blur.
"""

from __future__ import annotations

import re
from typing import Any

import orjson

from app.agents.state import GSTAgentState
from app.core.errors import ValidationFailedError
from app.core.logging import get_logger
from app.llm.base import ChatMessage
from app.llm.factory import get_llm_provider
from app.rules.gst_calculator import GSTCalculator, TransactionType

logger = get_logger(__name__)

_EXTRACTION_PROMPT = """Extract GST calculation parameters from the user's message as JSON.

Output ONLY a JSON object with these exact keys:
- "taxable_value": number (the base amount before tax)
- "gst_rate": number (the GST percentage, e.g. 18 for 18%)
- "transaction_type": one of "intra_state", "inter_state", "export", \
"sez_supply", "exempt", "nil_rated"
- "cess_rate": number (0 if not mentioned)

If the transaction type isn't stated, default to "intra_state". If any \
required value is genuinely missing from the message, set it to null.
Output ONLY the JSON object, no other text."""

_CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?:\u20b9|\b(?:rs|inr)\.?)\s*([0-9][0-9,]*(?:\.\d+)?)", re.IGNORECASE
)
_AMOUNT_AFTER_CALCULATION_PATTERN = re.compile(
    r"\b(?:calculate|compute|work\s+out)\s+(?:the\s+)?(?:gst|tax)?\s*"
    r"(?:on|for)\s+(?:a\s+)?(?:taxable\s+(?:value\s+)?(?:of\s+)?)?"
    r"([0-9][0-9,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_PERCENTAGE_PATTERN = re.compile(r"([0-9]+(?:\.\d+)?)\s*%")
_CESS_RATE_PATTERN = re.compile(
    r"(?:\bcess(?:\s+rate)?\s*(?:of|at)?\s*([0-9]+(?:\.\d+)?)\s*%|"
    r"([0-9]+(?:\.\d+)?)\s*%\s*cess)"
    r"\b",
    re.IGNORECASE,
)
_VALID_TRANSACTION_TYPES = {transaction_type.value for transaction_type in TransactionType}


def _heuristic_calculation_parameters(query: str) -> dict[str, Any]:
    """Extract common calculation phrasing without relying on an LLM.

    This keeps the deterministic calculator usable when the local model is
    starting, unavailable, or returns malformed extraction JSON. The LLM is
    still used first for less conventional phrasing.
    """

    amount_match = _CURRENCY_AMOUNT_PATTERN.search(query)
    if amount_match is None:
        amount_match = _AMOUNT_AFTER_CALCULATION_PATTERN.search(query)
    taxable_value = amount_match.group(1).replace(",", "") if amount_match else None

    cess_match = _CESS_RATE_PATTERN.search(query)
    cess_rate = (cess_match.group(1) or cess_match.group(2)) if cess_match else "0"
    gst_rate = None
    for match in _PERCENTAGE_PATTERN.finditer(query):
        # Do not mistake a separately stated cess rate for the GST rate.
        if "cess" not in query[max(0, match.start() - 16) : match.start()].lower():
            gst_rate = match.group(1)
            break

    normalized_query = query.lower()
    if "sez" in normalized_query or "special economic zone" in normalized_query:
        transaction_type = TransactionType.SEZ_SUPPLY.value
    elif "export" in normalized_query:
        transaction_type = TransactionType.EXPORT.value
    elif "exempt" in normalized_query:
        transaction_type = TransactionType.EXEMPT.value
    elif "nil-rated" in normalized_query or "nil rated" in normalized_query:
        transaction_type = TransactionType.NIL_RATED.value
    elif any(term in normalized_query for term in ("inter-state", "interstate", "igst")):
        transaction_type = TransactionType.INTER_STATE.value
    else:
        transaction_type = TransactionType.INTRA_STATE.value

    return {
        "taxable_value": taxable_value,
        "gst_rate": gst_rate,
        "transaction_type": transaction_type,
        "cess_rate": cess_rate,
    }


def _parse_llm_parameters(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        params = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return {}
    return params if isinstance(params, dict) else {}


def _clean_numeric_value(value: Any) -> Any:
    return value.replace(",", "") if isinstance(value, str) else value


async def _extract_calculation_parameters(query: str) -> dict[str, Any]:
    heuristic_params = _heuristic_calculation_parameters(query)
    if heuristic_params["taxable_value"] is not None and heuristic_params["gst_rate"] is not None:
        return heuristic_params

    llm_params: dict[str, Any] = {}
    try:
        llm = get_llm_provider()
        response = await llm.chat(
            [
                ChatMessage(role="system", content=_EXTRACTION_PROMPT),
                ChatMessage(role="user", content=query),
            ],
            temperature=0.0,
        )
        llm_params = _parse_llm_parameters(response.content)
    except Exception as exc:
        logger.warning("gst_calculation_extraction_fallback", error=str(exc))

    transaction_type = llm_params.get("transaction_type")
    if transaction_type not in _VALID_TRANSACTION_TYPES:
        transaction_type = heuristic_params["transaction_type"]

    return {
        "taxable_value": _clean_numeric_value(
            llm_params.get("taxable_value") or heuristic_params["taxable_value"]
        ),
        "gst_rate": _clean_numeric_value(
            llm_params.get("gst_rate") or heuristic_params["gst_rate"]
        ),
        "transaction_type": transaction_type,
        "cess_rate": _clean_numeric_value(
            llm_params.get("cess_rate") or heuristic_params["cess_rate"]
        ),
    }


async def gst_calculation_node(state: GSTAgentState) -> GSTAgentState:
    params = await _extract_calculation_parameters(state["user_query"])

    if params.get("taxable_value") is None or params.get("gst_rate") is None:
        return {
            **state,
            "answer": (
                "I need both a taxable value and a GST rate to calculate this. "
                "Could you provide both?"
            ),
            "confidence": 0.0,
            "requires_human_review": False,
        }

    calculator = GSTCalculator()
    try:
        result = calculator.calculate(
            taxable_value=params["taxable_value"],
            gst_rate=params["gst_rate"],
            transaction_type=params.get("transaction_type") or TransactionType.INTRA_STATE,
            cess_rate=params.get("cess_rate") or 0,
        )
    except ValidationFailedError as exc:
        return {
            **state,
            "answer": f"I couldn't complete that calculation: {exc.message}",
            "confidence": 0.0,
            "requires_human_review": False,
        }

    answer_lines = [
        f"Taxable value: ₹{result.taxable_value}",
        f"Transaction type: {result.transaction_type.value.replace('_', ' ')}",
    ]
    if result.cgst or result.sgst:
        answer_lines.append(f"CGST: ₹{result.cgst}  |  SGST: ₹{result.sgst}")
    if result.igst:
        answer_lines.append(f"IGST: ₹{result.igst}")
    if result.cess:
        answer_lines.append(f"CESS: ₹{result.cess}")
    answer_lines.append(f"Total tax: ₹{result.total_tax}")
    answer_lines.append(f"Grand total: ₹{result.grand_total}")
    if result.warnings:
        answer_lines.append("")
        answer_lines.extend(f"⚠ {w}" for w in result.warnings)

    return {
        **state,
        "answer": "\n".join(answer_lines),
        "calculations": result.as_dict(),
        "confidence": 1.0,  # deterministic calculation — not an LLM guess
        "requires_human_review": False,
    }
