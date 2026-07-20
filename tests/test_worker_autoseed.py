# tests/test_worker_autoseed.py
"""Regression tests for framework auto-seed on worker startup.

The framework table being empty causes every phase to fall back to the
sentinel string "Apply {fn} reasoning to structure your thinking here."
Auto-seed fires on lifespan startup when the table is empty, preventing
this silent degradation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_lifespan_triggers_seed_when_table_empty():
    """Sentinel: lifespan must call seed_all() when framework count is 0.

    Without this, every phase falls back to 'Apply {fn} reasoning here.'
    """
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[{"n": 0}]),
        patch("core.engine.cognition.seed.seed_all", new_callable=AsyncMock) as mock_seed_all,
        patch("core.engine.worker.processor.run_poll_cycle", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.init", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.close", new_callable=AsyncMock),
    ):
        mock_pool.connection.return_value = mock_ctx
        mock_pool.init = AsyncMock()
        mock_pool.close = AsyncMock()

        # Exercise the lifespan startup path only

        from core.engine.worker.app import app as worker_app
        from core.engine.worker.app import lifespan

        ctx = lifespan(worker_app)
        await ctx.__aenter__()
        # Immediately exit (cancel poll task cleanly)
        try:
            await ctx.__aexit__(None, None, None)
        except Exception:
            pass

    # Sentinel: seed_all must have been called when count == 0
    mock_seed_all.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_skips_seed_when_frameworks_exist():
    """Lifespan must NOT call seed_all() when frameworks are already seeded."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[{"n": 184}]),
        patch("core.engine.cognition.seed.seed_all", new_callable=AsyncMock) as mock_seed_all,
        patch("core.engine.worker.processor.run_poll_cycle", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.init", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.close", new_callable=AsyncMock),
    ):
        mock_pool.connection.return_value = mock_ctx
        mock_pool.init = AsyncMock()
        mock_pool.close = AsyncMock()

        from core.engine.worker.app import app as worker_app
        from core.engine.worker.app import lifespan

        ctx = lifespan(worker_app)
        await ctx.__aenter__()
        try:
            await ctx.__aexit__(None, None, None)
        except Exception:
            pass

    # Must NOT seed when frameworks already exist
    mock_seed_all.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_seed_failure_is_non_fatal():
    """seed_all() raising must not crash the worker startup."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[{"n": 0}]),
        patch("core.engine.cognition.seed.seed_all", side_effect=Exception("seed DB unreachable")),
        patch("core.engine.worker.processor.run_poll_cycle", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.init", new_callable=AsyncMock),
        patch("core.engine.core.db.pool.close", new_callable=AsyncMock),
    ):
        mock_pool.connection.return_value = mock_ctx
        mock_pool.init = AsyncMock()
        mock_pool.close = AsyncMock()

        from core.engine.worker.app import app as worker_app
        from core.engine.worker.app import lifespan

        ctx = lifespan(worker_app)
        # Must not raise — seed failure is non-fatal
        await ctx.__aenter__()
        try:
            await ctx.__aexit__(None, None, None)
        except Exception:
            pass
