"""Pure PDF structural parser.

`parse_pdf` extracts per-page text (via pypdf) and returns one page record per page, anchored by
its one-based page number so a citation can resolve to an exact page. Empty pages are kept so page
numbers stay exact. The parser reads no files and makes no acquisition or freshness claim.

pypdf is imported lazily and reached through an injectable `reader_factory`, so the adapter's own
logic is testable without a binary PDF fixture and without importing pypdf.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PdfPage:
    """One page of a PDF, anchored by its one-based page number."""

    page: int
    text: str
    anchor: str


@dataclass(frozen=True, slots=True)
class PdfDocument:
    """The structured translation of one PDF source."""

    pages: tuple[PdfPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _default_reader(content: bytes) -> Any:
    from io import BytesIO

    from pypdf import PdfReader

    return PdfReader(BytesIO(content))


def _structure(page_texts: list[str]) -> PdfDocument:
    pages = tuple(
        PdfPage(page=i, text=(text or "").strip(), anchor=f"page {i}") for i, text in enumerate(page_texts, start=1)
    )
    return PdfDocument(pages=pages)


def parse_pdf(
    content: bytes,
    *,
    reader_factory: Callable[[bytes], Any] = _default_reader,
) -> PdfDocument:
    """Parse PDF bytes into a structured document of page-anchored text."""
    reader = reader_factory(content)
    return _structure([page.extract_text() for page in reader.pages])
