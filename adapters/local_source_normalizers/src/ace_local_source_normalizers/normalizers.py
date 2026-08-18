"""Host-side format normalizers for ACE Personal Intelligence (PI4).

This is the seam that composes the local-source pipeline end-to-end. Each thin adapter
(``ace-local-{markdown,csv,json,pdf}-source``) is a pure translator: bytes in, a structured,
anchor-carrying document out. This package converts that native adapter output into the
format-agnostic :class:`~ace.intelligence.local_source_mapping.SourceUnit` shape that
``map_document_units`` maps into citable observations.

Each ``SourceUnit`` carries an ``(anchor_kind, anchor_value)`` pair chosen so it round-trips
through the locator grammar (``format_locator``/``parse_locator``) for its format:

- Markdown: one unit per section, ``anchor_kind="heading"``, ``anchor_value`` = the ``" > "``
  heading-path string. A preamble section (empty heading path) uses ``anchor_kind="none"``.
- CSV: one unit per data row, ``anchor_kind="row"``, ``anchor_value`` = the one-based row index,
  text = a readable ``key: value`` join of the row's cells.
- JSON: one unit per leaf, ``anchor_kind="pointer"``, ``anchor_value`` = the JSON Pointer,
  text = the string form of the leaf value.
- PDF: one unit per page, ``anchor_kind="page"``, ``anchor_value`` = the one-based page number.

This package owns no filesystem traversal, authority, or digesting; those belong to the governed
acquisition port. See docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from __future__ import annotations

from ace_local_csv_source import CsvDocument, parse_csv
from ace_local_json_source import JsonDocument, parse_json
from ace_local_markdown_source import MarkdownDocument, parse_markdown
from ace_local_pdf_source import PdfDocument, parse_pdf

from ace.intelligence.local_source_mapping import SourceUnit


def _row_text(cells: tuple[tuple[str, str], ...]) -> str:
    """Render a CSV row's cells as a readable ``key: value | key: value`` line."""
    return " | ".join(f"{key}: {value}" for key, value in cells)


def normalize_markdown(document: MarkdownDocument) -> tuple[SourceUnit, ...]:
    """Convert a parsed Markdown document into one source unit per section."""
    units: list[SourceUnit] = []
    for section in document.sections:
        if section.heading_path:
            units.append(
                SourceUnit(
                    anchor_kind="heading",
                    anchor_value=section.anchor,
                    text=section.text,
                )
            )
        else:
            # A preamble section has no heading path; its anchor is the empty whole-file anchor.
            units.append(
                SourceUnit(
                    anchor_kind="none",
                    anchor_value=section.anchor,
                    text=section.text,
                )
            )
    return tuple(units)


def normalize_csv(document: CsvDocument) -> tuple[SourceUnit, ...]:
    """Convert a parsed CSV document into one source unit per data row."""
    return tuple(
        SourceUnit(
            anchor_kind="row",
            anchor_value=str(row.index),
            text=_row_text(row.cells),
        )
        for row in document.rows
    )


def normalize_json(document: JsonDocument) -> tuple[SourceUnit, ...]:
    """Convert a parsed JSON document into one source unit per leaf value."""
    return tuple(
        SourceUnit(
            anchor_kind="pointer",
            anchor_value=leaf.pointer,
            text=str(leaf.value),
        )
        for leaf in document.leaves
    )


def normalize_pdf(document: PdfDocument) -> tuple[SourceUnit, ...]:
    """Convert a parsed PDF document into one source unit per page."""
    return tuple(
        SourceUnit(
            anchor_kind="page",
            anchor_value=str(page.page),
            text=page.text,
        )
        for page in document.pages
    )


def source_units_for(extension: str, content: bytes) -> tuple[SourceUnit, ...] | None:
    """Parse and normalize bytes for a supported extension, else ``None``.

    Routes ``md`` → Markdown, ``csv`` → CSV, ``json`` → JSON, ``pdf`` → PDF. Any other extension
    returns ``None`` — the unsupported-inventory signal PI3's acquisition port expects. The
    extension is matched case-insensitively with any leading dot stripped.
    """
    ext = extension.lower().lstrip(".")
    if ext == "md":
        return normalize_markdown(parse_markdown(content))
    if ext == "csv":
        return normalize_csv(parse_csv(content))
    if ext == "json":
        return normalize_json(parse_json(content))
    if ext == "pdf":
        return normalize_pdf(parse_pdf(content))
    return None
