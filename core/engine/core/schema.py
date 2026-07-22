# engine/core/schema.py
"""Schema migration — auto-apply pending .surql files on startup.

Reads `config_entry WHERE key = 'schema_version'` to determine the
current DB version, then applies all `schema/vNNN_*.surql` files with
version > current in order. Each file updates the version counter after
successful application.

Called from app lifespan so the DB is always current when the server starts.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from core.engine.core.db import pool
from core.engine.core.migration_compat import is_known_legacy_compatibility_error

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).parent.parent.parent / "schema"

# Latest version we expect in the codebase (set by highest v*.surql file).
# Computed lazily on first call to apply_pending().
_CODE_VERSION: int | None = None


def _split_statements(sql: str) -> list[str]:
    """Split SQL on ';' at brace-depth 0 (respects FOR {...} blocks).

    A ';' inside a `--` line comment is NOT a statement boundary — without
    this guard, prose like `-- TTL 7d; training negatives` produces a malformed
    second statement that SurrealDB rejects with a parse error. Block comments
    `/* ... */` are also tracked.
    """
    stmts: list[str] = []
    current: list[str] = []
    depth = 0
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(sql)
    while i < n:
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            current.append(char)
            if char == "*" and nxt == "/":
                current.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if char == "-" and nxt == "-":
            in_line_comment = True
            current.append(char)
            i += 1
            continue
        if char == "/" and nxt == "*":
            in_block_comment = True
            current.append(char)
            i += 1
            continue
        if char == "{":
            depth += 1
            current.append(char)
        elif char == "}":
            depth -= 1
            current.append(char)
        elif char == ";" and depth == 0:
            stmt = "".join(current).strip()
            lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
            stmt = "\n".join(lines).strip()
            if stmt:
                stmts.append(stmt)
            current = []
        else:
            current.append(char)
        i += 1
    stmt = "".join(current).strip()
    lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
    stmt = "\n".join(lines).strip()
    if stmt:
        stmts.append(stmt)
    return stmts


def _get_code_version() -> int:
    """Highest version number found in schema/*.surql files."""
    global _CODE_VERSION
    if _CODE_VERSION is not None:
        return _CODE_VERSION
    highest = 0
    for f in SCHEMA_DIR.glob("v*.surql"):
        m = re.search(r"v(\d+)", f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    _CODE_VERSION = highest
    return highest


async def get_db_version() -> int:
    """Read current schema version from DB."""
    try:
        async with pool.connection() as db:
            result = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
            if not result:
                return 0
            rows = result[0] if isinstance(result[0], list) else result
            return int(rows[0].get("value", "0")) if rows else 0
    except Exception:
        return 0


def _stmt_error(raw: object) -> str | None:
    """Extract an error message from a ``query_raw`` response, if present."""
    if not isinstance(raw, dict):
        return None
    err = raw.get("error")
    if err:
        return str(err.get("message", err) if isinstance(err, dict) else err)
    for entry in raw.get("result", []) or []:
        if isinstance(entry, dict) and entry.get("status") == "ERR":
            return str(entry.get("result"))
    return None


def _assert_no_stmt_error(raw: object, *, source: str) -> None:
    """Raise RuntimeError if a query_raw response carries any error.

    query_raw returns either {'error': {...}} (parse/auth) or
    {'result': [{'status': 'OK'|'ERR', 'result': ...}, ...]}. The surrealdb
    client's db.query() raises only on the top-level 'error' shape and SILENTLY
    discards per-statement 'ERR' entries — which is how a failed migration
    statement (e.g. a non-OVERWRITE DEFINE FIELD that errors 'already exists')
    went unnoticed and masked the v113 SCHEMAFULL bug. The migration runner must
    fail loud on either shape.
    """
    if error := _stmt_error(raw):
        raise RuntimeError(f"migration statement failed [{source}]: {error}")


def _check_stmt_result(raw: object, *, version: int, source: str) -> str | None:
    """Return an audited legacy event or fail closed on a statement error."""
    error = _stmt_error(raw)
    if error is None:
        return None
    if is_known_legacy_compatibility_error(version, error):
        return f"{source}: {error}"
    _assert_no_stmt_error(raw, source=source)
    raise AssertionError("unreachable")


async def apply_pending() -> int:
    """Apply all pending schema migrations. Returns count of files applied."""
    current = await get_db_version()
    code_ver = _get_code_version()

    if current >= code_ver:
        logger.info("Schema up to date (v%d)", current)
        return 0

    logger.info("Schema v%d → v%d: applying pending migrations...", current, code_ver)

    files = sorted(SCHEMA_DIR.glob("v*.surql"))
    applied = 0
    compatibility_events = 0

    async with pool.connection() as db:
        for f in files:
            m = re.search(r"v(\d+)", f.name)
            if not m:
                continue
            version = int(m.group(1))
            if version <= current:
                continue

            logger.info("  applying %s...", f.name)
            sql = f.read_text()
            stmts = _split_statements(sql)
            for stmt in stmts:
                raw = await db.query_raw(stmt)
                source = f"{f.name}: {stmt.strip()[:80]}"
                if event := _check_stmt_result(raw, version=version, source=source):
                    compatibility_events += 1
                    logger.warning("Audited legacy migration compatibility event: %s", event)

            raw = await db.query_raw(
                "UPSERT config_entry SET key = 'schema_version', value = $v WHERE key = 'schema_version'",
                {"v": str(version)},
            )
            _assert_no_stmt_error(raw, source=f"{f.name}: schema_version bump")
            applied += 1

    logger.info(
        "Schema migration complete — applied %d file(s), now at v%d (%d audited legacy compatibility events)",
        applied,
        code_ver,
        compatibility_events,
    )
    return applied
