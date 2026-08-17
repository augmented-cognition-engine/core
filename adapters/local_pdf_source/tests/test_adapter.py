"""Tests for the thin PDF structural parser.

The pypdf-backed text extraction is pypdf's responsibility; these tests inject a fake reader so
the adapter's own logic — page anchoring, whitespace trimming, empty-page handling — is verified
without a binary PDF fixture.
"""

from dataclasses import dataclass

from ace_local_pdf_source import PdfPage, parse_pdf


@dataclass
class _FakePage:
    _text: str

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, texts):
        self.pages = [_FakePage(t) for t in texts]


def _reader_of(*texts):
    return lambda content: _FakeReader(texts)


def test_each_page_is_anchored_by_one_based_page_number():
    doc = parse_pdf(b"%PDF", reader_factory=_reader_of("alpha", "beta"))
    assert doc.pages == (
        PdfPage(page=1, text="alpha", anchor="page 1"),
        PdfPage(page=2, text="beta", anchor="page 2"),
    )


def test_page_text_is_trimmed():
    doc = parse_pdf(b"%PDF", reader_factory=_reader_of("  spaced  \n"))
    assert doc.pages[0].text == "spaced"


def test_empty_pages_are_kept_so_page_numbers_stay_exact():
    doc = parse_pdf(b"%PDF", reader_factory=_reader_of("one", "", "three"))
    assert tuple(p.page for p in doc.pages) == (1, 2, 3)
    assert doc.pages[1] == PdfPage(page=2, text="", anchor="page 2")


def test_page_count_is_reported():
    doc = parse_pdf(b"%PDF", reader_factory=_reader_of("a", "b", "c"))
    assert doc.page_count == 3
