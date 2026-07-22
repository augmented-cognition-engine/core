#!/usr/bin/env python3
"""Apply versioned SurrealDB .surql files in order."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from surrealdb import AsyncSurreal

# Allow running as script without installing package
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.engine.core.config import settings
from core.engine.core.migration_compat import (
    STRICT_FROM_VERSION,
    is_known_legacy_compatibility_error,
)

SCHEMA_DIR = Path(__file__).parent.parent / "core" / "schema"

_REQUIRED_TABLES = {
    "config_entry",
    "decision",
    "discipline",
    "insight",
    "observation",
    "product",
    "reasoning_event",
    "specialty",
    "task",
    "workspace",
}


def _strip_sql_comments(sql: str) -> str:
    """Strip -- comments from SQL (both whole-line and inline).

    Processes line-by-line. Each line is truncated at the first '--' token,
    avoiding false splits when a semicolon appears inside a comment.
    """
    cleaned: list[str] = []
    for line in sql.splitlines():
        # Strip inline -- comment, keeping the part before it
        idx = line.find("--")
        cleaned.append(line[:idx].rstrip() if idx != -1 else line)
    return "\n".join(cleaned)


def _split_statements(sql: str) -> list[str]:
    """Split SQL on ';' at brace-depth 0 (respects FOR {...} blocks).

    Pre-processes to strip -- comments so semicolons inside comments
    never cause false splits (e.g. 'may be no-op; handled live').
    """
    sql = _strip_sql_comments(sql)
    stmts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in sql:
        if char == "{":
            depth += 1
            current.append(char)
        elif char == "}":
            depth -= 1
            current.append(char)
        elif char == ";" and depth == 0:
            stmt = "".join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
        else:
            current.append(char)
    # Trailing content without a final semicolon
    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)
    return stmts


async def get_current_version(db: AsyncSurreal) -> int:
    try:
        result = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
        if not result:
            return 0
        rows = result[0] if isinstance(result[0], list) else result
        return int(rows[0].get("value", "0")) if rows else 0
    except Exception:
        return 0


# Backward-compatible import used by the persistence verifier and existing
# tests; the policy itself has one owner in core.engine.core.migration_compat.
_is_known_legacy_compatibility_error = is_known_legacy_compatibility_error


async def apply_file(db: AsyncSurreal, version: int, name: str, sql: str) -> list[str]:
    """Execute a migration file's statements one by one; return compatibility events.

    SurrealDB reports many statement failures as error *strings* rather than
    raising, so the result of every query is checked. Unknown failures always
    abort. Only audited legacy compatibility events are allowed to continue.
    """
    compatibility_events: list[str] = []
    for stmt in _split_statements(sql):
        head = " ".join(stmt.split()[:6])[:80]
        error: str | None = None
        try:
            result = await db.query(stmt)
            if isinstance(result, str):
                error = result
        except Exception as exc:
            error = str(exc)
        if error is not None:
            msg = f"{name}: [{head}] -> {error[:200]}"
            if version >= STRICT_FROM_VERSION or not _is_known_legacy_compatibility_error(version, error):
                raise RuntimeError(f"per-statement error (fail-closed): {msg}")
            compatibility_events.append(msg)
    return compatibility_events


async def validate_schema(db: AsyncSurreal, expected_version: int) -> None:
    """Fail unless the fresh/upgrade result exposes the minimum runtime schema."""
    current = await get_current_version(db)
    if current != expected_version:
        raise RuntimeError(f"schema validation failed: expected v{expected_version}, found v{current}")

    result = await db.query("INFO FOR DB")
    info = result[0] if isinstance(result, list) and result else result
    if isinstance(info, list):
        info = info[0] if info else {}
    tables = set((info or {}).get("tables", {})) if isinstance(info, dict) else set()
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise RuntimeError(f"schema validation failed: missing required tables: {', '.join(missing)}")


async def apply_schema() -> None:
    files = sorted(SCHEMA_DIR.glob("v*.surql"))
    if not files:
        print(f"No .surql files found in {SCHEMA_DIR}", file=sys.stderr)
        sys.exit(1)

    db = AsyncSurreal(settings.surreal_url)
    await db.connect()
    await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
    await db.use(settings.surreal_ns, settings.surreal_db)

    current = await get_current_version(db)
    print(f"Current schema version: {current}")

    applied = 0
    compatibility_events: list[str] = []
    expected_version = 0
    for f in files:
        match = re.search(r"v(\d+)", f.name)
        if not match:
            continue
        version = int(match.group(1))
        expected_version = max(expected_version, version)
        if version <= current:
            print(f"  skip {f.name} (already applied)")
            continue
        print(f"  apply {f.name}...")
        # Statements run one at a time: SurrealDB v3 cannot REMOVE + DEFINE a
        # table in the same query batch (the DEFINE sees the old table).
        compatibility_events.extend(await apply_file(db, version, f.name, f.read_text()))
        await db.query(
            "UPSERT config_entry SET key = 'schema_version', value = $v WHERE key = 'schema_version'",
            {"v": str(version)},
        )
        applied += 1

    await validate_schema(db, expected_version)
    print(
        f"\nDone — applied {applied} file(s); schema v{expected_version} validated"
        f" ({len(compatibility_events)} audited legacy compatibility events)."
    )


if __name__ == "__main__":
    asyncio.run(apply_schema())
