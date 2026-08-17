# ace-local-markdown-source

A thin Markdown/Obsidian **source adapter** for ACE Personal Intelligence (ACE 1.2).

This package is a pure translator. Given Markdown bytes it returns a structured document —
parsed frontmatter, sections keyed by their heading path (so a citation can anchor to an exact
heading), and deduplicated Obsidian wikilinks:

```python
from ace_local_markdown_source import parse_markdown

doc = parse_markdown(open("note.md", "rb").read())
doc.frontmatter        # {"title": "My Note", ...}
doc.sections           # (MarkdownSection(heading_path=("H1", "H2"), text=..., anchor="H1 > H2"), ...)
doc.wikilinks          # ("Linked Note", ...)
```

## Boundary

By design this adapter does **not** walk folders, read files, enforce access scope, compute
content digests, or admit anything. That security-sensitive plumbing is the governed
local-acquisition port's responsibility, not the adapter's. See
[the local source adapter architecture](../../docs/design/personal-intelligence-local-source-adapters-v1.md).

The adapter is independently versioned and adds no dependency beyond `ace-core`. It is one of the
four planned local-source adapters (Markdown/Obsidian, PDF, CSV, JSON); only the PDF adapter will
pull a parser dependency.

## Development

```bash
uv run --no-project --with pytest python -m pytest adapters/local_markdown_source/tests
```
