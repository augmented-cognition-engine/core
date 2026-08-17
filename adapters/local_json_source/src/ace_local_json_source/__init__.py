"""Thin JSON structural source adapter for ACE Personal Intelligence.

A pure translator: JSON bytes in, leaf values out, each anchored by its RFC 6901 JSON Pointer for
PI4's citation locator grammar. It performs no filesystem traversal, authority evaluation,
digesting, or admission. See docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from ace_local_json_source.adapter import JsonDocument, JsonLeaf, parse_json

__all__ = ["JsonDocument", "JsonLeaf", "parse_json"]
