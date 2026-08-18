"""Tests for the local-source citation locator grammar (PI4).

A locator encodes a workspace-relative file path plus one adapter anchor so a citation resolves to
an exact span. It round-trips: `parse_locator(format_locator(loc)) == loc`.
"""

import pytest

from ace.intelligence.local_source_locator import LocalSourceLocator, format_locator, parse_locator


def _loc(path, kind, value):
    return LocalSourceLocator(relative_path=path, anchor_kind=kind, anchor_value=value)


def test_heading_locator_format():
    assert format_locator(_loc("notes/a.md", "heading", "One > Two")) == "notes/a.md#heading=One > Two"


def test_page_locator_format():
    assert format_locator(_loc("report.pdf", "page", "3")) == "report.pdf#page=3"


def test_row_locator_format():
    assert format_locator(_loc("data.csv", "row", "5")) == "data.csv#row=5"


def test_pointer_locator_format():
    assert format_locator(_loc("data.json", "pointer", "/a/b")) == "data.json#pointer=/a/b"


def test_no_anchor_locator_is_just_the_path():
    assert format_locator(_loc("readme.txt", "none", "")) == "readme.txt"


@pytest.mark.parametrize(
    "loc",
    [
        _loc("notes/a.md", "heading", "One > Two"),
        _loc("report.pdf", "page", "12"),
        _loc("data.csv", "row", "5"),
        _loc("data.json", "pointer", "/a/b/0"),
        _loc("readme.txt", "none", ""),
    ],
)
def test_round_trip(loc):
    assert parse_locator(format_locator(loc)) == loc


def test_path_containing_hash_is_encoded_and_round_trips():
    loc = _loc("weird#name.md", "heading", "H")
    encoded = format_locator(loc)
    assert "%23" in encoded  # the path's '#' is encoded so the anchor delimiter stays unambiguous
    assert parse_locator(encoded) == loc


def test_value_containing_equals_and_hash_round_trips():
    loc = _loc("a.md", "heading", "a = b # c")
    assert parse_locator(format_locator(loc)) == loc


def test_parse_rejects_unknown_anchor_kind():
    with pytest.raises(ValueError):
        parse_locator("a.md#bogus=x")


def test_locator_fits_the_citation_field_bound():
    # CitationV1Alpha1.locator is max_length=500; a typical locator is well under it.
    assert len(format_locator(_loc("notes/deep/a.md", "heading", "One > Two > Three"))) < 500
