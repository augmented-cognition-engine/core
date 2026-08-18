"""Host-side format normalizers composing the ACE Personal Intelligence local-source pipeline.

This package sits between the four thin per-format adapters and the format-agnostic mapping
contract in ace-core. It converts each adapter's native, anchor-carrying output into
``SourceUnit`` values whose ``(anchor_kind, anchor_value)`` round-trips through the citation
locator grammar, and offers a ``source_units_for(extension, content)`` dispatch that routes by
file extension and returns ``None`` for unsupported formats. See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from ace_local_source_normalizers.normalizers import (
    normalize_csv,
    normalize_json,
    normalize_markdown,
    normalize_pdf,
    source_units_for,
)

__all__ = [
    "normalize_csv",
    "normalize_json",
    "normalize_markdown",
    "normalize_pdf",
    "source_units_for",
]
