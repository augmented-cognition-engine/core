# ace-local-source-normalizers

Host-side **format normalizers** for ACE Personal Intelligence (ACE 1.2, PI4). This is the seam
that composes the local-source pipeline end-to-end: it turns each thin adapter's native output
into the format-agnostic `SourceUnit` shape that ace-core's mapping contract maps into citable
observations.

```python
from ace_local_source_normalizers import source_units_for
from ace.intelligence.local_source_mapping import map_document_units

units = source_units_for("md", open("note.md", "rb").read())   # -> tuple[SourceUnit, ...] | None
observations = map_document_units("notes/note.md", digest, units)
```

`source_units_for(extension, content)` routes by extension and returns `None` for any unsupported
format — the unsupported-inventory signal the governed acquisition port (PI3) expects.

## Mapping rules

Every `SourceUnit`'s `(anchor_kind, anchor_value)` is chosen so it round-trips through the citation
locator grammar (`format_locator` / `parse_locator`) for its format.

| Format | Unit granularity | `anchor_kind` | `anchor_value` | `text` |
|--------|------------------|---------------|----------------|--------|
| Markdown | one per section | `heading` (`none` for a preamble) | the `" > "` heading-path string (`""` for a preamble) | section text |
| CSV | one per data row | `row` | one-based row index | `key: value \| key: value` join of the row's cells |
| JSON | one per leaf | `pointer` | the RFC 6901 JSON Pointer | `str(value)` of the leaf |
| PDF | one per page | `page` | one-based page number | page text |

Empty-text units are dropped downstream by `map_document_units`, so a citation always points at
citable content.

## Boundary

This package owns no filesystem traversal, authority evaluation, or digesting — those belong to the
governed local-acquisition port in ace-core. It only composes the adapters with the mapping
contract. See
[the local source adapter architecture](../../docs/design/personal-intelligence-local-source-adapters-v1.md).

## Development

The package depends on ace-core plus the four sibling adapter packages. `pyproject.toml` wires all
of them onto `pythonpath` for pytest, so no install is needed:

```bash
uv run --no-project --with pytest --with pypdf python -m pytest tests
```
