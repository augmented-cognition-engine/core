# tests/test_schema_observation_workspace.py
"""Regression lock: dead-concept fields must never end up required on replay.

v034 rebuilt the observation table and redefined workspace as a REQUIRED
record<workspace> (v002 had option<>). v061 retired the workspace concept but
only removed the field from initiative/recurring_initiative — observation kept
the required definition. On any database built by replaying core/schema/*.surql
in order (every fresh install and the open kernel export), EVERY
`CREATE observation` then fails SurrealDB field validation — silently, because
the per-statement error is returned as a string and /observe used to report
"queued" anyway.

The 2026-07-15 drift audit found the same class on agent_feedback.org: the
v058/v061 org→product retirement never touched agent_feedback, so fresh
replays require org TYPE record<org> while feedback_handler.py writes product.

Long-lived internal DBs never noticed either one: the live definitions were
hand-patched and drifted from these files. These tests replay the *files* —
the only truth a fresh install has — and assert each dead-concept field ends
absent or optional.
"""

import re
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).parent.parent / "core" / "schema"

# (table, field) pairs for retired concepts (workspace: v061, org: v058/v061)
# that at some point were defined as required on a still-written table.
DEAD_CONCEPT_FIELDS = [
    ("observation", "workspace"),
    ("agent_feedback", "org"),
]


def _final_field_type(table: str, field: str) -> str | None:
    """Replay migrations in apply order; return the field's final declared type, or None if absent."""
    define_re = re.compile(
        rf"DEFINE\s+FIELD\s+(?:OVERWRITE\s+|IF\s+NOT\s+EXISTS\s+)?{field}\s+ON\s+(?:TABLE\s+)?{table}\s+TYPE\s+([^;]+);",
        re.IGNORECASE,
    )
    remove_field_re = re.compile(
        rf"REMOVE\s+FIELD\s+(?:IF\s+EXISTS\s+)?{field}\s+ON\s+(?:TABLE\s+)?{table}\b",
        re.IGNORECASE,
    )
    remove_table_re = re.compile(
        rf"REMOVE\s+TABLE\s+(?:IF\s+EXISTS\s+)?{table}\b",
        re.IGNORECASE,
    )

    final: str | None = None
    for path in sorted(SCHEMA_DIR.glob("v*.surql")):
        text = path.read_text()
        # Process statements in file order so intra-file sequencing is honoured.
        events: list[tuple[int, str, str | None]] = []
        for m in remove_table_re.finditer(text):
            events.append((m.start(), "absent", None))
        for m in remove_field_re.finditer(text):
            events.append((m.start(), "absent", None))
        for m in define_re.finditer(text):
            events.append((m.start(), "define", m.group(1).strip()))
        for _, kind, typ in sorted(events):
            final = typ if kind == "define" else None
    return final


@pytest.mark.parametrize(("table", "field"), DEAD_CONCEPT_FIELDS)
def test_dead_concept_field_not_required_after_full_replay(table: str, field: str):
    final = _final_field_type(table, field)
    assert final is None or final.lower().startswith("option<"), (
        f"Replaying core/schema/*.surql leaves {table}.{field} as required "
        f"({final!r}) — every CREATE {table} on a fresh install will fail, and the "
        f"failure is swallowed (per-statement ERR string; see v113/v140/v141 headers). "
        f"Ship a migration that removes the field (v061 pattern) or widens it to option<>."
    )
