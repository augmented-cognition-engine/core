# ace-local-json-source

A thin JSON **source adapter** for ACE Personal Intelligence (ACE 1.2).

Pure translator: JSON bytes in, leaf values out, each anchored by its RFC 6901 JSON Pointer for
PI4's citation locator grammar.

```python
from ace_local_json_source import parse_json

doc = parse_json(open("data.json", "rb").read())
doc.leaves             # (JsonLeaf(pointer="/a/b", value=1, anchor="/a/b"), ...)
```

Objects and arrays flatten in document order; pointer tokens escape `~` as `~0` and `/` as `~1`.

## Boundary

No folder walking, file reading, access enforcement, digesting, or admission — that governed
plumbing belongs to the local-acquisition port, not the adapter. See
[the local source adapter architecture](../../docs/design/personal-intelligence-local-source-adapters-v1.md).
Stdlib-only, no dependency beyond `ace-core`.

## Development

```bash
uv run --no-project --with pytest python -m pytest adapters/local_json_source/tests
```
