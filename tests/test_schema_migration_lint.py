# tests/test_schema_migration_lint.py
"""Migration lint + capture-front-door coverage, from a file-level replay.

Two enforcement rules born from the 2026-07-15 drift audit
(docs/schema-drift-audit-2026-07-15.md):

1. OVERWRITE lint — on this SurrealDB build a plain `DEFINE FIELD` for a field
   that already exists errors "already exists" and silently no-ops under the
   legacy runner. ~90 historical statements did this (v029's entire purpose
   no-oped). From v142 on, redefinitions must use `DEFINE FIELD OVERWRITE`
   (or remove the field first). History is grandfathered; new files are not.

2. Front-door coverage — every field that ends REQUIRED (non-option, no
   DEFAULT) after replaying all migration files must be SET by the write path
   that feeds the table. This is the v034/observation.workspace and
   v032/agent_feedback.org class: a required field the writer never sets means
   every write fails on a fresh install, silently. The check parses BOTH sides
   from source (schema files x CREATE statements), so it goes red the day a
   migration and a writer disagree — including inside the export's stranger
   clean room, which runs this suite.

The simulator mirrors the swallowed-error semantics the runner had for legacy
files: plain DEFINE FIELD on an existing field is a NO-OP (recorded as a
violation), REMOVE TABLE clears all its fields, IF NOT EXISTS applies only
when absent, OVERWRITE always applies.
"""

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
SCHEMA_DIR = REPO / "core" / "schema"

_SPEC = importlib.util.spec_from_file_location("schema_apply", REPO / "scripts" / "schema_apply.py")
_schema_apply = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_schema_apply)
_split_statements = _schema_apply._split_statements

OVERWRITE_LINT_FROM_VERSION = 142

