"""Pure CSV structural parser.

`parse_csv` turns CSV bytes into a header tuple and a tuple of row records. Each data row is
anchored by its one-based row number so a citation can resolve to an exact row. Cells beyond the
header get positional `column_N` keys; short rows are padded with empty strings. The parser reads
no files and makes no acquisition or freshness claim.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CsvRow:
    """One data row, anchored by its one-based row number."""

    index: int
    cells: tuple[tuple[str, str], ...]
    anchor: str


@dataclass(frozen=True, slots=True)
class CsvDocument:
    """The structured translation of one CSV source."""

    headers: tuple[str, ...]
    rows: tuple[CsvRow, ...]


def _cells(headers: tuple[str, ...], values: list[str]) -> tuple[tuple[str, str], ...]:
    width = max(len(headers), len(values))
    pairs: list[tuple[str, str]] = []
    for i in range(width):
        key = headers[i] if i < len(headers) else f"column_{i + 1}"
        value = values[i] if i < len(values) else ""
        pairs.append((key, value))
    return tuple(pairs)


def parse_csv(content: bytes) -> CsvDocument:
    """Parse CSV bytes into a structured document."""
    text = content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    records = [row for row in reader if row]
    if not records:
        return CsvDocument(headers=(), rows=())

    headers = tuple(records[0])
    rows = tuple(
        CsvRow(index=i, cells=_cells(headers, values), anchor=f"row {i}")
        for i, values in enumerate(records[1:], start=1)
    )
    return CsvDocument(headers=headers, rows=rows)
