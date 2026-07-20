import pytest

from core.engine.product.pillar_aggregator import PillarAggregator
from core.engine.product.pillars import Pillar


def test_pillar_aggregator_computes_from_legacy_dims():
    agg = PillarAggregator(pool=None)
    dim_scores = {"ux": 0.8, "accessibility": 0.6, "security": 0.5}
    pillar_scores = agg._aggregate_from_dim_scores(dim_scores)
    assert abs(pillar_scores[Pillar.EXPERIENCE] - 0.7) < 0.001
    assert abs(pillar_scores[Pillar.TRUST] - 0.5) < 0.001


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pillar_aggregator_caches_and_invalidates(db_pool):
    agg = PillarAggregator(db_pool)
    pid = "product:test_pillar_cache"
    await agg._write_cache(pid, Pillar.EXPERIENCE, 0.65)
    cached = await agg._read_cache(pid, Pillar.EXPERIENCE)
    assert cached is not None and abs(cached - 0.65) < 0.001
    await agg.invalidate(pid)
    cached_after = await agg._read_cache(pid, Pillar.EXPERIENCE)
    assert cached_after is None