_REMOVE_TABLE = re.compile(r"^REMOVE TABLE (?:IF EXISTS )?(\w+)", re.IGNORECASE)
_DEFINE_TABLE = re.compile(r"^DEFINE TABLE (?:OVERWRITE |IF NOT EXISTS )?(\w+)", re.IGNORECASE)
_REMOVE_FIELD = re.compile(r"^REMOVE FIELD (?:IF EXISTS )?([\w.*]+) ON (?:TABLE )?(\w+)", re.IGNORECASE)
_DEFINE_FIELD = re.compile(
    r"^DEFINE FIELD (OVERWRITE |IF NOT EXISTS )?([\w.*]+) ON (?:TABLE )?(\w+)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TYPE_OF = re.compile(r"\bTYPE\s+(.+?)(?:\s+DEFAULT\s|\s+ASSERT\s|\s+PERMISSIONS\s|\s+VALUE\s|$)", re.IGNORECASE)


def replay(files):
    """Replay [(version, name, text)] -> (fields, violations).

    fields: {table: {field: definition-remainder}} — final state.
    violations: plain DEFINE FIELD on an already-defined field (a silent no-op
    under the legacy runner), as dicts with version/name/table/field.
    """
    fields: dict[str, dict[str, str]] = {}
    violations: list[dict] = []
    for version, name, text in sorted(files):
        for stmt in _split_statements(text):
            s = " ".join(stmt.split())
            if m := _REMOVE_TABLE.match(s):
                fields.pop(m.group(1), None)
            elif m := _DEFINE_TABLE.match(s):
                fields.setdefault(m.group(1), {})
            elif m := _REMOVE_FIELD.match(s):
                fields.get(m.group(2), {}).pop(m.group(1), None)
            elif m := _DEFINE_FIELD.match(s):
                modifier, field, table, rest = m.groups()
                table_fields = fields.setdefault(table, {})
                exists = field in table_fields
                if modifier is None and exists:
                    violations.append({"version": version, "name": name, "table": table, "field": field})
                    continue  # SurrealDB: "already exists" — silent no-op
                if modifier and modifier.strip().upper() == "IF NOT EXISTS" and exists:
                    continue
                table_fields[field] = rest
    return fields, violations


def load_schema_files(max_version: int | None = None):
    out = []
    for path in sorted(SCHEMA_DIR.glob("v*.surql")):
        version = int(re.search(r"v(\d+)", path.name).group(1))
        if max_version is not None and version >= max_version:
            continue
        out.append((version, path.name, path.read_text()))
    return out


def required_fields(fields: dict[str, dict[str, str]], table: str) -> set[str]:
    """Top-level fields whose final definition is non-option with no DEFAULT."""
    out = set()
    for field, rest in fields.get(table, {}).items():
        if "." in field or "*" in field:
            continue  # nested defs only validate inside a present parent
        m = _TYPE_OF.search(rest)
        if not m:
            continue
        ftype = m.group(1).strip()
        if not ftype.lower().startswith("option<") and not re.search(r"\bDEFAULT\b", rest, re.IGNORECASE):
            out.add(field)
    return out


def fields_written_by(source: Path, table: str) -> set[str]:
    """Field names assigned in the writer's `CREATE <table> SET ...` statement."""
    text = source.read_text()
    m = re.search(rf"CREATE {table} SET(.*?)\"\"\"", text, re.DOTALL)
    assert m, f"no `CREATE {table} SET` statement found in {source}"
    return set(re.findall(r"(\w+)\s*=", m.group(1)))


# The capture front doors: (table, writer module that CREATEs it).
FRONT_DOORS = [
    ("observation", REPO / "core" / "engine" / "worker" / "app.py"),
    ("agent_feedback", REPO / "core" / "engine" / "product" / "feedback_handler.py"),
]


# ── simulator semantics (synthetic) ──────────────────────────────────────────


def test_plain_redefine_is_violation_and_noop():
    fields, violations = replay(
        [
            (1, "v001.surql", "DEFINE FIELD x ON t TYPE option<string>;"),
            (2, "v002.surql", "DEFINE FIELD x ON t TYPE string;"),
        ]
    )
    assert [(v["version"], v["table"], v["field"]) for v in violations] == [(2, "t", "x")]
    assert fields["t"]["x"].lower().startswith("type option<string>"), "plain redefine must NOT take effect"


def test_overwrite_applies_without_violation():
    fields, violations = replay(
        [
            (1, "v001.surql", "DEFINE FIELD x ON t TYPE option<string>;"),
            (2, "v002.surql", "DEFINE FIELD OVERWRITE x ON t TYPE string;"),
        ]
    )
    assert violations == []
    assert fields["t"]["x"].lower().startswith("type string")


def test_remove_table_resets_fields():
    fields, violations = replay(
        [
            (1, "v001.surql", "DEFINE FIELD x ON t TYPE string;"),
            (
                2,
                "v002.surql",
                "REMOVE TABLE IF EXISTS t; DEFINE TABLE t SCHEMALESS; DEFINE FIELD x ON t TYPE option<int>;",
            ),
        ]
    )
    assert violations == [], "redefine after table rebuild is legitimate"
    assert fields["t"]["x"].lower().startswith("type option<int>")


def test_required_fields_respects_option_and_default():
    fields, _ = replay(
        [
            (
                1,
                "v001.surql",
                "DEFINE FIELD a ON t TYPE string; "
                "DEFINE FIELD b ON t TYPE option<string>; "
                "DEFINE FIELD c ON t TYPE int DEFAULT 0; "
                "DEFINE FIELD d.* ON t TYPE string;",
            )
        ]
    )
    assert required_fields(fields, "t") == {"a"}


# ── self-proof on real history: the detector catches the original bug ───────


def test_detector_catches_the_v034_workspace_bug_in_history():
    """Replaying only files < v140 must flag observation.workspace as
    required-but-unwritten — proof this check would have caught the original
    export breakage, not just today's fixed state."""
    fields, _ = replay(load_schema_files(max_version=140))
    required = required_fields(fields, "observation")
    written = fields_written_by(REPO / "core" / "engine" / "worker" / "app.py", "observation")
    assert "workspace" in required - written


# ── enforcement on the real, current files ───────────────────────────────────


def test_no_plain_redefine_from_v142_on():
    _, violations = replay(load_schema_files())
    modern = [v for v in violations if v["version"] >= OVERWRITE_LINT_FROM_VERSION]
    assert modern == [], (
        "Plain DEFINE FIELD on an existing field silently no-ops "
        f"(SurrealDB 'already exists'). Use DEFINE FIELD OVERWRITE: {modern}"
    )


def test_capture_front_doors_write_every_required_field():
    fields, _ = replay(load_schema_files())
    for table, writer in FRONT_DOORS:
        missing = required_fields(fields, table) - fields_written_by(writer, table)
        assert not missing, (
            f"{table}: required after fresh replay but never set by {writer.name}: {sorted(missing)} — "
            f"every CREATE {table} on a fresh install will fail (v034/v032 class). "
            f"Widen/remove the field via migration or set it in the writer."
        )
