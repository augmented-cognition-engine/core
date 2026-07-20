# tests/test_e2e_edge_writer.py
"""End-to-end: create_edge actually writes a readable edge against live SurrealDB.

Regression guard for the `RELATE <record>$param` parse error (SurrealDB v3) that
made create_edge — and thus EVERY edge writer routing through it (Cognify,
edge_inference, decisions, spec_generator, …) — a SILENT no-op: the parse error
was swallowed by create_edge's own try/except and it returned None, writing
nothing. The mocked unit tests assert the query CONTAINS 'RELATE'; they cannot
catch a parse error only the real DB raises.

Requires SurrealDB; skips cleanly (via db_pool) if the pool is unreachable.
"""

import pytest

from core.engine.core.db import parse_record_id, parse_rows

pytestmark = pytest.mark.e2e

A = "insight:rt_ew_a"
B = "insight:rt_ew_b"


@pytest.mark.asyncio
async def test_create_edge_writes_readable_edge(db_pool):
    """create_edge must produce a real, readable edge — not silently return None."""
    from core.engine.graph.edge_writer import create_edge

    try:
        async with db_pool.connection() as db:
            for rid in (A, B):
                await db.query(
                    f"CREATE {rid} SET content = 'x', status = 'active', "
                    "clearance = 'open', product = <record>$p, created_at = time::now()",
                    {"p": "product:default"},
                )

        result = await create_edge("depends_on", A, B, metadata={"source": "cognify", "confidence": 0.9})
        assert result is not None, "create_edge returned None — edge was NOT written"

        async with db_pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT in, out, source, confidence FROM depends_on WHERE in = $a AND out = $b",
                    {"a": parse_record_id(A), "b": parse_record_id(B)},
                )
            )
        assert len(rows) == 1, f"expected exactly one edge, got: {rows}"
        assert rows[0].get("source") == "cognify"
        assert rows[0].get("confidence") == 0.9
    finally:
        async with db_pool.connection() as db:
            await db.query(f"DELETE depends_on WHERE in = {A} AND out = {B}")
            await db.query(f"DELETE {A}")
            await db.query(f"DELETE {B}")
