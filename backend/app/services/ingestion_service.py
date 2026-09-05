"""Document ingestion pipeline orchestration.

Upload -> hash/dedupe -> object storage -> load -> chunk -> embed ->
Qdrant upsert -> Postgres metadata -> BM25 rebuild.

This is what backs both "admin uploads a GST knowledge document" and
"user uploads a tenant-private document" — the only difference is whether
`organization_id` is set, which determines both the storage bucket and the
target Qdrant collection (public knowledge collections vs. `tenant_documents`
with a `tenant_id` payload filter).
"""

from __future__ import annotations

import hashlib
import uuid

from qdrant_client.http import models as qm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.ingestion.chunking import TextChunk, chunk_pages
from app.ingestion.loaders import load_document
from app.models.document import Document, DocumentChunk, DocumentStatus, DocumentType
from app.rag.bm25_index import BM25Document, BM25Index
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import KnowledgeCollection, ensure_collections, get_qdrant_client
from app.storage.object_storage import ObjectStorage

logger = get_logger(__name__)

_GLOBAL_COLLECTION_BY_TYPE: dict[DocumentType, KnowledgeCollection] = {
    DocumentType.ACT: KnowledgeCollection.GST_ACTS,
    DocumentType.RULE: KnowledgeCollection.GST_RULES,
    DocumentType.NOTIFICATION: KnowledgeCollection.GST_NOTIFICATIONS,
    DocumentType.CIRCULAR: KnowledgeCollection.GST_CIRCULARS,
    DocumentType.FAQ: KnowledgeCollection.GST_FAQ,
    DocumentType.CASE_KNOWLEDGE: KnowledgeCollection.GST_CASE_KNOWLEDGE,
}

_BUCKET_BY_TYPE: dict[DocumentType, str] = {
    DocumentType.INVOICE: "invoices",
    DocumentType.SUPPORTING: "supporting",
}


def _collection_for(
    document_type: DocumentType, organization_id: uuid.UUID | None
) -> KnowledgeCollection:
    if organization_id is not None:
        return KnowledgeCollection.TENANT_DOCUMENTS
    return _GLOBAL_COLLECTION_BY_TYPE.get(document_type, KnowledgeCollection.GST_FAQ)


def _bucket_for(document_type: DocumentType, organization_id: uuid.UUID | None) -> str:
    if document_type in _BUCKET_BY_TYPE:
        return _BUCKET_BY_TYPE[document_type]
    return "documents" if organization_id is not None else "knowledge"


class IngestionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        storage: ObjectStorage,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        # The embedding provider (fastembed) downloads a ~90MB model on first
        # construction, and the Qdrant client can attempt a connection — both
        # too slow for the upload request path. Resolve them lazily so only
        # the background `process_document` / `reindex_document` work pays
        # that cost, off the request/response cycle.
        self._embeddings = embedding_provider
        self._qdrant = None

    @property
    def embeddings(self) -> EmbeddingProvider:
        if self._embeddings is None:
            from app.rag.embeddings import get_embedding_provider

            self._embeddings = get_embedding_provider()
        return self._embeddings

    @property
    def qdrant(self):  # noqa: ANN201 - AsyncQdrantClient
        if self._qdrant is None:
            self._qdrant = get_qdrant_client()
        return self._qdrant

    async def create_pending_document(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
        document_type: DocumentType,
        title: str,
        organization_id: uuid.UUID | None,
        uploaded_by: uuid.UUID | None,
        jurisdiction: str = "India",
        effective_date: str | None = None,
        source_url: str | None = None,
    ) -> Document:
        """Fast path: dedupe, store the file and insert a `processing`
        Document row. The heavy OCR/chunk/embed/index work is done later by
        `process_document` (a background task) so the upload request returns
        immediately.
        """
        content_hash = hashlib.sha256(content).hexdigest()

        existing = (
            await self.session.execute(
                select(Document).where(
                    Document.content_hash == content_hash,
                    Document.organization_id == organization_id,
                    Document.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == DocumentStatus.FAILED:
                # A previous attempt at this exact file failed — let the user
                # retry by reusing the row rather than blocking with a 409.
                existing.status = DocumentStatus.PROCESSING
                existing.error_message = None
                existing.title = title
                existing.document_type = document_type
                await self.session.flush()
                try:
                    self.storage.upload_bytes(
                        bucket=existing.storage_bucket,
                        key=existing.storage_key,
                        data=content,
                        content_type=mime_type,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("document_storage_upload_failed", error=str(exc))
                    existing.status = DocumentStatus.FAILED
                    existing.error_message = f"Could not store the uploaded file: {exc}"
                    await self.session.flush()
                return existing
            raise ConflictError(
                "An identical document has already been ingested (matching content hash)."
            )

        bucket_kind = _bucket_for(document_type, organization_id)
        bucket = self.storage.bucket_for(bucket_kind)
        storage_key = f"{document_type.value}/{content_hash}/{filename}"

        document = Document(
            organization_id=organization_id,
            document_type=document_type,
            status=DocumentStatus.PROCESSING,
            title=title,
            filename=filename,
            mime_type=mime_type,
            storage_bucket=bucket,
            storage_key=storage_key,
            content_hash=content_hash,
            file_size_bytes=len(content),
            jurisdiction=jurisdiction,
            effective_date=effective_date,
            source_url=source_url,
            created_by=uploaded_by,
        )

        try:
            self.storage.upload_bytes(
                bucket=bucket, key=storage_key, data=content, content_type=mime_type
            )
        except Exception as exc:  # noqa: BLE001 - surface as a failed row, not a 500
            logger.error("document_storage_upload_failed", error=str(exc))
            document.status = DocumentStatus.FAILED
            document.error_message = f"Could not store the uploaded file: {exc}"

        self.session.add(document)
        await self.session.flush()
        return document

    async def process_document(self, document: Document) -> Document:
        """Heavy path: load stored content -> chunk -> embed -> Qdrant upsert
        -> BM25 rebuild, updating `document.status` to `indexed` / `failed`.
        Safe to run from a background task; never raises.
        """
        if document.status == DocumentStatus.FAILED and document.error_message:
            # Storage upload already failed — there is nothing to process.
            return document

        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        await self.session.flush()

        try:
            content = self.storage.download_bytes(
                bucket=document.storage_bucket, key=document.storage_key
            )
            loaded = load_document(
                content=content, mime_type=document.mime_type, filename=document.filename
            )
        except Exception as exc:  # noqa: BLE001 - record on the row, don't crash the task
            logger.error("document_load_failed", document_id=str(document.id), error=str(exc))
            document.status = DocumentStatus.FAILED
            document.error_message = f"Could not read this document: {exc}"
            await self.session.flush()
            return document

        document.page_count = loaded.page_count
        chunks = chunk_pages(loaded.pages)
        if not chunks:
            document.status = DocumentStatus.FAILED
            document.error_message = "No extractable text was found in this document."
            await self.session.flush()
            return document

        collection = _collection_for(document.document_type, document.organization_id)
        try:
            await self._index_chunks(document, chunks, collection)
            document.status = DocumentStatus.INDEXED
            await self.session.flush()
            await self._rebuild_bm25(collection.value)
        except Exception as exc:  # noqa: BLE001 - embedding/Qdrant outage
            logger.error("document_index_failed", document_id=str(document.id), error=str(exc))
            document.status = DocumentStatus.FAILED
            document.error_message = (
                f"Indexing failed (is Qdrant / the embedding model available?): {exc}"
            )
            await self.session.flush()
            return document

        logger.info(
            "document_ingested",
            document_id=str(document.id),
            collection=collection.value,
            chunk_count=len(chunks),
        )
        return document

    async def ingest_document(self, **kwargs) -> Document:
        """Create + fully process a document in one call (used by scripts and
        tests). The HTTP upload path splits these two steps instead."""
        document = await self.create_pending_document(**kwargs)
        return await self.process_document(document)

    async def _index_chunks(
        self, document: Document, chunks: list[TextChunk], collection: KnowledgeCollection
    ) -> None:
        """Embed `chunks`, upsert them into Qdrant, and persist matching
        `DocumentChunk` rows. Shared by both first-time ingestion and
        re-indexing so the two paths can never drift apart.
        """
        await ensure_collections()

        texts = [c.text for c in chunks]
        vectors = await self.embeddings.embed_documents(texts)

        points: list[qm.PointStruct] = []
        chunk_rows: list[DocumentChunk] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid4())
            payload = {
                "document_id": str(document.id),
                "tenant_id": str(document.organization_id) if document.organization_id else None,
                "document_type": document.document_type.value,
                "title": document.title,
                "section": chunk.section,
                "page": chunk.page,
                "effective_date": document.effective_date,
                "source": document.source_url,
                "jurisdiction": document.jurisdiction,
                "version": document.current_version,
                "text": chunk.text,
            }
            points.append(qm.PointStruct(id=point_id, vector=vector, payload=payload))
            chunk_rows.append(
                DocumentChunk(
                    document_id=document.id,
                    qdrant_collection=collection.value,
                    qdrant_point_id=point_id,
                    chunk_index=chunk.chunk_index,
                    section=chunk.section,
                    page=chunk.page,
                    token_count=max(len(chunk.text) // 4, 1),
                    metadata_json=payload,
                )
            )

        await self.qdrant.upsert(collection_name=collection.value, points=points)
        self.session.add_all(chunk_rows)
        await self.session.flush()

    async def _rebuild_bm25(self, collection_name: str) -> None:
        """Rebuild the BM25 index for a collection from all points currently
        stored in Qdrant. O(collection size) per ingestion — acceptable at
        MVP scale; move to incremental indexing if collections grow large.
        """
        documents: list[BM25Document] = []
        next_offset = None
        while True:
            records, next_offset = await self.qdrant.scroll(
                collection_name=collection_name,
                limit=256,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                text = (record.payload or {}).get("text", "")
                if text:
                    documents.append(BM25Document(chunk_id=str(record.id), text=text))
            if next_offset is None:
                break

        await BM25Index(collection_name).build(documents)

    async def reindex_document(self, document: Document) -> Document:
        """Re-fetch stored content and re-run the full ingestion pipeline for
        an existing document (used after a metadata edit or on manual
        re-index request)."""
        content = self.storage.download_bytes(
            bucket=document.storage_bucket, key=document.storage_key
        )
        # Remove old chunks (Qdrant + Postgres) before recreating them.
        old_chunks = list(document.chunks)
        if old_chunks:
            collection = old_chunks[0].qdrant_collection
            await self.qdrant.delete(
                collection_name=collection,
                points_selector=qm.PointIdsList(points=[c.qdrant_point_id for c in old_chunks]),
            )
            for chunk in old_chunks:
                await self.session.delete(chunk)
            await self.session.flush()

        document.current_version += 1
        document.status = DocumentStatus.PROCESSING
        await self.session.flush()

        loaded = load_document(
            content=content, mime_type=document.mime_type, filename=document.filename
        )
        chunks = chunk_pages(loaded.pages)
        if not chunks:
            document.status = DocumentStatus.FAILED
            document.error_message = "No extractable text was found on re-index."
            await self.session.flush()
            return document

        collection = _collection_for(document.document_type, document.organization_id)
        await self._index_chunks(document, chunks, collection)
        document.status = DocumentStatus.INDEXED
        document.page_count = loaded.page_count
        await self.session.flush()
        await self._rebuild_bm25(collection.value)
        return document
