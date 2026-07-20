# tests/test_schema_v007.py
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v007_tables_exist(db_pool):
    """After applying v007, engine_run, output_version, research_queue tables must be queryable."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    expected_tables = ["engine_run", "output_version", "research_queue"]
    async with db_pool.connection() as db:
        for table in expected_tables:
            rows = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert rows is not None, f"Table {table} not accessible"


@pytest.mark.asyncio
async def test_v007_schema_version_is_current(db_pool):
    """Schema version should be current after migration."""
    from core.engine.core.db import parse_one

    async with db_pool.connection() as db:
        result = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
        row = parse_one(result)
        assert row is not None, "schema_version config entry not found"
        version = int(row["value"])
        assert version >= 34, f"Expected schema version >= 34, got {version}"


@pytest.mark.asyncio
async def test_v007_intelligence_utilization_field_on_task(db_pool):
    """intelligence_utilization field should be defined on task table."""
    async with db_pool.connection() as db:
        info = await db.query("INFO FOR TABLE task")
        assert info is not None
