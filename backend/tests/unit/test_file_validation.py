"""Unit tests for upload validation (extension allowlist, size, magic-byte
sniffing). No network/DB required.
"""

import pytest

from app.core.errors import ValidationFailedError
from app.security.file_validation import sniff_mime_type, validate_upload


class TestSniffMimeType:
    def test_detects_pdf(self) -> None:
        assert sniff_mime_type(b"%PDF-1.7\n...") == "application/pdf"

    def test_detects_png(self) -> None:
        assert sniff_mime_type(b"\x89PNG\r\n\x1a\n...") == "image/png"

    def test_unknown_bytes_return_none(self) -> None:
        assert sniff_mime_type(b"not a known file format") is None


class TestValidateUpload:
    def test_valid_pdf_passes(self) -> None:
        validate_upload(filename="invoice.pdf", content=b"%PDF-1.7\nrest of pdf content")

    def test_missing_extension_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="invoice", content=b"%PDF-1.7")

    def test_disallowed_extension_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="malware.exe", content=b"MZ\x90\x00")

    def test_empty_file_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="invoice.pdf", content=b"")

    def test_content_mismatched_with_extension_rejected(self) -> None:
        # A PNG's magic bytes claiming to be a PDF should fail sniffing.
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="invoice.pdf", content=b"\x89PNG\r\n\x1a\nrest")

    def test_oversized_file_rejected(self) -> None:
        from app.config import get_settings

        settings = get_settings()
        oversized = b"%PDF-1.7" + b"0" * (settings.max_upload_size_mb * 1024 * 1024 + 1)
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="invoice.pdf", content=oversized)

    def test_valid_txt_passes(self) -> None:
        validate_upload(filename="notes.txt", content=b"hello GST world")

    def test_invalid_utf8_text_file_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            validate_upload(filename="notes.txt", content=b"\xff\xfe\x00\x01invalid")
