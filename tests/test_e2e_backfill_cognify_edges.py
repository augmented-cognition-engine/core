# tests/test_e2e_backfill_cognify_edges.py
"""e2e: the backfill's insight-load query actually parses + runs on SurrealDB v3.

Guards the load_insights SQL (the unit tests mock the DB and can't catch a
parse error like the `ORDER BY created_at` projection-strictness rule). Skips
cleanly (via db_pool) if the pool is unreachable.
"""

import pytest

pytestmark = pytest.mark.e2e

RID = "insight:rt_bf_a"


@pytest.mark.asyncio
async def test_load_insights_query_runs(db_pool):
    from scripts.backfill_cognify_edges import load_insights

    try:
        async with db_pool.connection() as db:
            await db.query(
                f"CREATE {RID} SET content='backfill-e2e', status='active', clearance='open', "
                "product=<record>$p, confidence=0.8, insight_type='fact', tier='specialty', "
                "source_domain='sentinel.test', created_at=time::now(), updated_at=time::now(), "
                "last_confirmed=time::now()",
                {"p": "product:default"},
            )
        async with db_pool.connection() as db:
            rows = await load_insights(db, product="product:default", max_rows=50)
        ids = [r["id"] for r in rows]
        assert RID in ids, f"load_insights did not return the created insight: {ids[:5]}"
        row = next(r for r in rows if r["id"] == RID)
        assert row["content"] == "backfill-e2e"
        assert set(row.keys()) == {"id", "content", "embedding"}  # returned shape
    finally:
        async with db_pool.connection() as db:
            await db.query(f"DELETE {RID}")
