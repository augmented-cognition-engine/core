# tests/test_schema_apply_fail_closed.py
"""The migration runner must fail closed on per-statement errors.

SurrealDB reports many statement failures as error *strings* (not raised
exceptions). scripts/schema_apply.py historically ignored query results
entirely, so failing migrations shipped silently — the 2026-07-15 drift audit
found 110 swallowed errors across a fresh replay (see
docs/schema-drift-audit-2026-07-15.md).

Legacy files carry 110 audited compatibility events that later migrations
compensate for, so the contract is:
- version >= STRICT_FROM_VERSION: any per-statement error (string or raised)
  aborts the run — fail closed.
- legacy versions: only version-and-category allowlisted compatibility events
  continue; every unknown string or raised error aborts.
"""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "schema_apply", Path(__file__).parent.parent / "scripts" / "schema_apply.py"
)
schema_apply = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(schema_apply)


class FakeDB:
    """Scripted db.query: each call pops the next behaviour."""

    def __init__(self, behaviours):
        self.behaviours = list(behaviours)
        self.executed = []

    async def query(self, stmt, *args):
        self.executed.append(stmt)
        b = self.behaviours.pop(0)
        if isinstance(b, Exception):
            raise b
        return b


STRICT = schema_apply.STRICT_FROM_VERSION


async def test_strict_version_error_string_raises():
    db = FakeDB(["The field 'x' already exists"])
    with pytest.raises(RuntimeError, match="fail-closed"):
        await schema_apply.apply_file(db, STRICT, "v999_test.surql", "DEFINE FIELD x ON t TYPE string;")


async def test_strict_version_exception_propagates():
    db = FakeDB([ValueError("coercion failed")])
    with pytest.raises((RuntimeError, ValueError)):
        await schema_apply.apply_file(db, STRICT, "v999_test.surql", "UPDATE t SET x = 1;")


async def test_audited_legacy_compatibility_event_continues():
    db = FakeDB(["The field 'x' already exists", []])
    events = await schema_apply.apply_file(
        db, 6, "v006_test.surql", "DEFINE FIELD x ON t TYPE string; DEFINE FIELD y ON t TYPE string;"
    )
    assert len(events) == 1 and "already exists" in events[0]
    assert len(db.executed) == 2, "later statements must run after an audited compatibility event"


async def test_unknown_legacy_exception_fails_closed():
    db = FakeDB([ValueError("coercion failed")])
    with pytest.raises(RuntimeError, match="fail-closed"):
        await schema_apply.apply_file(db, 6, "v006_test.surql", "UPDATE t SET x = 1;")
    assert len(db.executed) == 1


async def test_success_no_warnings():
    db = FakeDB([[], [{"id": "t:1"}]])
    warnings = await schema_apply.apply_file(db, STRICT, "v999_test.surql", "DEFINE TABLE t SCHEMALESS; CREATE t;")
    assert warnings == []
