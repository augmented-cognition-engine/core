# ace-local-pdf-source

A thin PDF **source adapter** for ACE Personal Intelligence (ACE 1.2).

Pure translator: PDF bytes in, per-page text out, each page anchored by its one-based page number
for PI4's citation locator grammar.

```python
from ace_local_pdf_source import parse_pdf

doc = parse_pdf(open("report.pdf", "rb").read())
doc.page_count         # 12
doc.pages              # (PdfPage(page=1, text="...", anchor="page 1"), ...)
```

Empty pages are kept so page numbers stay exact.

## Dependency

This is the **one** local adapter that carries a parser dependency — `pypdf` — because PDF is not
a text format. The Markdown, CSV, and JSON adapters are stdlib-only; a user who connects only those
never pulls pypdf. Text extraction is pypdf's responsibility; this adapter owns page anchoring and
trimming. pypdf is reached through an injectable `reader_factory`, so the adapter's own logic is
testable without a binary fixture.

## Boundary

No folder walking, file reading, access enforcement, digesting, or admission — that governed
plumbing belongs to the local-acquisition port, not the adapter. See
[the local source adapter architecture](../../docs/design/personal-intelligence-local-source-adapters-v1.md).

## Development

```bash
uv run --no-project --with pytest python -m pytest adapters/local_pdf_source/tests
```
