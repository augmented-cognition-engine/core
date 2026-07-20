"""Extract API call shapes from TypeScript/React source files.

Parses `api.get<Type>("/path")` patterns to build SeamExpectation objects
that describe what the frontend expects from each backend route.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.engine.seam.types import FieldShape, SeamExpectation

# Matches: api.get<TypeOrInline>("path") / api.post<...>('path') / api.del<...>(`path`)
_API_CALL_RE = re.compile(
    r"""api\.(get|post|put|patch|del)\s*<\s*([^>]+?)\s*>\s*\(\s*(?:["'`])([^"'`]+?)(?:["'`])""",
    re.DOTALL,
)

# Maps JS method names to HTTP verbs
_METHOD_MAP = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "del": "DELETE",
}


def extract_interface_fields(type_name: str, source: str) -> list[FieldShape]:
    """Find an exported interface by name and extract its top-level fields.

    Handles nested object types by counting braces rather than regex matching.
    """
    # Find the interface header
    header_re = re.compile(rf"(?:export\s+)?interface\s+{re.escape(type_name)}\s*\{{", re.MULTILINE)
    m = header_re.search(source)
    if not m:
        return []

    # Walk forward counting braces to find the matching closing brace
    start = m.end() - 1  # position of opening '{'
    depth = 0
    body_start = start + 1
    body_end = body_start
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                body_end = i
                break

    body = source[body_start:body_end]

    # Extract only top-level fields (depth 0 within the body)
    fields: list[FieldShape] = []
    seen: set[str] = set()
    lines = body.split("\n")
    nested_depth = 0
    for line in lines:
        opens = line.count("{")
        closes = line.count("}")
        # A line at depth-0 that opens a nested block belongs to a top-level field
        # whose type is an inline object (e.g. `address: {`).  Capture it before
        # raising the depth counter.
        if nested_depth == 0:
            stripped = line.strip().rstrip(";").rstrip(",")
            if stripped and not stripped.startswith("//"):
                field_m = re.match(r"^(\w+)\s*[?]?\s*:\s*(.+)", stripped)
                if field_m:
                    name = field_m.group(1)
                    type_hint = field_m.group(2).strip().rstrip("{").strip()
                    if name not in seen:
                        seen.add(name)
                        fields.append(FieldShape(name=name, type_hint=type_hint, source="interface"))
        # Only count braces on non-comment lines — comment braces don't affect structure
        stripped_for_depth = line.strip()
        if not stripped_for_depth.startswith("//"):
            nested_depth += opens - closes
        if nested_depth < 0:
            nested_depth = 0
    return fields


def _extract_inline_fields(type_text: str) -> list[FieldShape]:
    """Extract fields from an inline type like `{ items: Item[]; count: number }`."""
    # Strip outer braces
    inner = type_text.strip()
    if inner.startswith("{"):
        inner = inner[1:]
    if inner.endswith("}"):
        inner = inner[:-1]

    fields: list[FieldShape] = []
    # Split by semicolons to handle single-line inline types
    for segment in inner.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        # Match: fieldName?: Type
        m = re.match(r"(\w+)\s*[?]?\s*:\s*(.+)", segment)
        if m:
            fields.append(
                FieldShape(
                    name=m.group(1),
                    type_hint=m.group(2).strip(),
                    source="inline",
                )
            )
    return fields


def _normalize_route(raw: str) -> str:
    """Normalize a route path: replace ${...} with {}, strip query strings, strip trailing slash."""
    # Replace template expressions like ${encodeURIComponent(id)} with {}
    route = re.sub(r"\$\{[^}]*\}", "{}", raw)
    # Strip query string
    route = route.split("?")[0]
    # Strip trailing slash (but keep root "/")
    if len(route) > 1 and route.endswith("/"):
        route = route.rstrip("/")
    return route


def _resolve_named_type(type_name: str, source_files: list[str], current_source: str) -> list[FieldShape]:
    """Resolve a named type by searching through source files and the current file."""
    # Try current file first
    fields = extract_interface_fields(type_name, current_source)
    if fields:
        return fields

    # Search through provided type source files
    for file_path in source_files:
        path = Path(file_path)
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fields = extract_interface_fields(type_name, text)
        if fields:
            return fields

    return []


def extract_frontend_expectations(file_path: str, type_source_files: list[str] | None = None) -> list[SeamExpectation]:
    """Extract all API call expectations from a TypeScript/React source file.

    Args:
        file_path: Path to the .ts/.tsx file to analyze.
        type_source_files: Additional files to search for interface definitions.

    Returns:
        List of SeamExpectation objects describing each API call found.
    """
    if type_source_files is None:
        type_source_files = []

    path = Path(file_path)
    if not path.is_file():
        return []

    try:
        source = path.read_text()
    except (OSError, UnicodeDecodeError):
        return []

    # Check for @/lib/api import
    if "@/lib/api" not in source:
        return []

    expectations: list[SeamExpectation] = []

    for match in _API_CALL_RE.finditer(source):
        js_method = match.group(1)
        type_text = match.group(2).strip()
        raw_route = match.group(3)

        http_method = _METHOD_MAP.get(js_method, js_method.upper())
        route = _normalize_route(raw_route)

        # Determine line number
        line_num = source[: match.start()].count("\n") + 1

        # Resolve fields based on type shape
        if type_text.startswith("{"):
            # Inline type
            fields = _extract_inline_fields(type_text)
            type_name = ""
        elif re.match(r"^\w+$", type_text):
            # Named type
            type_name = type_text
            fields = _resolve_named_type(type_name, type_source_files, source)
        else:
            # Complex generic or union — skip field extraction
            type_name = type_text
            fields = []

        expectations.append(
            SeamExpectation(
                route=route,
                method=http_method,
                consumer_file=file_path,
                consumer_line=line_num,
                type_name=type_name,
                expected_fields=fields,
            )
        )

    return expectations
