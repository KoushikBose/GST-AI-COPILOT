"""Unit tests for the paragraph-aware chunker."""

from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import LoadedPage


class TestChunkPages:
    def test_short_page_becomes_single_chunk(self) -> None:
        pages = [LoadedPage(page_number=1, text="A short paragraph of GST guidance.")]
        chunks = chunk_pages(pages, max_chars=1500)
        assert len(chunks) == 1
        assert chunks[0].page == 1
        assert chunks[0].chunk_index == 0

    def test_long_page_splits_into_multiple_chunks(self) -> None:
        paragraph = "GST applies to the supply of goods and services. " * 100
        pages = [LoadedPage(page_number=1, text=paragraph)]
        chunks = chunk_pages(pages, max_chars=500, overlap_chars=50)
        assert len(chunks) > 1
        assert all(len(c.text) <= 500 + 60 for c in chunks)  # small slack for overlap join
        assert all(c.page == 1 for c in chunks)

    def test_chunks_never_span_page_boundaries(self) -> None:
        pages = [
            LoadedPage(page_number=1, text="Content on page one."),
            LoadedPage(page_number=2, text="Content on page two."),
        ]
        chunks = chunk_pages(pages, max_chars=1500)
        assert len(chunks) == 2
        assert chunks[0].page == 1
        assert chunks[1].page == 2

    def test_empty_pages_are_skipped(self) -> None:
        pages = [
            LoadedPage(page_number=1, text="   "),
            LoadedPage(page_number=2, text="Real content."),
        ]
        chunks = chunk_pages(pages)
        assert len(chunks) == 1
        assert chunks[0].page == 2

    def test_chunk_indices_are_sequential(self) -> None:
        paragraph = "Sentence one. Sentence two. Sentence three. " * 50
        pages = [LoadedPage(page_number=1, text=paragraph)]
        chunks = chunk_pages(pages, max_chars=400, overlap_chars=40)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_no_content_is_lost_for_pathological_unbroken_text(self) -> None:
        pages = [LoadedPage(page_number=1, text="x" * 5000)]
        chunks = chunk_pages(pages, max_chars=1000, overlap_chars=0)
        assert sum(len(c.text) for c in chunks) >= 5000
