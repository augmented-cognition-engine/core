"""Local-source document mapping contract (PI4).

Mapping turns a document's normalized *source units* into typed observations, each carrying a
resolvable citation locator (via the locator grammar) and the source digest as provenance. It is
format-agnostic: a per-format normalizer (host side, next to the adapters) converts an adapter's
native output — Markdown sections, PDF pages, CSV rows, JSON leaves — into ``SourceUnit`` values;
this contract maps those units uniformly.

A unit with no material text yields no observation, so a citation always points at citable
content. See docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from ace.intelligence.local_source_locator import (
    AnchorKind,
    LocalSourceLocator,
    format_locator,
)


@dataclass(frozen=True, slots=True)
class SourceUnit:
    """One citable unit of a document, in a format-agnostic shape."""

    anchor_kind: AnchorKind
    anchor_value: str
    text: str


@dataclass(frozen=True, slots=True)
class MappedObservation:
    """A citable observation derived from one source unit."""

    relative_path: str
    locator: str
    text: str
    source_digest: str


def map_document_units(
    relative_path: str,
    source_digest: str,
    units: tuple[SourceUnit, ...],
) -> tuple[MappedObservation, ...]:
    """Map normalized source units to citable observations, skipping empty-text units."""
    observations: list[MappedObservation] = []
    for unit in units:
        if not unit.text.strip():
            continue
        locator = format_locator(
            LocalSourceLocator(
                relative_path=relative_path,
                anchor_kind=unit.anchor_kind,
                anchor_value=unit.anchor_value,
            )
        )
        observations.append(
            MappedObservation(
                relative_path=relative_path,
                locator=locator,
                text=unit.text,
                source_digest=source_digest,
            )
        )
    return tuple(observations)
