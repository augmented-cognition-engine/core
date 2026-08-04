# tests/test_worker_autoseed.py
"""Regression tests for framework integrity and worker lifecycle startup.

A missing or partial framework library causes phases to fall back to the
sentinel string "Apply {fn} reasoning to structure your thinking here."
Workers verify the same complete 177-prompt contract as the API.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_seed_all_callable():
    """seed_all() must exist as an async function — not just main() + asyncio.run()."""
    import inspect

    from core.engine.cognition.seed import seed_all

    assert inspect.iscoroutinefunction(seed_all), (
        "seed_all must be async — calling asyncio.run() inside a running event loop raises RuntimeError"
    )


@pytest.mark.asyncio
async def test_seed_all_calls_both_seeders():
    """seed_all() must call both seed_frameworks() and seed_meta_skills()."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("core.engine.cognition.seed.seed_frameworks", new_callable=AsyncMock) as mock_frameworks,
        patch("core.engine.cognition.seed.seed_meta_skills", new_callable=AsyncMock) as mock_meta,
    ):
        from core.engine.cognition.seed import seed_all

        await seed_all()

    mock_frameworks.assert_called_once()
    mock_meta.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_verifies_complete_framework_library():
    started: set[str] = set()
    cancelled: set[str] = set()

    async def blocked(name: str, *_args, **_kwargs):
        started.add(name)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(name)
            raise

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch(
            "core.engine.cognition.seed.ensure_frameworks_seeded",
            new_callable=AsyncMock,
            return_value=177,
        ) as mock_ensure,
        patch("core.engine.worker.app._live_observe_loop", new=lambda: blocked("live")),
        patch("core.engine.worker.app._continuous_drain_loop", new=lambda: blocked("drain")),
        patch(
            "core.engine.worker.fs_watcher.run_fs_watcher",
            new=lambda **kwargs: blocked("watcher", **kwargs),
        ),
    ):
        mock_pool.init = AsyncMock()
        mock_pool.close = AsyncMock()

        from core.engine.worker.app import app as worker_app
        from core.engine.worker.app import lifespan

        ctx = lifespan(worker_app)
        await ctx.__aenter__()
        await asyncio.sleep(0)
        await ctx.__aexit__(None, None, None)

    mock_ensure.assert_awaited_once()
    assert started == {"live", "drain", "watcher"}
    assert cancelled == started
    mock_pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_framework_failure_is_fatal():
    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch(
            "core.engine.cognition.seed.ensure_frameworks_seeded",
            new_callable=AsyncMock,
            side_effect=RuntimeError("framework seed incomplete"),
        ),
    ):
        mock_pool.init = AsyncMock()
        mock_pool.close = AsyncMock()

        from core.engine.worker.app import app as worker_app
        from core.engine.worker.app import lifespan

        ctx = lifespan(worker_app)
        with pytest.raises(RuntimeError, match="cannot start without"):
            await ctx.__aenter__()
