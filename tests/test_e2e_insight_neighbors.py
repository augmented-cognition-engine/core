# tests/test_e2e_insight_neighbors.py
"""End-to-end: the relationship-aware reader follows a REAL Cognify edge.

This is the proof the mocked unit tests cannot give: against a live SurrealDB
v3, the reader binds seed/id params as RecordIDs so `IN $list` actually matches.
A string-bound reader returns zero rows here — this test would catch that.

Requires: SurrealDB running, schema applied. Skips cleanly (via db_pool) if the
pool is unreachable.
"""

import pytest

from core.engine.core.db import parse_record_id, parse_rows

pytestmark = pytest.mark.e2e

PRODUCT = "product:default"
SEED_ID = "insight:rt_a"
NBR_ID = "insight:rt_b"
PREFIX = "INSIGHT-NEIGHBORS-E2E"


@pytest.mark.asyncio
async def test_reader_follows_real_cognify_edge(db_pool):
    """Reader returns the depends_on neighbor of a real seed, tagged outgoing.

    1. Create two active/open insights in the test product.
    2. RELATE rt_a -> depends_on -> rt_b with source='cognify'.
    3. load_insight_neighbors(["insight:rt_a"], product) returns exactly rt_b.
    4. Tear everything down in finally.
    """
    from core.engine.graph.insight_neighbors import load_insight_neighbors

    try:
        # ------------------------------------------------------------------
        # Step 1 — Create two real insight records (explicit ids)
        # ------------------------------------------------------------------
        async with db_pool.connection() as db:
            for rid, content in ((SEED_ID, "seed"), (NBR_ID, "neighbor")):
                created = await db.query(
                    f"""
                    CREATE {rid} SET
                        product       = <record>$product,
                        insight_type  = 'fact',
                        tier          = 'specialty',
                        content       = <string>$content,
                        status        = 'active',
                        confidence    = 0.8,
                        source_domain = 'sentinel.test',
                        clearance     = 'open',
                        created_at     = time::now(),
                        updated_at     = time::now(),
                        last_confirmed = time::now()
                    """,
                    {"product": PRODUCT, "content": f"{PREFIX}: {content}"},
                )
                assert parse_rows(created), f"Failed to create {rid}"

        # ------------------------------------------------------------------
        # Step 2 — RELATE the Cognify edge (source='cognify', confidence=0.9).
        # Bind endpoints as RecordIDs — same lesson as the reader fix: this
        # SurrealDB build rejects `RELATE <record>$param`, so cast in Python.
        # ------------------------------------------------------------------
        async with db_pool.connection() as db:
            edge = await db.query(
                "RELATE $a -> depends_on -> $b SET source = 'cognify', confidence = 0.9, created_at = time::now()",
                {"a": parse_record_id(SEED_ID), "b": parse_record_id(NBR_ID)},
            )
            assert parse_rows(edge), "Failed to create cognify edge"

        # ------------------------------------------------------------------
        # Step 3 — The reader must follow the edge — NON-EMPTY, specific
        # ------------------------------------------------------------------
        result = await load_insight_neighbors([SEED_ID], PRODUCT)

        assert len(result) == 1, f"Expected exactly the rt_b neighbor, got: {result}"
        nbr = result[0]
        assert nbr["insight_id"] == NBR_ID
        assert nbr["relationship"] == "depends_on"
        assert nbr["direction"] == "outgoing"
        assert nbr["via_insight"] == SEED_ID
        assert nbr["edge_confidence"] == 0.9
        assert nbr["content"] == f"{PREFIX}: neighbor"
    finally:
        # ------------------------------------------------------------------
        # Step 4 — Tear down the two insights + the edge
        # ------------------------------------------------------------------
        async with db_pool.connection() as db:
            await db.query(f"DELETE depends_on WHERE in = {SEED_ID} AND out = {NBR_ID}")
            await db.query(f"DELETE {SEED_ID}")
            await db.query(f"DELETE {NBR_ID}")
