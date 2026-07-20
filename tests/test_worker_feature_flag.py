import pytest


@pytest.mark.asyncio
async def test_default_false(db_pool):
    from core.engine.worker.feature_flag import is_worker_canvas_bridge_enabled

    assert await is_worker_canvas_bridge_enabled(db_pool, "product:platform") is False


@pytest.mark.asyncio
async def test_round_trip(db_pool):
    from core.engine.worker.feature_flag import (
        is_worker_canvas_bridge_enabled,
        set_worker_canvas_bridge_enabled,
    )

    pid = "product:platform"
    await set_worker_canvas_bridge_enabled(db_pool, pid, True)
    try:
        assert await is_worker_canvas_bridge_enabled(db_pool, pid) is True
    finally:
        await set_worker_canvas_bridge_enabled(db_pool, pid, False)
    assert await is_worker_canvas_bridge_enabled(db_pool, pid) is False
