"""Tests for the local-source document mapping contract (PI4).

Mapping turns an adapter's normalized source units into typed observations, each carrying a
resolvable citation locator and the source digest as provenance. It composes the locator grammar.
"""

from ace.intelligence.local_source_locator import parse_locator
from ace.intelligence.local_source_mapping import (
    MappedObservation,
    SourceUnit,
    map_document_units,
)

_DIGEST = "sha256:" + "0" * 64


def test_one_observation_per_unit_with_locator_and_provenance():
    units = (
        SourceUnit(anchor_kind="heading", anchor_value="One > Two", text="alpha"),
        SourceUnit(anchor_kind="heading", anchor_value="One > Three", text="beta"),
    )
    observations = map_document_units("notes/a.md", _DIGEST, units)
    assert observations == (
        MappedObservation(
            relative_path="notes/a.md",
            locator="notes/a.md#heading=One > Two",
            text="alpha",
            source_digest=_DIGEST,
        ),
        MappedObservation(
            relative_path="notes/a.md",
            locator="notes/a.md#heading=One > Three",
            text="beta",
            source_digest=_DIGEST,
        ),
    )


def test_each_anchor_kind_produces_a_resolvable_locator():
    units = (
        SourceUnit(anchor_kind="page", anchor_value="3", text="p"),
        SourceUnit(anchor_kind="row", anchor_value="5", text="r"),
        SourceUnit(anchor_kind="pointer", anchor_value="/a/b", text="j"),
    )
    observations = map_document_units("f", _DIGEST, units)
    resolved = [parse_locator(o.locator) for o in observations]
    assert [(r.anchor_kind, r.anchor_value) for r in resolved] == [
        ("page", "3"),
        ("row", "5"),
        ("pointer", "/a/b"),
    ]


def test_units_with_empty_text_are_skipped():
    units = (
        SourceUnit(anchor_kind="heading", anchor_value="Empty", text="   "),
        SourceUnit(anchor_kind="heading", anchor_value="Full", text="content"),
    )
    observations = map_document_units("a.md", _DIGEST, units)
    assert [o.text for o in observations] == ["content"]


def test_whole_file_unit_uses_a_pathonly_locator():
    units = (SourceUnit(anchor_kind="none", anchor_value="", text="body"),)
    (observation,) = map_document_units("readme.txt", _DIGEST, units)
    assert observation.locator == "readme.txt"
    assert parse_locator(observation.locator).anchor_kind == "none"


def test_no_units_maps_to_no_observations():
    assert map_document_units("a.md", _DIGEST, ()) == ()
