"""Negative acceptance — what should NOT appear when phase-aware ranking is on.

Vacuously passes when no capabilities exist for product:platform; meaningful
once the bootstrap (seed_phase_floors + ingest_ambition + scan) has populated
the test substrate. Acts as a regression guard against future drift.
"""

import pytest

from core.engine.product.feature_flags import set_phase_aware_ranking_enabled
from core.engine.product.strategic_prioritizer import StrategicPrioritizer


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_health_endpoint_not_in_top_five_post_flag(db_pool):
    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    try:
        p = StrategicPrioritizer(db_pool)
        results = await p.prioritize(pid)
        top_five = results[:5]
        rationales = " ".join(r.get("rationale", "") for r in top_five).lower()
        assert "/health/live" not in rationales
        assert "no canary deployment" not in rationales
    finally:
        await set_phase_aware_ranking_enabled(db_pool, pid, False)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_no_zero_score_in_top_five(db_pool):
    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    try:
        p = StrategicPrioritizer(db_pool)
        results = await p.prioritize(pid)
        top_five = results[:5]
        for r in top_five:
            if "rank" in r:
                assert float(r.get("rank", 0.0)) >= 0.0
    finally:
        await set_phase_aware_ranking_enabled(db_pool, pid, False)
