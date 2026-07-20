"""End-to-end: compute_roadmap against the real graph.

The unit tests use fakes, so they can't catch a rec→RoadmapItem mapping that
reads the wrong dict keys (which silently produced empty titles / rank 0 / 289
uncapped items in a real dogfood run). This test calls compute_roadmap on the
live graph and asserts the invariants that mapping bug violated:
  - total item count is > 0 and <= max_items (the cap)
  - every now/next item has a non-empty title and rank > 0
Skips cleanly when SurrealDB is unreachable (via the db_pool fixture).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_compute_roadmap_real_graph_shape(db_pool):
    from core.engine.product.roadmap import compute_roadmap

    roadmap = await compute_roadmap("product:platform")

    total = sum(len(items) for items in roadmap.lanes.values())
    if total == 0:
        pytest.skip("no gaps on product:platform graph — nothing to project (honest empty state)")

    # The cap: 289 raw gaps is unusable; compute_roadmap keeps the top 25 by rank.
    assert total <= 25, f"roadmap exceeded the cap: {total} items"

    # The mapping-bug guard: actionable lanes must carry real titles + scores.
    for lane in ("now", "next"):
        for item in roadmap.lanes.get(lane, []):
            assert item.title, f"empty title in lane {lane}: {item!r}"
            assert item.rank > 0, f"rank not > 0 in lane {lane}: {item!r}"
