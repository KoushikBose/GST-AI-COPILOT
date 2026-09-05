"""Document loaders: turn raw file bytes into page-level text.

Every loader returns the same `LoadedDocument` shape regardless of source
format, so the chunking/embedding stage downstream never has to know
whether a piece of text came from a native PDF, an OCR'd scan, a DOCX, or a
spreadsheet.

Supported: PDF (native + scanned via OCR fallback), DOCX, XLSX, CSV, TXT,
JSON, HTML, PNG/JPG/JPEG/TIFF.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.core.errors import ValidationFailedError
from app.core.logging import get_logger
from app.ingestion.ocr import get_ocr_engine

logger = get_logger(__name__)

# A page with fewer real characters than this (relative to its rendered
# size) is treated as a scanned/image page and routed through OCR.
_MIN_NATIVE_TEXT_CHARS = 20


@dataclass
class LoadedPage:
    page_number: int
    text: str
    was_ocr: bool = False
    ocr_confidence: float | None = None


@dataclass
class LoadedDocument:
    pages: list[LoadedPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def page_count(self) -> int:
        return len(self.pages)


class _HTMLTextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and (text := data.strip()):
            self.chunks.append(text)


def _load_pdf(content: bytes) -> LoadedDocument:
    import pymupdf

    ocr_engine = None
    doc = LoadedDocument()
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        for i, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if len(text) >= _MIN_NATIVE_TEXT_CHARS:
                doc.pages.append(LoadedPage(page_number=i, text=text))
                continue

            # Likely a scanned page — rasterize and OCR it.
            logger.info("pdf_page_ocr_fallback", page=i)
            if ocr_engine is None:
                ocr_engine = get_ocr_engine()
            pixmap = page.get_pixmap(dpi=200)
            image_bytes = pixmap.tobytes("png")
            result = ocr_engine.extract(image_bytes)
            doc.pages.append(
                LoadedPage(
                    page_number=i,
                    text=result.text,
                    was_ocr=True,
                    ocr_confidence=result.confidence,
                )
            )
    return doc


def _load_docx(content: bytes) -> LoadedDocument:
    import docx

    document = docx.Document(io.BytesIO(content))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                paragraphs.append(" | ".join(cells))
    return LoadedDocument(pages=[LoadedPage(page_number=1, text="\n".join(paragraphs))])


def _load_xlsx(content: bytes) -> LoadedDocument:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    pages: list[LoadedPage] = []
    for i, sheet_name in enumerate(workbook.sheetnames, start=1):
        sheet = workbook[sheet_name]
        lines = [f"Sheet: {sheet_name}"]
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
        pages.append(LoadedPage(page_number=i, text="\n".join(lines)))
    return LoadedDocument(pages=pages)


def _load_csv(content: bytes) -> LoadedDocument:
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    lines = [" | ".join(row) for row in reader]
    return LoadedDocument(pages=[LoadedPage(page_number=1, text="\n".join(lines))])


def _load_txt(content: bytes) -> LoadedDocument:
    return LoadedDocument(
        pages=[LoadedPage(page_number=1, text=content.decode("utf-8", errors="replace"))]
    )


def _load_json(content: bytes) -> LoadedDocument:
    try:
        parsed = json.loads(content)
        text = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(f"Invalid JSON document: {exc}") from exc
    return LoadedDocument(pages=[LoadedPage(page_number=1, text=text)])


def _load_html(content: bytes) -> LoadedDocument:
    extractor = _HTMLTextExtractor()
    extractor.feed(content.decode("utf-8", errors="replace"))
    return LoadedDocument(pages=[LoadedPage(page_number=1, text="\n".join(extractor.chunks))])


def _load_image(content: bytes) -> LoadedDocument:
    result = get_ocr_engine().extract(content)
    return LoadedDocument(
        pages=[
            LoadedPage(
                page_number=1, text=result.text, was_ocr=True, ocr_confidence=result.confidence
            )
        ]
    )


_LOADERS_BY_MIME = {
    "application/pdf": _load_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _load_docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _load_xlsx,
    "text/csv": _load_csv,
    "text/plain": _load_txt,
    "application/json": _load_json,
    "text/html": _load_html,
    "image/png": _load_image,
    "image/jpeg": _load_image,
    "image/tiff": _load_image,
}

_LOADERS_BY_EXTENSION = {
    "pdf": _load_pdf,
    "docx": _load_docx,
    "xlsx": _load_xlsx,
    "csv": _load_csv,
    "txt": _load_txt,
    "json": _load_json,
    "html": _load_html,
    "htm": _load_html,
    "png": _load_image,
    "jpg": _load_image,
    "jpeg": _load_image,
    "tiff": _load_image,
}


def load_document(*, content: bytes, mime_type: str, filename: str) -> LoadedDocument:
    loader = _LOADERS_BY_MIME.get(mime_type)
    if loader is None:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        loader = _LOADERS_BY_EXTENSION.get(extension)
    if loader is None:
        raise ValidationFailedError(
            f"Unsupported document type: mime_type={mime_type!r}, filename={filename!r}"
        )
    return loader(content)
