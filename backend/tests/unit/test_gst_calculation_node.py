from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.agents.nodes import gst_calculation
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolDefinition


class UnavailableLLM(LLMProvider):
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        raise RuntimeError("LLM is unavailable")

    async def stream_chat(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> AsyncIterator[str]:
        raise RuntimeError("LLM is unavailable")
        yield ""  # pragma: no cover - makes this an async generator

    async def health_check(self) -> bool:
        return False


def test_heuristic_extraction_handles_currency_commas_and_transaction_type() -> None:
    params = gst_calculation._heuristic_calculation_parameters(
        "Calculate GST on \u20b91,00,000 at 18% for an inter-state sale with 1% cess"
    )

    assert params == {
        "taxable_value": "100000",
        "gst_rate": "18",
        "transaction_type": "inter_state",
        "cess_rate": "1",
    }


@pytest.mark.asyncio
async def test_calculation_succeeds_when_llm_extraction_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(gst_calculation, "get_llm_provider", lambda: UnavailableLLM())

    result = await gst_calculation.gst_calculation_node(
        {"user_query": "Calculate GST on \u20b9100000 at 18% intra-state"}
    )

    assert result["confidence"] == 1.0
    assert result["calculations"]["cgst"] == "9000.00"
    assert result["calculations"]["sgst"] == "9000.00"
    assert result["calculations"]["grand_total"] == "118000.00"
