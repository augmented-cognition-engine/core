"""Pure JSON structural parser.

`parse_json` flattens JSON bytes into leaf values, each carrying its RFC 6901 JSON Pointer so a
citation can resolve to an exact location. Object and array leaves are emitted in document order;
pointer tokens escape `~` as `~0` and `/` as `~1`. The parser reads no files and makes no
acquisition or freshness claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JsonLeaf:
    """One leaf value, anchored by its JSON Pointer."""

    pointer: str
    value: Any
    anchor: str


@dataclass(frozen=True, slots=True)
class JsonDocument:
    """The structured translation of one JSON source."""

    leaves: tuple[JsonLeaf, ...]


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _walk(node: Any, pointer: str, out: list[JsonLeaf]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{pointer}/{_escape(str(key))}", out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, f"{pointer}/{index}", out)
    else:
        out.append(JsonLeaf(pointer=pointer, value=node, anchor=pointer))


def parse_json(content: bytes) -> JsonDocument:
    """Parse JSON bytes into a structured document of pointer-anchored leaves."""
    root = json.loads(content.decode("utf-8"))
    leaves: list[JsonLeaf] = []
    _walk(root, "", leaves)
    return JsonDocument(leaves=tuple(leaves))
