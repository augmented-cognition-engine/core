from __future__ import annotations

import pytest

from core.engine.core.surreal32_upgrade import (
    SURREAL32_UPGRADE_CONTRACT,
    prepare_surreal32_upgrade,
)

pytestmark = pytest.mark.unit


class FakeSchemaDB:
    def __init__(self, tables: dict[str, dict]):
        self.tables = tables
        self.removed: list[tuple[str, str]] = []

    async def query(self, statement: str):
        if statement == "INFO FOR DB":
            return {"tables": {name: "definition" for name in self.tables}}
        if statement.startswith("INFO FOR TABLE "):
            return self.tables[statement.removeprefix("INFO FOR TABLE ")]
        if statement.startswith("REMOVE INDEX "):
            _, _, index, _, table = statement.split()
            self.tables[table]["indexes"].pop(index)
            self.removed.append((table, index))
            return []
        raise AssertionError(statement)


def _table(*, fields=(), indexes=None):
    return {
        "fields": {name: f"DEFINE FIELD {name}" for name in fields},
        "indexes": indexes or {},
    }


@pytest.mark.asyncio
async def test_dry_run_reports_only_missing_org_field_indexes_on_v061_tables():
    db = FakeSchemaDB(
        {
            "task": _table(
                fields=("product",),
                indexes={
                    "idx_task_org": "DEFINE INDEX idx_task_org ON task FIELDS org, status",
                    "idx_task_product": "DEFINE INDEX idx_task_product ON task FIELDS product, status",
                },
            ),
            "unrelated": _table(
                fields=("product",),
                indexes={"idx_other_org": "DEFINE INDEX idx_other_org ON unrelated FIELDS org"},
            ),
            "config_entry": {
                "fields": {"value": "DEFINE FIELD `value` ON config_entry TYPE string"},
                "indexes": {},
            },
        }
    )

    report = await prepare_surreal32_upgrade(db)

    assert report.contract == SURREAL32_UPGRADE_CONTRACT
    assert report.mode == "dry_run"
    assert [(item.table, item.index) for item in report.stale_indexes] == [("task", "idx_task_org")]
    assert report.config_value_idiom == "escaped"
    assert db.removed == []


@pytest.mark.asyncio
async def test_apply_removes_exact_findings_rechecks_and_is_idempotent():
    db = FakeSchemaDB(
        {
            "task": _table(
                fields=("product",),
                indexes={"idx_task_org": "DEFINE INDEX idx_task_org ON task FIELDS org, status"},
            ),
            "config_entry": {
                "fields": {"value": "DEFINE FIELD `value` ON config_entry TYPE string"},
                "indexes": {},
            },
        }
    )

    applied = await prepare_surreal32_upgrade(db, apply=True)
    replay = await prepare_surreal32_upgrade(db, apply=True)

    assert [(item.table, item.index) for item in applied.removed_indexes] == [("task", "idx_task_org")]
    assert applied.clean is True
    assert replay.removed_indexes == ()
    assert replay.clean is True
    assert db.removed == [("task", "idx_task_org")]


@pytest.mark.asyncio
async def test_apply_preserves_structurally_valid_org_index():
    db = FakeSchemaDB(
        {
            "task": _table(
                fields=("org",),
                indexes={"idx_task_org": "DEFINE INDEX idx_task_org ON task FIELDS org, status"},
            )
        }
    )

    report = await prepare_surreal32_upgrade(db, apply=True)
    assert report.clean is True
    assert db.removed == []
