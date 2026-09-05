"""Ollama LLM provider — talks to a local/self-hosted Ollama server, or
Ollama Cloud (https://ollama.com), over the same HTTP API. No cloud API key
is required to run the assistant end to end against a local install; pass
`api_key` to authenticate against Ollama Cloud instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import orjson

from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = get_logger(__name__)


class OllamaLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        timeout: int = 120,
        num_ctx: int = 8192,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_temperature = temperature
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _to_ollama_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _to_ollama_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
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

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.default_temperature,
                "num_ctx": self.num_ctx,
            },
        }
        ollama_tools = self._to_ollama_tools(tools)
        if ollama_tools:
            payload["tools"] = ollama_tools

        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message = data.get("message", {})
        tool_calls: list[ToolCall] = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=str(call.get("id", i)),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}) or {},
                )
            )

        return LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            raw=data,
            model=self.model,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages),
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else self.default_temperature,
                "num_ctx": self.num_ctx,
            },
        }
        async with (
            httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client,
            client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    break

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5, headers=self._headers) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as exc:
            logger.warning("ollama_health_check_failed", error=str(exc))
            return False
