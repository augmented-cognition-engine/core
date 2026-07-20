"""e2e: RELATE needs `$param` (RecordID-bound), not `<record>$param` (parse error).

Class guard for the 7-site RELATE <record> cast sweep. Skips if DB unreachable.
"""

import pytest

from core.engine.core.db import parse_record_id, parse_rows

pytestmark = pytest.mark.e2e

A = "graph_file:rt_relate_a"
B = "capability:rt_relate_b"


@pytest.mark.asyncio
async def test_relate_needs_recordid_not_cast(db_pool):
    try:
        async with db_pool.connection() as db:
            # the OLD broken form must parse-fail
            failed = False
            try:
                await db.query("RELATE <record>$a -> realizes -> <record>$b SET x = 1", {"a": A, "b": B})
            except Exception:
                failed = True
            assert failed, "RELATE <record>$x unexpectedly parsed — sweep premise wrong"

            # the FIXED form (RecordID-bound, no cast) must write a readable edge
            await db.query(
                "RELATE $a -> realizes -> $b SET source = 'rt-test', created_at = time::now()",
                {"a": parse_record_id(A), "b": parse_record_id(B)},
            )
            rows = parse_rows(
                await db.query(
                    "SELECT in, out, source FROM realizes WHERE in = $a AND out = $b",
                    {"a": parse_record_id(A), "b": parse_record_id(B)},
                )
            )
        assert len(rows) == 1 and rows[0].get("source") == "rt-test"
    finally:
        async with db_pool.connection() as db:
            await db.query("DELETE realizes WHERE in = graph_file:rt_relate_a AND out = capability:rt_relate_b")
