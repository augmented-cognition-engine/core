"""Tests for edge_inference helper — causal-edge inference rules + idempotency."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_score_changed_triggered_by_recent_gap():
    """canvas.score.changed within 1h of gap.detected for same pillar → triggered edge."""
    from core.engine.cognition.edge_inference import infer_edges_for_product
    from core.engine.core.db import parse_one, pool

    await pool.init()
    async with pool.connection() as db:
        await db.query(
            "DELETE journey_event WHERE topic IN ['gap.detected', 'canvas.score.changed'] AND product = product:test_inf"
        )
        await db.query("DELETE reasoning_edge WHERE product = product:test_inf")

        gap = parse_one(
            await db.query(
                "CREATE journey_event SET topic='gap.detected', product=product:test_inf, "
                "payload={pillar:'security'}, occurred_at=time::now() - 30m RETURN AFTER"
            )
        )
        score = parse_one(
            await db.query(
                "CREATE journey_event SET topic='canvas.score.changed', product=product:test_inf, "
                "payload={pillar:'security', new_score:0.7}, occurred_at=time::now() RETURN AFTER"
            )
        )

    try:
        edges = await infer_edges_for_product(pool, "product:test_inf")
        # Should produce at least one edge: score.changed ← triggered ← gap.detected
        match = [e for e in edges if e["from_event"] == str(gap["id"]) and e["to_event"] == str(score["id"])]
        assert match, f"expected triggered edge gap→score, got {edges}"
        assert match[0]["edge_type"] == "triggered"
    finally:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_inf")
            await db.query("DELETE reasoning_edge WHERE product = product:test_inf")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_inference_idempotent():
    """Re-running inference produces zero new edges (UNIQUE index)."""
    from core.engine.cognition.edge_inference import infer_edges_for_product
    from core.engine.core.db import parse_rows, pool

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE journey_event WHERE product = product:test_inf2")
        await db.query("DELETE reasoning_edge WHERE product = product:test_inf2")
        await db.query(
            "CREATE journey_event SET topic='gap.detected', product=product:test_inf2, "
            "payload={pillar:'ux'}, occurred_at=time::now() - 30m"
        )
        await db.query(
            "CREATE journey_event SET topic='canvas.score.changed', product=product:test_inf2, "
            "payload={pillar:'ux', new_score:0.65}, occurred_at=time::now()"
        )

    try:
        first = await infer_edges_for_product(pool, "product:test_inf2")
        second = await infer_edges_for_product(pool, "product:test_inf2")
        # Second call returns 0 NEW edges (existing ones already in reasoning_edge)
        assert len(second) == 0, f"expected 0 new edges on second call, got {len(second)}"
        # Total edges in DB unchanged
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT id FROM reasoning_edge WHERE product = product:test_inf2"))
        assert len(rows) == len(first)
    finally:
        async with pool.connection() as db:
            await db.query("DELETE journey_event WHERE product = product:test_inf2")
            await db.query("DELETE reasoning_edge WHERE product = product:test_inf2")
