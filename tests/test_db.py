# tests/test_db.py
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_pool_connects_and_queries(db_pool):
    async with db_pool.connection() as db:
        result = await db.query("RETURN 1")
    # SDK 2 correctly raises for missing tables; connectivity uses valid SurrealQL.
    assert result is not None


@pytest.mark.asyncio
async def test_pool_concurrent_connections(db_pool):
    import asyncio

    async def run_query():
        async with db_pool.connection() as db:
            return await db.query("RETURN time::now()")

    results = await asyncio.gather(*[run_query() for _ in range(5)])
    assert len(results) == 5
