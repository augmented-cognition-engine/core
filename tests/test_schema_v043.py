import pytest

pytestmark = pytest.mark.e2e


async def test_schema_v043_applies(db_health, db_pool):
    """v043 migration creates composition_signal and token_baseline tables."""
    async with db_pool.connection() as db:
        result = await db.query("INFO FOR TABLE composition_signal")
        assert result is not None

        result = await db.query("INFO FOR TABLE token_baseline")
        assert result is not None


async def test_schema_v043_idempotent(db_health, db_pool):
    """Running v043 twice doesn't error."""
    from pathlib import Path

    schema = Path("schema/v043_composition_memory.surql").read_text()
    async with db_pool.connection() as db:
        await db.query(schema)
        await db.query(schema)  # second run should not fail
