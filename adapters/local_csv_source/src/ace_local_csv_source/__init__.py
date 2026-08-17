"""Thin CSV structural source adapter for ACE Personal Intelligence.

A pure translator: CSV bytes in, a header tuple and row records out, each row anchored by its
one-based data-row number for PI4's citation locator grammar. It performs no filesystem
traversal, authority evaluation, digesting, or admission. See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from ace_local_csv_source.adapter import CsvDocument, CsvRow, parse_csv

__all__ = ["CsvDocument", "CsvRow", "parse_csv"]
