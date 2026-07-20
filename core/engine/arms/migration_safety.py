"""Migration-safety mirror — a fast, in-process check for the Data arm's critic. Encodes the
data-slop bugs this session hit (v126 required-field-drops-rows, v125 enum-narrowing) + the
SurrealDB v3 <record>$-in-RELATE trap + version-number correctness.

NOT an idempotency check: the schema applier is version-gated (apply_pending runs each migration
once per DB; test_schema_idempotency re-runs apply which no-ops when up-to-date), so bare DEFINE
is the codebase norm (~1900 of them). Flagging bare DEFINE would flag nearly every real migration.

Parses by STATEMENT (split on ';'), not by line — so multi-line `DEFINE FIELD ... \\n DEFAULT/ASSERT`
and `FLEXIBLE TYPE` fields (both common idioms in the real schema) are handled correctly."""

from __future__ import annotations

import os
import re

# Field head: name, table, and the first TYPE token. Allows OVERWRITE/IF NOT EXISTS before the name
# and FLEXIBLE/READONLY modifiers before TYPE (otherwise those fields would be invisible to the rules).
_FIELD_HEAD = re.compile(
    r"DEFINE\s+FIELD\s+(?:OVERWRITE\s+|IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\s+ON\s+(?:TABLE\s+)?"
    r"([A-Za-z0-9_]+)\s+(?:(?:FLEXIBLE|READONLY)\s+)*TYPE\s+(\S+)",
    re.IGNORECASE,
)
_TABLE_HEAD = re.compile(r"DEFINE\s+TABLE\s+(?:OVERWRITE\s+|IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)", re.IGNORECASE)
_ASSERT_INSIDE = re.compile(r"ASSERT\s+\$value\s+(?:INSIDE|IN)\s*\[([^\]]*)\]", re.IGNORECASE)
_RELATE = re.compile(r"\bRELATE\b", re.IGNORECASE)
_RECORD_CAST = re.compile(r"<record>\s*\$")
_VERSION = re.compile(r"v(\d+)")


def _statements(sql: str) -> list[str]:
    """Split DDL into statements by ';' (sufficient for migration files). Each statement is the
    full multi-line text, so DEFAULT/ASSERT on a line after TYPE are in scope."""
    return [s.strip() for s in (sql or "").split(";") if s.strip()]


def _enum_values(text: str) -> set[str]:
    return {v.strip().strip("'\"") for v in text.split(",") if v.strip()}


def _field_defs(sql: str):
    """Yield (field, table, type_token, statement_text) for each DEFINE FIELD — full-statement scope."""
    for stmt in _statements(sql):
        m = _FIELD_HEAD.search(stmt)
        if m:
            yield m.group(1), m.group(2), m.group(3).strip(), stmt


def _table_defs(sql: str) -> set[str]:
    out: set[str] = set()
    for stmt in _statements(sql):
        m = _TABLE_HEAD.search(stmt)
        if m:
            out.add(m.group(1))
    return out


def parse_schema_dir(schema_dir: str):
    """Parse existing .surql files → (max_version:int, tables:set[str], enums:dict[(t,f)->set])."""
    max_version = 0
    tables: set[str] = set()
    enums: dict = {}
    if not os.path.isdir(schema_dir):
        return max_version, tables, enums
    for fn in sorted(os.listdir(schema_dir)):
        if not fn.endswith(".surql"):
            continue
        m = _VERSION.search(fn)
        if m:
            max_version = max(max_version, int(m.group(1)))
        try:
            with open(os.path.join(schema_dir, fn), encoding="utf-8") as fh:
                sql = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        tables |= _table_defs(sql)
        for field, table, _type, stmt in _field_defs(sql):
            am = _ASSERT_INSIDE.search(stmt)
            if am:
                enums[(table, field)] = _enum_values(am.group(1))
    return max_version, tables, enums


def scan_migration_violations(
    sql: str, *, existing_max_version: int, filename: str, prior_tables=None, prior_enums=None
) -> list[str]:
    """Return human-readable migration-safety violations. Empty == safe additive migration."""
    prior_tables = prior_tables or set()
    prior_enums = prior_enums or {}
    violations: list[str] = []

    new_tables = _table_defs(sql)  # tables created here are exempt — no existing rows to break

    # 1. version correctness
    m = _VERSION.search(filename or "")
    if m is None:
        violations.append(f"filename '{filename}' has no version (expected v{existing_max_version + 1}_*.surql)")
    elif int(m.group(1)) != existing_max_version + 1:
        violations.append(f"version v{int(m.group(1))} is not the next version (expected v{existing_max_version + 1})")

    for field, table, ftype, stmt in _field_defs(sql):
        low = stmt.lower()
        # 2. required field, no default, on an EXISTING table (v126 silent-drop)
        if (
            table in prior_tables
            and table not in new_tables
            and not ftype.lower().startswith("option<")
            and "default" not in low
        ):
            violations.append(
                f"DEFINE FIELD {field} ON {table} is required (TYPE {ftype}) with no DEFAULT on an "
                f"existing table — breaks existing rows/CREATEs (v126 bug); use option<...>, a DEFAULT, or a backfill"
            )
        # 3. enum narrowing (v125) — ASSERT scoped to the full statement (no fixed window)
        am = _ASSERT_INSIDE.search(stmt)
        if am and (table, field) in prior_enums:
            dropped = prior_enums[(table, field)] - _enum_values(am.group(1))
            if dropped:
                violations.append(
                    f"DEFINE FIELD {field} ON {table} ASSERT drops prior enum value(s) {sorted(dropped)} "
                    f"— existing rows with those values become invalid (v125 bug)"
                )

    # 4. <record>$ inside a RELATE
    for stmt in _statements(sql):
        if _RELATE.search(stmt) and _RECORD_CAST.search(stmt):
            violations.append("<record>$ inside a RELATE — SurrealDB v3 trap; bind parse_record_id instead")

    return violations
