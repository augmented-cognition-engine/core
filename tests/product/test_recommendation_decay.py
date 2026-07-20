import pytest

from core.engine.product.recommendation_decay import (
    acknowledge,
    apply_decay,
    get_decay_state,
    increment_briefing_count,
)


async def _cleanup_decay_rows(pool):
    async with pool.connection() as db:
        await db.query("DELETE recommendation_decay_state WHERE product = product:test_decay")


@pytest.mark.asyncio
async def test_decay_state_starts_at_zero(db_pool):
    await _cleanup_decay_rows(db_pool)
    state = await get_decay_state(db_pool, "rec:test_decay_1", "product:test_decay")
    assert state.consecutive_briefings_at_top == 0


@pytest.mark.asyncio
async def test_increment_briefing_count(db_pool):
    await _cleanup_decay_rows(db_pool)
    rec_id = "rec:test_decay_2"
    pid = "product:test_decay"
    await increment_briefing_count(db_pool, rec_id, pid)
    await increment_briefing_count(db_pool, rec_id, pid)
    state = await get_decay_state(db_pool, rec_id, pid)
    assert state.consecutive_briefings_at_top == 2
    await _cleanup_decay_rows(db_pool)


@pytest.mark.asyncio
async def test_acknowledge_resets_count(db_pool):
    await _cleanup_decay_rows(db_pool)
    rec_id = "rec:test_decay_3"
    pid = "product:test_decay"
    await increment_briefing_count(db_pool, rec_id, pid)
    await increment_briefing_count(db_pool, rec_id, pid)
    await acknowledge(db_pool, rec_id)
    state = await get_decay_state(db_pool, rec_id, pid)
    assert state.consecutive_briefings_at_top == 0
    await _cleanup_decay_rows(db_pool)


def test_apply_decay_no_decay_below_threshold():
    rank = 1.0
    decayed = apply_decay(rank, consecutive_briefings_at_top=4)
    assert decayed == 1.0


def test_apply_decay_at_threshold():
    rank = 1.0
    decayed = apply_decay(rank, consecutive_briefings_at_top=5)
    assert abs(decayed - 1.0) < 0.001


def test_apply_decay_above_threshold():
    rank = 1.0
    decayed = apply_decay(rank, consecutive_briefings_at_top=8)
    assert abs(decayed - 0.85**3) < 0.001
