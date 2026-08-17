"""Thin PDF structural source adapter for ACE Personal Intelligence.

A pure translator: PDF bytes in, per-page text out, each page anchored by its one-based page
number for PI4's citation locator grammar. It performs no filesystem traversal, authority
evaluation, digesting, or admission. This is the one local adapter that carries a parser
dependency (pypdf); the others are stdlib-only. See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from ace_local_pdf_source.adapter import PdfDocument, PdfPage, parse_pdf

__all__ = ["PdfDocument", "PdfPage", "parse_pdf"]
