"""Upload validation: extension allowlist, size limit, and MIME sniffing
from file content (not just the client-supplied filename/Content-Type,
which are trivially spoofable).

This is a deliberately lightweight, dependency-free magic-byte sniffer
covering the file types this product actually accepts (see
ALLOWED_UPLOAD_EXTENSIONS) — not a general-purpose libmagic replacement.
"""

from __future__ import annotations

from app.config import get_settings
from app.core.errors import ValidationFailedError

_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),  # docx/xlsx are zip containers
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

_EXTENSION_TO_EXPECTED_MIME_FAMILY = {
    "pdf": {"application/pdf"},
    "docx": {"application/zip"},  # zip container; true MIME is OOXML-specific
    "xlsx": {"application/zip"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "tiff": {"image/tiff"},
    # Plain-text-ish formats have no reliable magic bytes; validated by
    # extension + a UTF-8 decode check instead.
    "csv": set(),
    "txt": set(),
    "json": set(),
    "html": set(),
    "htm": set(),
}


def sniff_mime_type(content: bytes) -> str | None:
    for magic, mime in _MAGIC_BYTES:
        if content.startswith(magic):
            return mime
    return None


def validate_upload(*, filename: str, content: bytes) -> None:
    settings = get_settings()

    if not filename or "." not in filename:
        raise ValidationFailedError("Uploaded file must have a valid extension.")

    extension = filename.rsplit(".", 1)[-1].lower()
    if extension not in settings.allowed_upload_extensions_list:
        raise ValidationFailedError(
            f"File type '.{extension}' is not allowed. "
            f"Allowed types: {', '.join(settings.allowed_upload_extensions_list)}."
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationFailedError(
            f"File exceeds the maximum upload size of {settings.max_upload_size_mb}MB."
        )
    if len(content) == 0:
        raise ValidationFailedError("Uploaded file is empty.")

    expected_families = _EXTENSION_TO_EXPECTED_MIME_FAMILY.get(extension, set())
    if expected_families:
        sniffed = sniff_mime_type(content)
        if sniffed not in expected_families:
            raise ValidationFailedError(
                f"File content does not match its '.{extension}' extension "
                "(failed magic-byte verification)."
            )
    else:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationFailedError(
                f"File claims to be a text-based '.{extension}' file but is not valid UTF-8."
            ) from exc
