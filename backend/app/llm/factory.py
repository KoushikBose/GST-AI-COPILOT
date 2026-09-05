"""LLM provider factory.

Every call site gets an `LLMProvider` from `get_llm_provider()` — never
constructs `OllamaLLMProvider` (or any concrete provider) directly. Swapping
the runtime is a one-line env var change (`LLM_PROVIDER=openai`), not a
code change.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.errors import DependencyUnavailableError
from app.llm.base import LLMProvider
from app.llm.ollama_provider import OllamaLLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()

    if settings.llm_provider == "ollama":
        return OllamaLLMProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.ollama_temperature,
            timeout=settings.ollama_timeout,
            num_ctx=settings.ollama_num_ctx,
            api_key=settings.ollama_api_key,
        )

    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAILLMProvider

        if not settings.openai_api_key:
            raise DependencyUnavailableError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not configured."
            )
        return OpenAILLMProvider(api_key=settings.openai_api_key, model=settings.openai_model)

    raise DependencyUnavailableError(
        f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
        "Supported: ollama, openai (azure_openai/anthropic adapters can be added the same way)."
    )
