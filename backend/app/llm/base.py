"""LLM provider abstraction.

Business logic, agents and tools depend only on `LLMProvider` — never on
Ollama, OpenAI, or any other SDK directly. This is what makes the model
swappable via `LLM_PROVIDER` without touching a single agent/prompt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(ABC):
    """Common interface every LLM backend (Ollama, OpenAI, Anthropic, Bedrock,
    Azure OpenAI, ...) must implement."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
