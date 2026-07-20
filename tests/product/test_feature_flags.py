import pytest

from core.engine.product.feature_flags import (
    is_phase_aware_ranking_enabled,
    set_phase_aware_ranking_enabled,
)


@pytest.mark.asyncio
async def test_default_is_off_at_merge(db_pool):
    enabled = await is_phase_aware_ranking_enabled(db_pool, "product:test_ff")
    assert enabled is False


@pytest.mark.asyncio
async def test_can_be_enabled_per_product(db_pool):
    pid = "product:test_ff_2"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    enabled = await is_phase_aware_ranking_enabled(db_pool, pid)
    assert enabled is True
    await set_phase_aware_ranking_enabled(db_pool, pid, False)
    enabled = await is_phase_aware_ranking_enabled(db_pool, pid)
    assert enabled is False
    async with db_pool.connection() as db:
        await db.query("DELETE product_feature_flag WHERE product = <record>$pid", {"pid": pid})
