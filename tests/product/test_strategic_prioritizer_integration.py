import pytest

from core.engine.product.feature_flags import set_phase_aware_ranking_enabled
from core.engine.product.strategic_prioritizer import StrategicPrioritizer


@pytest.mark.asyncio
async def test_legacy_path_when_flag_off(db_pool):
    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, False)
    p = StrategicPrioritizer(db_pool)
    results = await p.prioritize(pid)
    assert isinstance(results, list)
    if results:
        assert "pillar" not in results[0]


@pytest.mark.asyncio
async def test_ranked_output_includes_pillar_when_flag_on(db_pool):
    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    try:
        p = StrategicPrioritizer(db_pool)
        results = await p.prioritize(pid)
        assert isinstance(results, list)
        if results:
            first = results[0]
            assert "pillar" in first
            assert "rank" in first
            assert "ambition_relevance" in first
    finally:
        await set_phase_aware_ranking_enabled(db_pool, pid, False)
