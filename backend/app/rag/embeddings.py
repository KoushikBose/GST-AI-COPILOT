"""Embedding provider abstraction.

Default is `fastembed` — a local, open-source, ONNX-runtime embedding
library with no external API dependency (runs BAAI/bge-small-en-v1.5 by
default, matching EMBEDDING_MODEL). An Ollama-served embedding model is
supported as an alternative via EMBEDDING_PROVIDER=ollama.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...


class FastEmbedProvider(EmbeddingProvider):
    """Local ONNX embeddings via the `fastembed` library — no network call,
    no GPU required, runs fine on a laptop CPU."""

    def __init__(self, model_name: str, dimension: int) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        self._dimension = dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # fastembed is CPU-bound and synchronous; run it off the event loop.
        import asyncio

        def _run() -> list[list[float]]:
            return [vec.tolist() for vec in self._model.embed(texts)]

        return await asyncio.to_thread(_run)

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_documents([text])
        return results[0]

    @property
    def dimension(self) -> int:
        return self._dimension


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Uses an embedding-capable model served by Ollama (e.g. `nomic-embed-text`)."""

    def __init__(self, base_url: str, model: str, dimension: int, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dimension = dimension
        self.timeout = timeout

    async def _embed_one(self, client: httpx.AsyncClient, text: str) -> list[float]:
        response = await client.post(
            f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return [await self._embed_one(client, t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await self._embed_one(client, text)

    @property
    def dimension(self) -> int:
        return self._dimension


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "fastembed":
        return FastEmbedProvider(settings.embedding_model, settings.embedding_dim)
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddingProvider(
            settings.ollama_base_url, settings.embedding_model, settings.embedding_dim
        )
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'.")
