"""OpenAI-compatible LLM provider.

Demonstrates that `LLMProvider` is a genuine swap point, not just an Ollama
wrapper — an Azure OpenAI or other OpenAI-API-compatible endpoint can reuse
this class by pointing `base_url` at it. Not wired in by default; enabled
via LLM_PROVIDER=openai + OPENAI_API_KEY.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolCall, ToolDefinition


class OpenAILLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else 0.1,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"].get("arguments", {}),
            )
            for tc in choice.get("tool_calls", []) or []
        ]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice.get("content") or "",
            tool_calls=tool_calls,
            raw=data,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    async def stream_chat(
        self, messages: list[ChatMessage], *, temperature: float | None = None
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else 0.1,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client, client.stream(
            "POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if data == "[DONE]":
                    break
                import orjson

                chunk = orjson.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                if content := delta.get("content"):
                    yield content

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
                return response.status_code == 200
        except Exception:
            return False
