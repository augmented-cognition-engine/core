"""e2e: WHERE col IN $list matches only when bound as RecordIDs (SurrealDB v3).

Class-proof for the string-vs-RecordID binding bug fixed across the codebase.
Skips cleanly (via db_pool) if the pool is unreachable.
"""

import pytest

from core.engine.core.db import parse_record_id, parse_record_ids, parse_rows

pytestmark = pytest.mark.e2e

A = "insight:rt_rb_a"
B = "insight:rt_rb_b"

_FIXTURE_DATA = {
    "status": "active",
    "clearance": "open",
    "insight_type": "observation",
    "source_domain": "test",
    "tier": "standard",
    "confidence": 0.5,
    "product": None,  # filled per-row below
}


@pytest.mark.asyncio
async def test_in_list_needs_record_ids(db_pool):
    try:
        async with db_pool.connection() as db:
            for rid, letter in ((A, "a"), (B, "b")):
                await db.query(
                    f"CREATE {rid} CONTENT $data",
                    {
                        "data": {
                            **_FIXTURE_DATA,
                            "content": f"test-{letter}",
                            "product": parse_record_id("product:default"),
                        }
                    },
                )
        async with db_pool.connection() as db:
            # String-bound (the bug): zero matches.
            str_rows = parse_rows(await db.query("SELECT id FROM insight WHERE id IN $ids", {"ids": [A, B]}))
            # RecordID-bound (the fix): matches both.
            rec_rows = parse_rows(
                await db.query(
                    "SELECT id FROM insight WHERE id IN $ids",
                    {"ids": parse_record_ids([A, B])},
                )
            )
        assert str_rows == [], f"string IN $list unexpectedly matched: {str_rows}"
        assert len(rec_rows) == 2, f"RecordID IN $list should match both, got: {rec_rows}"
    finally:
        async with db_pool.connection() as db:
            await db.query(f"DELETE {A}")
            await db.query(f"DELETE {B}")
