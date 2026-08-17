# ace-local-csv-source

A thin CSV **source adapter** for ACE Personal Intelligence (ACE 1.2).

Pure translator: CSV bytes in, a header tuple and row records out, each row anchored by its
one-based data-row number for PI4's citation locator grammar.

```python
from ace_local_csv_source import parse_csv

doc = parse_csv(open("data.csv", "rb").read())
doc.headers            # ("name", "age")
doc.rows               # (CsvRow(index=1, cells=(("name", "Ada"), ("age", "36")), anchor="row 1"), ...)
```

Cells beyond the header get positional `column_N` keys; short rows pad with empty strings.

## Boundary

No folder walking, file reading, access enforcement, digesting, or admission — that governed
plumbing belongs to the local-acquisition port, not the adapter. See
[the local source adapter architecture](../../docs/design/personal-intelligence-local-source-adapters-v1.md).
Stdlib-only, no dependency beyond `ace-core`.

## Development

```bash
uv run --no-project --with pytest python -m pytest adapters/local_csv_source/tests
```
