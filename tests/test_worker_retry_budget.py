# tests/test_worker_retry_budget.py
"""Tests for observation retry budget — durability fix.

Before this fix, first synthesizer failure → observation marked 'failed' permanently.
After this fix: observation stays 'pending' with retry_count incremented, only marks
'failed' after MAX_RETRIES attempts. Prevents silent intelligence loss from transient
LLM errors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _obs(retry_count: int = 0) -> dict:
    return {
        "id": MagicMock(__str__=lambda s: "observation:abc"),
        "content": "test observation",
        "observation_type": "pattern",
        "domain_path": "testing",
        "confidence": 0.7,
        "product": MagicMock(__str__=lambda s: "product:platform"),
        "retry_count": retry_count,
    }


class _FakeConn:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *a):
        pass


@pytest.mark.asyncio
async def test_first_failure_stays_pending_increments_retry_count():
    """First synth failure: observation must stay pending, retry_count → 1, NOT failed."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = _FakeConn(mock_db)
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.flush = AsyncMock(side_effect=RuntimeError("transient LLM error"))
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(_obs(retry_count=0))

    calls = [str(c) for c in mock_db.query.call_args_list]
    # must NOT mark failed on first failure
    assert not any("status = 'failed'" in c for c in calls), "First failure must not mark as 'failed'"
    # must increment retry_count
    assert any("retry_count" in c for c in calls), "Must update retry_count field"


@pytest.mark.asyncio
async def test_nth_failure_below_max_stays_pending():
    """Failures 1..MAX-1 keep observation pending for retry."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = _FakeConn(mock_db)
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.flush = AsyncMock(side_effect=RuntimeError("blip"))
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(_obs(retry_count=1))

    calls = [str(c) for c in mock_db.query.call_args_list]
    assert not any("status = 'failed'" in c for c in calls)


@pytest.mark.asyncio
async def test_failure_at_max_retries_marks_failed():
    """When retry_count reaches MAX_RETRIES-1 and fails again, marks 'failed'."""
    from core.engine.worker.processor import MAX_RETRIES

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = _FakeConn(mock_db)
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.flush = AsyncMock(side_effect=RuntimeError("permanent"))
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(_obs(retry_count=MAX_RETRIES - 1))

    calls = [str(c) for c in mock_db.query.call_args_list]
    assert any("status = 'failed'" in c for c in calls), "Must mark failed once retry budget exhausted"


@pytest.mark.asyncio
async def test_successful_process_ignores_retry_count():
    """Successful synthesis marks 'processed' regardless of retry_count."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = _FakeConn(mock_db)
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.flush = AsyncMock()
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(_obs(retry_count=2))

    calls = [str(c) for c in mock_db.query.call_args_list]
    assert any("status = 'processed'" in c for c in calls)


@pytest.mark.asyncio
async def test_max_retries_constant_is_at_least_3():
    """The budget must be enough to survive transient errors."""
    from core.engine.worker.processor import MAX_RETRIES

    assert MAX_RETRIES >= 3


@pytest.mark.asyncio
async def test_fetch_pending_still_picks_up_observations_with_retries():
    """Sentinel boundary check: after 1st failure, fetch_pending MUST still include the obs.

    If the SQL query were `status = 'pending' AND retry_count = 0` this would regress.
    The retry budget is only useful if the poll loop keeps picking up retry-eligible rows.
    """
    captured_sql: list[str] = []

    async def fake_query(sql, params=None):
        captured_sql.append(sql)
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = _FakeConn(mock_db)
        from core.engine.worker.processor import fetch_pending

        await fetch_pending("product:test")

    assert any("status = 'pending'" in s for s in captured_sql)
    # must NOT filter out partially-failed rows by retry_count
    assert not any("retry_count = 0" in s for s in captured_sql), (
        "fetch_pending must not exclude rows with retry_count > 0"
    )
