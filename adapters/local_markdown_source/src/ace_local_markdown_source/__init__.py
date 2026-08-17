"""Thin Markdown/Obsidian structural source adapter for ACE Personal Intelligence.

This package is a pure translator: it turns Markdown bytes into a structured document
(frontmatter, sections keyed by heading path, and Obsidian wikilinks). It performs no
filesystem traversal, authority evaluation, digesting, or admission — those are owned by
the governed local-acquisition port (PI3). See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from ace_local_markdown_source.adapter import (
    MarkdownDocument,
    MarkdownSection,
    parse_markdown,
)

__all__ = ["MarkdownDocument", "MarkdownSection", "parse_markdown"]
