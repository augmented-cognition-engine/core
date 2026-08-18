"""Dispatch tests for ``source_units_for``: routing by extension and the unsupported signal."""

from io import BytesIO

from ace_local_source_normalizers import source_units_for
from pypdf import PdfWriter


def _one_page_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_md_routes_to_markdown_normalizer():
    units = source_units_for("md", b"# Heading\nbody\n")
    assert len(units) == 1
    assert units[0].anchor_kind == "heading"
    assert units[0].anchor_value == "Heading"
    assert units[0].text == "body"


def test_csv_routes_to_csv_normalizer():
    units = source_units_for("csv", b"a,b\n1,2\n")
    assert len(units) == 1
    assert units[0].anchor_kind == "row"
    assert units[0].anchor_value == "1"
    assert units[0].text == "a: 1 | b: 2"


def test_json_routes_to_json_normalizer():
    units = source_units_for("json", b'{"k": "v"}')
    assert len(units) == 1
    assert units[0].anchor_kind == "pointer"
    assert units[0].anchor_value == "/k"
    assert units[0].text == "v"


def test_pdf_routes_to_pdf_normalizer():
    units = source_units_for("pdf", _one_page_pdf())
    assert len(units) == 1
    assert units[0].anchor_kind == "page"
    assert units[0].anchor_value == "1"


def test_extension_is_case_insensitive_and_dot_tolerant():
    assert source_units_for(".JSON", b'{"k": "v"}') == source_units_for("json", b'{"k": "v"}')


def test_unsupported_extension_returns_none():
    assert source_units_for("txt", b"hello") is None
    assert source_units_for("docx", b"...") is None
    assert source_units_for("", b"...") is None
