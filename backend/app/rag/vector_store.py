"""Qdrant client factory and collection bootstrap.

Collections are one-per-knowledge-domain as specified in the architecture:
gst_acts, gst_rules, gst_notifications, gst_circulars, gst_faq,
gst_case_knowledge, tenant_documents.

Every point stores a `tenant_id` payload field (null for global/public GST
knowledge) so retrieval can be filtered per-tenant without ever leaking one
organization's private documents into another's search results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: AsyncQdrantClient | None = None
_EMBEDDED_LOCK_RETRIES = 5
_EMBEDDED_LOCK_BACKOFF_SECONDS = 1.5


class KnowledgeCollection(StrEnum):
    GST_ACTS = "gst_acts"
    GST_RULES = "gst_rules"
    GST_NOTIFICATIONS = "gst_notifications"
    GST_CIRCULARS = "gst_circulars"
    GST_FAQ = "gst_faq"
    GST_CASE_KNOWLEDGE = "gst_case_knowledge"
    TENANT_DOCUMENTS = "tenant_documents"


ALL_COLLECTIONS: tuple[KnowledgeCollection, ...] = tuple(KnowledgeCollection)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict


def _new_client(settings) -> AsyncQdrantClient:  # noqa: ANN001
    if settings.qdrant_local_path:
        # Embedded, on-disk Qdrant — no server or cloud cluster required.
        return AsyncQdrantClient(path=settings.qdrant_local_path)
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=settings.qdrant_prefer_grpc,
    )


def get_qdrant_client() -> AsyncQdrantClient:
    """Return the process-wide Qdrant client (created once).

    Embedded mode (`QDRANT_LOCAL_PATH`) takes an exclusive lock on the
    storage folder — only one client, in one process, can hold it. A brief
    conflict during a `--reload` restart is retried; a persistent failure
    means a second backend process is running (stop it) or Qdrant should be
    run as a server instead.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    attempts = _EMBEDDED_LOCK_RETRIES if settings.qdrant_local_path else 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _client = _new_client(settings)
            return _client
        except RuntimeError as exc:
            last_exc = exc
            if "already accessed" not in str(exc) or attempt == attempts:
                break
            logger.warning(
                "qdrant_embedded_locked_retrying",
                attempt=attempt,
                path=settings.qdrant_local_path,
            )
            time.sleep(_EMBEDDED_LOCK_BACKOFF_SECONDS)

    if settings.qdrant_local_path and last_exc is not None:
        raise RuntimeError(
            f"Could not open the embedded Qdrant store at {settings.qdrant_local_path!r}: "
            f"{last_exc}. Another backend process is almost certainly still running — stop "
            "every extra `uvicorn` process and keep only one, or run Qdrant as a server "
            "(set QDRANT_URL and leave QDRANT_LOCAL_PATH unset)."
        ) from last_exc
    raise last_exc  # type: ignore[misc]


async def close_qdrant() -> None:
    """Release the client (and, in embedded mode, the storage-folder lock)
    on app shutdown so a clean restart frees it."""
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("qdrant_close_failed", error=str(exc))
        _client = None


async def check_qdrant_health() -> bool:
    try:
        client = get_qdrant_client()
        await client.get_collections()
        return True
    except Exception:
        return False


async def ensure_collections() -> None:
    """Idempotently create all knowledge collections if they don't exist."""
    settings = get_settings()
    client = get_qdrant_client()
    existing = {c.name for c in (await client.get_collections()).collections}

    for collection in ALL_COLLECTIONS:
        if collection.value in existing:
            continue
        logger.info("qdrant_creating_collection", collection=collection.value)
        await client.create_collection(
            collection_name=collection.value,
            vectors_config=qm.VectorParams(
                size=settings.embedding_dim,
                distance=qm.Distance.COSINE,
            ),
        )
        # Payload indexes used for metadata filtering during retrieval.
        for field_name, schema in (
            ("tenant_id", qm.PayloadSchemaType.KEYWORD),
            ("document_type", qm.PayloadSchemaType.KEYWORD),
            ("jurisdiction", qm.PayloadSchemaType.KEYWORD),
            ("effective_date", qm.PayloadSchemaType.KEYWORD),
            ("document_id", qm.PayloadSchemaType.KEYWORD),
        ):
            await client.create_payload_index(
                collection_name=collection.value,
                field_name=field_name,
                field_schema=schema,
            )
