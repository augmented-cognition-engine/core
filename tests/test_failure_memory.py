from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_failure_memory_write_called_on_gaps():
    """When VerificationGate returns gaps, failure_memory write is triggered."""
    from core.engine.orchestration.executor import _write_failure_memory

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.query = AsyncMock(return_value=[])

        await _write_failure_memory(
            product_id="product:test",
            discipline="coding",
            task_summary="Add rate limiting to the API",
            gaps=["Missing Retry-After header", "No multi-worker test"],
            verdict="gaps_found",
        )

        assert mock_conn.query.call_count >= 1
        all_sql = [c[0][0] for c in mock_conn.query.call_args_list]
        assert any("CREATE failure_memory" in s for s in all_sql)


@pytest.mark.asyncio
async def test_failure_memory_write_skips_on_clean_verdict():
    """Clean or skipped verification verdicts must NOT write failure_memory entries."""
    from core.engine.orchestration.executor import _write_failure_memory

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.query = AsyncMock(return_value=[])

        for verdict in ("clean", "skipped"):
            await _write_failure_memory(
                product_id="product:test",
                discipline="coding",
                task_summary="task",
                gaps=["gap"],
                verdict=verdict,
            )

        mock_conn.query.assert_not_called()


@pytest.mark.asyncio
async def test_failure_memory_write_skips_on_empty_gaps():
    """No gaps means nothing to record — must not write."""
    from core.engine.orchestration.executor import _write_failure_memory

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.query = AsyncMock(return_value=[])

        await _write_failure_memory(
            product_id="product:test",
            discipline="coding",
            task_summary="task",
            gaps=[],
            verdict="gaps_found",
        )

        mock_conn.query.assert_not_called()
