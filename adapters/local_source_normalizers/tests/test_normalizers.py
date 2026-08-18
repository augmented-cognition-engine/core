"""Per-format normalizer tests: real adapter output -> expected SourceUnits.

Each test feeds real adapter parser output through a normalizer and asserts the exact
``SourceUnit`` tuple, then confirms every emitted ``(anchor_kind, anchor_value)`` round-trips
through the locator grammar for that format.
"""

from ace_local_csv_source import parse_csv
from ace_local_json_source import parse_json
from ace_local_markdown_source import parse_markdown
from ace_local_pdf_source import parse_pdf
from ace_local_source_normalizers import (
    normalize_csv,
    normalize_json,
    normalize_markdown,
    normalize_pdf,
)

from ace.intelligence.local_source_locator import (
    LocalSourceLocator,
    format_locator,
    parse_locator,
)
from ace.intelligence.local_source_mapping import SourceUnit


def _assert_roundtrips(units):
    """Every unit's (anchor_kind, anchor_value) must survive format -> parse."""
    for unit in units:
        locator = format_locator(
            LocalSourceLocator(
                relative_path="notes/doc.ext",
                anchor_kind=unit.anchor_kind,
                anchor_value=unit.anchor_value,
            )
        )
        parsed = parse_locator(locator)
        assert parsed.anchor_kind == unit.anchor_kind
        assert parsed.anchor_value == unit.anchor_value


def test_markdown_sections_become_heading_units_with_none_preamble():
    doc = parse_markdown(b"intro\n# One\nalpha\n## Two\nbeta\n")
    units = normalize_markdown(doc)
    assert units == (
        SourceUnit(anchor_kind="none", anchor_value="", text="intro"),
        SourceUnit(anchor_kind="heading", anchor_value="One", text="alpha"),
        SourceUnit(anchor_kind="heading", anchor_value="One > Two", text="beta"),
    )
    _assert_roundtrips(units)


def test_markdown_heading_value_with_special_chars_roundtrips():
    doc = parse_markdown(b"# a=b # c\nbody\n")
    units = normalize_markdown(doc)
    assert units == (SourceUnit(anchor_kind="heading", anchor_value="a=b # c", text="body"),)
    _assert_roundtrips(units)


def test_csv_rows_become_row_units_with_readable_text():
    doc = parse_csv(b"name,role\nAda,eng\nGrace,adm\n")
    units = normalize_csv(doc)
    assert units == (
        SourceUnit(anchor_kind="row", anchor_value="1", text="name: Ada | role: eng"),
        SourceUnit(anchor_kind="row", anchor_value="2", text="name: Grace | role: adm"),
    )
    _assert_roundtrips(units)


def test_json_leaves_become_pointer_units_with_stringified_values():
    doc = parse_json(b'{"a": 1, "b": {"c": "x"}}')
    units = normalize_json(doc)
    assert units == (
        SourceUnit(anchor_kind="pointer", anchor_value="/a", text="1"),
        SourceUnit(anchor_kind="pointer", anchor_value="/b/c", text="x"),
    )
    _assert_roundtrips(units)


def test_pdf_pages_become_page_units():
    def fake_reader(_content):
        class _Page:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class _Reader:
            pages = [_Page("first page body"), _Page("second page body")]

        return _Reader()

    doc = parse_pdf(b"ignored", reader_factory=fake_reader)
    units = normalize_pdf(doc)
    assert units == (
        SourceUnit(anchor_kind="page", anchor_value="1", text="first page body"),
        SourceUnit(anchor_kind="page", anchor_value="2", text="second page body"),
    )
    _assert_roundtrips(units)
