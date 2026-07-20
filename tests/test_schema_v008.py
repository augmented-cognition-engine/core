# tests/test_schema_v008.py
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_briefing_table_exists(db_pool):
    """v008: briefing table must be queryable."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/schema_apply.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    async with db_pool.connection() as db:
        r = await db.query("INFO FOR TABLE briefing")
        assert r is not None


@pytest.mark.asyncio
async def test_conflict_resolution_type_field(db_pool):
    """v008: conflict table must have resolution_type field."""
    async with db_pool.connection() as db:
        r = await db.query("INFO FOR TABLE conflict")
        info_str = str(r)
        assert "resolution_type" in info_str
