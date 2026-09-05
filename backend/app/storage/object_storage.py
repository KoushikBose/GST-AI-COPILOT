"""Object storage abstraction.

Every caller goes through an object-storage backend — never touches a
storage SDK directly — so a future move to AWS S3 or Azure Blob only
touches this file.

Two backends are provided, selected via ``OBJECT_STORAGE_PROVIDER``:

- ``minio`` (default): MinIO / any S3-compatible service. Use in any
  deployment that has a real object store reachable.
- ``filesystem``: stores objects as plain files under a local directory
  (``OBJECT_STORAGE_FILESYSTEM_ROOT``). No external service required —
  meant for local development and CI where standing up MinIO is overkill.
  Buckets become sub-directories; keys become nested paths beneath them.

Both implement :class:`ObjectStorage` (a runtime-checkable Protocol) so
callers never branch on which one is active.
"""

from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

from minio import Minio
from minio.error import S3Error

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class UploadResult:
    bucket: str
    key: str
    size_bytes: int
    etag: str


@runtime_checkable
class ObjectStorage(Protocol):
    """Common surface shared by every storage backend."""

    def ensure_buckets(self) -> None: ...

    def bucket_for(self, kind: str) -> str: ...

    def upload_bytes(
        self, *, bucket: str, key: str, data: bytes, content_type: str = ...
    ) -> UploadResult: ...

    def download_bytes(self, *, bucket: str, key: str) -> bytes: ...

    def delete(self, *, bucket: str, key: str) -> None: ...

    def object_exists(self, *, bucket: str, key: str) -> bool: ...

    def presigned_upload_url(
        self, *, bucket: str, key: str, expires_minutes: int = ...
    ) -> str: ...

    def presigned_download_url(
        self, *, bucket: str, key: str, expires_minutes: int = ...
    ) -> str: ...


def _bucket_map(settings: Settings) -> dict[str, str]:
    return {
        "documents": settings.object_storage_bucket_documents,
        "invoices": settings.object_storage_bucket_invoices,
        "supporting": settings.object_storage_bucket_supporting,
        "knowledge": settings.object_storage_bucket_knowledge,
        "exports": settings.object_storage_bucket_exports,
        "backups": settings.object_storage_bucket_backups,
    }


def _resolve_bucket(buckets: dict[str, str], kind: str) -> str:
    try:
        return buckets[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown storage bucket kind: {kind!r}") from exc


class MinioObjectStorage:
    """S3-compatible backend backed by the MinIO SDK."""

    def __init__(self, settings: Settings) -> None:
        self._client = Minio(
            settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=settings.object_storage_secure,
        )
        self._buckets = _bucket_map(settings)

    def ensure_buckets(self) -> None:
        for bucket in self._buckets.values():
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
                logger.info("storage_bucket_created", bucket=bucket)

    def bucket_for(self, kind: str) -> str:
        return _resolve_bucket(self._buckets, kind)

    def upload_bytes(
        self, *, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> UploadResult:
        result = self._client.put_object(
            bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )
        return UploadResult(bucket=bucket, key=key, size_bytes=len(data), etag=result.etag or "")

    def download_bytes(self, *, bucket: str, key: str) -> bytes:
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, *, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)

    def presigned_upload_url(self, *, bucket: str, key: str, expires_minutes: int = 15) -> str:
        return self._client.presigned_put_object(
            bucket, key, expires=timedelta(minutes=expires_minutes)
        )

    def presigned_download_url(self, *, bucket: str, key: str, expires_minutes: int = 15) -> str:
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(minutes=expires_minutes)
        )

    def object_exists(self, *, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                return False
            raise


class FilesystemObjectStorage:
    """Local-directory backend — one sub-directory per bucket, nested files
    per key. For development / CI where a real object store isn't available.
    """

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.object_storage_filesystem_root).expanduser().resolve()
        self._buckets = _bucket_map(settings)

    def _path(self, bucket: str, key: str) -> Path:
        # Guard against keys escaping their bucket directory via "..".
        target = (self._root / bucket / key).resolve()
        bucket_root = (self._root / bucket).resolve()
        if not target.is_relative_to(bucket_root):
            raise ValueError(f"Invalid storage key: {key!r}")
        return target

    def ensure_buckets(self) -> None:
        for bucket in self._buckets.values():
            (self._root / bucket).mkdir(parents=True, exist_ok=True)

    def bucket_for(self, kind: str) -> str:
        return _resolve_bucket(self._buckets, kind)

    def upload_bytes(
        self, *, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> UploadResult:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return UploadResult(bucket=bucket, key=key, size_bytes=len(data), etag="")

    def download_bytes(self, *, bucket: str, key: str) -> bytes:
        path = self._path(bucket, key)
        if not path.is_file():
            raise FileNotFoundError(f"No stored object at {bucket}/{key}")
        return path.read_bytes()

    def delete(self, *, bucket: str, key: str) -> None:
        self._path(bucket, key).unlink(missing_ok=True)

    def object_exists(self, *, bucket: str, key: str) -> bool:
        return self._path(bucket, key).is_file()

    def presigned_upload_url(self, *, bucket: str, key: str, expires_minutes: int = 15) -> str:
        return self._path(bucket, key).as_uri()

    def presigned_download_url(self, *, bucket: str, key: str, expires_minutes: int = 15) -> str:
        return self._path(bucket, key).as_uri()

    def purge(self) -> None:
        """Delete everything under the storage root (test/dev helper)."""
        if self._root.exists():
            shutil.rmtree(self._root)


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.object_storage_provider == "filesystem":
        storage = FilesystemObjectStorage(settings)
        storage.ensure_buckets()
        logger.info("object_storage_backend", provider="filesystem", root=str(storage._root))
        return storage
    return MinioObjectStorage(settings)
