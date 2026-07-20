import pytest


@pytest.mark.asyncio
async def test_closed_loop_learning_enabled_default_false(db_pool):
    from core.engine.learning.feature_flag import is_closed_loop_learning_enabled

    assert await is_closed_loop_learning_enabled(db_pool, "product:platform") is False


@pytest.mark.asyncio
async def test_closed_loop_learning_round_trip(db_pool):
    from core.engine.learning.feature_flag import (
        is_closed_loop_learning_enabled,
        set_closed_loop_learning_enabled,
    )

    pid = "product:platform"
    await set_closed_loop_learning_enabled(db_pool, pid, True)
    try:
        assert await is_closed_loop_learning_enabled(db_pool, pid) is True
    finally:
        await set_closed_loop_learning_enabled(db_pool, pid, False)
    assert await is_closed_loop_learning_enabled(db_pool, pid) is False
