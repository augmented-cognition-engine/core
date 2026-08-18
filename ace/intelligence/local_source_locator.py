"""Local-source citation locator grammar (PI4).

A citation over a local file must resolve to an exact span. This module defines the canonical
locator string that goes in ``CitationV1Alpha1.locator`` for local sources: a workspace-relative
path plus one adapter anchor.

Grammar::

    <path>[#<kind>=<value>]

where ``kind`` is one of ``heading``, ``page``, ``row``, or ``pointer`` (or omitted for a
whole-file locator). The path is percent-encoded so its own ``#`` never collides with the anchor
delimiter, and the anchor value is the remainder of the string, so values may contain ``=`` and
``#`` literally. ``format_locator`` and ``parse_locator`` round-trip.

The anchor kinds line up with what the PI2 adapters emit: Markdown heading paths, PDF page numbers,
CSV row numbers, and JSON Pointers. See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, unquote

AnchorKind = Literal["heading", "page", "row", "pointer", "none"]
_ANCHORED_KINDS = frozenset({"heading", "page", "row", "pointer"})


@dataclass(frozen=True, slots=True)
class LocalSourceLocator:
    """A workspace-relative path plus one adapter anchor."""

    relative_path: str
    anchor_kind: AnchorKind
    anchor_value: str


def format_locator(locator: LocalSourceLocator) -> str:
    """Render a locator to its canonical string form."""
    encoded_path = quote(locator.relative_path, safe="/")
    if locator.anchor_kind == "none":
        return encoded_path
    return f"{encoded_path}#{locator.anchor_kind}={locator.anchor_value}"


def parse_locator(value: str) -> LocalSourceLocator:
    """Parse a canonical locator string back into a `LocalSourceLocator`."""
    encoded_path, sep, rest = value.partition("#")
    path = unquote(encoded_path)
    if not sep:
        return LocalSourceLocator(relative_path=path, anchor_kind="none", anchor_value="")
    kind, kind_sep, anchor_value = rest.partition("=")
    if not kind_sep or kind not in _ANCHORED_KINDS:
        raise ValueError(f"unknown or malformed locator anchor: {rest!r}")
    return LocalSourceLocator(
        relative_path=path,
        anchor_kind=kind,  # type: ignore[arg-type]
        anchor_value=anchor_value,
    )
