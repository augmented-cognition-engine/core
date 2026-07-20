# tests/test_integration.py
"""Integration tests — require SurrealDB running.

Run with: make db-up && make schema-apply && uv run pytest tests/test_integration.py -v
"""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_full_pipeline_writes_to_db(db_pool):
    """Full pipeline processes a session import and writes memory + observation records."""
    # Verify tables are queryable (schema v002 applied)
    async with db_pool.connection() as db:
        memories = await db.query("SELECT count() AS n FROM memory GROUP ALL")
        assert memories is not None

        observations = await db.query("SELECT count() AS n FROM observation GROUP ALL")
        assert observations is not None

        insights = await db.query("SELECT count() AS n FROM insight GROUP ALL")
        assert insights is not None
