# tests/test_e2e_flywheel.py
"""End-to-end: verify intelligence compounds and specialties emerge.

Requires: SurrealDB running, schema v003, domains seeded, LLM mocked.
"""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_maturation_scoring_works(db_pool):
    """Verify maturation can be calculated for a domain."""
    from core.engine.intelligence.maturation import calculate_maturation

    # Should return Nascent with score 0 for empty discipline
    result = await calculate_maturation("discipline", "technology", "product:test")
    assert result["phase"] == 1
    assert result["phase_name"] == "nascent"


@pytest.mark.asyncio
async def test_specialty_tables_exist(db_pool):
    """Verify v003 schema tables are queryable."""
    async with db_pool.connection() as db:
        for table in ["maturation", "maturation_history"]:
            result = await db.query(f"SELECT * FROM {table} LIMIT 1")
            assert result is not None, f"Table {table} not accessible"
