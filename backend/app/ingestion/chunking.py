"""Semantic-ish chunking: paragraph-aware recursive splitting with overlap.

Not a learned semantic segmenter — a deliberately simple, fast, dependency-
free splitter that respects paragraph/sentence boundaries where possible and
falls back to hard character splits for pathological input (e.g. one huge
unbroken line). Each chunk carries the source page number(s) so citations
can point a user at "Section X, Page Y" rather than just a raw offset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.loaders import LoadedPage

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page: int | None
    section: str | None = None


def _split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = _SENTENCE_SPLIT_RE.split(paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    # Extremely long single "sentences" (e.g. no punctuation) still need a
    # hard split so we never silently drop content into an oversized chunk.
    final: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            final.append(piece)
        else:
            final.extend(piece[i : i + max_chars] for i in range(0, len(piece), max_chars))
    return final


def chunk_pages(
    pages: list[LoadedPage],
    *,
    max_chars: int = 1500,
    overlap_chars: int = 200,
) -> list[TextChunk]:
    """Chunk a document's pages into overlapping text windows.

    Overlap is applied within a page's paragraph stream; chunks never span
    a page boundary, so page attribution on a citation is always exact.
    """
    chunks: list[TextChunk] = []
    index = 0

    for page in pages:
        if not page.text.strip():
            continue

        paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(page.text) if p.strip()]
        pieces: list[str] = []
        for paragraph in paragraphs:
            pieces.extend(_split_paragraph(paragraph, max_chars))

        buffer = ""
        for piece in pieces:
            candidate = f"{buffer}\n\n{piece}".strip() if buffer else piece
            if len(candidate) <= max_chars:
                buffer = candidate
                continue

            if buffer:
                chunks.append(TextChunk(text=buffer, chunk_index=index, page=page.page_number))
                index += 1
                # carry a small overlap forward for retrieval continuity
                buffer = buffer[-overlap_chars:] + "\n\n" + piece if overlap_chars else piece
                if len(buffer) > max_chars:
                    buffer = piece
            else:
                buffer = piece

        if buffer:
            chunks.append(TextChunk(text=buffer, chunk_index=index, page=page.page_number))
            index += 1

    return chunks
