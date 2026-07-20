# tests/canvas/test_schema.py
import pytest

from core.engine.core.db import parse_one

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_canvas_session_table_exists(db_pool):
    async with db_pool.connection() as db:
        test_id = "canvas_session:schema_probe"
        await db.query(
            f"UPSERT {test_id} SET project_id = 'product:platform', "
            f"title = 'schema probe', created_at = time::now(), updated_at = time::now();"
        )
        result = await db.query(f"SELECT id FROM {test_id};")
    row = parse_one(result)
    assert row is not None and row["id"] is not None, "canvas_session table must exist after v103 migration"


@pytest.mark.asyncio
async def test_canvas_artifact_table_exists(db_pool):
    async with db_pool.connection() as db:
        test_id = "canvas_artifact:schema_probe"
        await db.query(
            f"UPSERT {test_id} SET session_id = 'canvas_session:probe', "
            f"kind = 'sticky', payload = {{}}, created_at = time::now();"
        )
        result = await db.query(f"SELECT id FROM {test_id};")
    row = parse_one(result)
    assert row is not None and row["id"] is not None, "canvas_artifact table must exist after v103 migration"


@pytest.mark.asyncio
async def test_decision_has_surface_field(db_pool):
    async with db_pool.connection() as db:
        sid = "canvas_session:test_decision_field"
        # UPSERT is idempotent across test runs.
        await db.query(
            f"UPSERT {sid} SET project_id = 'product:platform', created_at = time::now(), updated_at = time::now();"
        )
        rid = "decision:test_surface_field"
        # decision table requires: product (record<product>), title, decision_type, rationale
        # per v040 + v058/v061 (org renamed to product). All must be supplied or SurrealDB
        # returns a coercion-error string (not an exception) and the record is not created.
        await db.query(
            f"UPSERT {rid} SET "
            f"product = product:platform, "
            f"title = 't', "
            f"decision_type = 'architecture', "
            f"rationale = 'test', "
            f"surface = 'canvas', "
            f"canvas_session_id = {sid}, "
            f"cited_artifact_ids = ['canvas_artifact:a1'], "
            f"framework_kind = 'trade_off_matrix', "
            f"created_at = time::now();"
        )
        result = await db.query(f"SELECT surface, canvas_session_id, cited_artifact_ids, framework_kind FROM {rid};")
    row = parse_one(result)
    assert row is not None, "decision row should exist"
    assert row["surface"] == "canvas"
    assert row["canvas_session_id"] is not None
    assert row["framework_kind"] == "trade_off_matrix"
    assert row["cited_artifact_ids"] == ["canvas_artifact:a1"]
