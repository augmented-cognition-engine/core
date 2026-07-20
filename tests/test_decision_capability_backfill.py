"""Tests for the nightly decision_capability_backfill sentinel.

Tests the drift-catcher that re-infers decisions created in the last 24h
without affected_capabilities tags.

Spec: docs/superpowers/specs/2026-05-14-layer5-context-assembly-design.md §6.8
"""

from __future__ import annotations

import pytest

from core.engine.core.db import parse_rows
from core.engine.sentinel.engines.decision_capability_backfill import decision_capability_backfill
from core.engine.sentinel.registry import get_engine


@pytest.mark.asyncio
async def test_sentinel_only_processes_last_24h_uninferred(db_pool, monkeypatch):
    """Sentinel filters to decisions created in last 24h with no inferred_at tag.

    - Seeds 2 OLD decisions (48h ago, uninferred)
    - Seeds 3 RECENT decisions (1h ago, uninferred)
    - Monkeypatches the LLM to return stub inference results
    - Asserts the 3 recent ones are inferred
    - Asserts the 2 old decisions remain untouched
    """

    # Stub LLM to avoid actual calls
    async def stub_infer_batch(rows):
        """Return empty caps for all rows."""
        print(f"DEBUG: stub_infer_batch called with {len(rows)} rows")
        return {row["id"]: ([], 0.75) for row in rows}

    # Patch at the module level where it's imported
    import core.engine.intelligence.decision_capability_inference

    monkeypatch.setattr(
        core.engine.intelligence.decision_capability_inference,
        "_infer_batch",
        stub_infer_batch,
    )

    test_marker = "test_sentinel_24h"
    old_ids = []
    recent_ids = []

    async with db_pool.connection() as db:
        # Seed 2 OLD decisions (48 hours ago)
        for i in range(2):
            old_result = await db.query(
                """CREATE decision SET
                    product = <record>$product,
                    title = $title,
                    rationale = $rationale,
                    decision_type = "architecture",
                    created_at = time::now() - 48h,
                    affected_capabilities_inferred_at = NONE
                RETURN id""",
                {
                    "product": "product:test_sentinel",
                    "title": f"old decision {i + 1}",
                    "rationale": f"{test_marker}_old_{i + 1}",
                },
            )
            rows = parse_rows(old_result)
            if rows:
                old_ids.append(rows[0]["id"])

        # Seed 3 RECENT decisions (1 hour ago, uninferred)
        for i in range(3):
            recent_result = await db.query(
                """CREATE decision SET
                    product = <record>$product,
                    title = $title,
                    rationale = $rationale,
                    decision_type = "architecture",
                    created_at = time::now() - 1h,
                    affected_capabilities_inferred_at = NONE
                RETURN id""",
                {
                    "product": "product:test_sentinel",
                    "title": f"recent decision {i + 1}",
                    "rationale": f"{test_marker}_recent_{i + 1}",
                },
            )
            rows = parse_rows(recent_result)
            if rows:
                recent_ids.append(rows[0]["id"])

    # Run the sentinel
    await decision_capability_backfill(db_pool)

    # Verify the seeded rows individually. SurrealDB v3 doesn't match
    # `WHERE id IN $ids` against a list of plain strings — needs <record>
    # casting per element. Per-row SELECT is the simpler workaround.
    from core.engine.core.db import parse_one

    async with db_pool.connection() as db:
        for rid in old_ids:
            r = await db.query(
                "SELECT id, affected_capabilities_inferred_at FROM decision WHERE id = <record>$rid",
                {"rid": rid},
            )
            row = parse_one(r)
            assert row is not None, f"Old decision {rid} missing after sentinel run"
            assert row.get("affected_capabilities_inferred_at") is None, (
                f"Old decision {rid} was incorrectly inferred (48h-ago should be outside the sentinel's 24h window)"
            )

        inferred_recent = 0
        for rid in recent_ids:
            r = await db.query(
                "SELECT id, affected_capabilities_inferred_at FROM decision WHERE id = <record>$rid",
                {"rid": rid},
            )
            row = parse_one(r)
            assert row is not None, f"Recent decision {rid} missing after sentinel run"
            if row.get("affected_capabilities_inferred_at") is not None:
                inferred_recent += 1

        assert inferred_recent == len(recent_ids), (
            f"Expected all {len(recent_ids)} recent decisions to be inferred, got {inferred_recent}"
        )


def test_sentinel_registers_with_cron_0_4():
    """Sentinel is registered with cron "0 4 * * *" (4am daily)."""
    entry = get_engine("decision_capability_backfill")
    assert entry is not None, "decision_capability_backfill not registered"
    assert entry["cron"] == "0 4 * * *", f"Expected cron '0 4 * * *', got {entry['cron']}"
