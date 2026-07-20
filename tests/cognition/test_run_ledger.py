# tests/cognition/test_run_ledger.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition import run_ledger


def _mock_hung_pool(captured=None):
    """A pool whose db.query never completes — simulates a live-but-unresponsive DB connection.
    Records the SQL of each attempted query into `captured` if provided."""
    db = MagicMock()

    async def _hang(sql, params=None):
        if captured is not None:
            captured.append(sql)
        await asyncio.sleep(30)  # never returns within any sane timeout

    db.query = AsyncMock(side_effect=_hang)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


def _mock_pool_update_ok_events_hang(captured):
    """A pool where the UPDATE write succeeds fast but every reasoning_event write hangs — exercises
    the finalize_run break-on-None path (a DB that goes unresponsive mid event-emission)."""
    db = MagicMock()

    async def _query(sql, params=None):
        captured.append(sql)
        if "UPDATE" in sql:
            return []  # primary run-row write succeeds → wrote=True → enter the event loop
        await asyncio.sleep(30)  # every reasoning_event write hangs

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


def _mock_pool(query_return, captured=None):
    """Build a mock db pool whose connection() is an async context manager.
    Records (sql, params) into `captured` if provided."""
    db = MagicMock()

    async def _query(sql, params=None):
        if captured is not None:
            captured.append((sql, params))
        return query_return

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


@pytest.mark.integration
async def test_create_run_returns_record_id_on_success():
    captured = []
    pool = _mock_pool([{"id": "reasoning_run:abc"}], captured)
    with patch("core.engine.core.db.pool", pool):
        run_id = await run_ledger.create_run(
            product_id="product:platform",
            thought="Should we open-source the kernel?",
            meta_skills=["strategic_intelligence"],
            depth=3,
            discipline="strategy",
        )
    assert run_id == "reasoning_run:abc"
    # The Task Ledger fields must be in the write params.
    _, params = captured[0]
    assert params["thought"] == "Should we open-source the kernel?"
    assert params["meta_skills"] == ["strategic_intelligence"]
    assert params["depth"] == 3


@pytest.mark.integration
async def test_create_run_returns_none_on_db_failure():
    pool = MagicMock()
    pool.connection.side_effect = Exception("DB unreachable")
    with patch("core.engine.core.db.pool", pool):
        run_id = await run_ledger.create_run(
            product_id="product:platform",
            thought="x",
            meta_skills=[],
            depth=1,
            discipline=None,
        )
    assert run_id is None  # failure is non-fatal — caller proceeds with None


@pytest.mark.integration
async def test_finalize_run_writes_phases_and_trace():
    captured = []
    pool = _mock_pool([], captured)
    with patch("core.engine.core.db.pool", pool):
        await run_ledger.finalize_run(
            run_id="reasoning_run:abc",
            conclusion="open-source it",
            phases=[{"cognitive_function": "frame", "output": "o", "confidence": 0.8}],
            trace=[{"phase_idx": 0, "confidence": 0.8, "tainted": False}],
            status="complete",
        )
    assert captured, "expected an UPDATE write"
    _, params = captured[0]
    assert params["conclusion"] == "open-source it"
    assert params["phases"][0]["cognitive_function"] == "frame"
    assert params["trace"][0]["phase_idx"] == 0
    assert params["status"] == "complete"


@pytest.mark.integration
async def test_finalize_run_is_noop_when_run_id_is_none():
    pool = _mock_pool([], [])
    with patch("core.engine.core.db.pool", pool):
        await run_ledger.finalize_run(run_id=None, conclusion="x", phases=[], trace=[], status="complete")
    pool.connection.assert_not_called()  # nothing to update — skip the DB entirely


@pytest.mark.integration
async def test_finalize_run_never_raises_on_db_failure():
    pool = MagicMock()
    pool.connection.side_effect = Exception("DB down")
    with patch("core.engine.core.db.pool", pool):
        # Must return normally despite the DB error.
        await run_ledger.finalize_run(
            run_id="reasoning_run:abc", conclusion="x", phases=[], trace=[], status="complete"
        )


@pytest.mark.integration
async def test_get_recent_runs_returns_rows_for_product():
    captured = []
    rows = [{"id": "reasoning_run:abc", "thought": "t", "depth": 3, "status": "complete"}]
    pool = _mock_pool(rows, captured)
    with (
        patch("core.engine.core.db.pool", pool),
        patch("core.engine.core.db.parse_rows", return_value=rows),
    ):
        out = await run_ledger.get_recent_runs(product_id="product:platform", limit=5)
    assert out == rows
    _, params = captured[0]
    assert params["product"] == "product:platform"
    assert params["lim"] == 5


@pytest.mark.integration
async def test_get_recent_runs_returns_empty_on_failure():
    pool = MagicMock()
    pool.connection.side_effect = Exception("DB down")
    with patch("core.engine.core.db.pool", pool):
        out = await run_ledger.get_recent_runs(product_id="product:platform", limit=5)
    assert out == []


@pytest.mark.integration
async def test_create_run_times_out_on_hung_query():
    """A DB write that hangs must not block the reasoning hot path. wait_for cancels the hung query
    and create_run degrades fail-safe (returns None) within the timeout ceiling, not the 30s hang."""
    pool = _mock_hung_pool()
    loop = asyncio.get_event_loop()
    with patch("core.engine.core.db.pool", pool), patch.object(run_ledger, "_DB_TIMEOUT_S", 0.05):
        start = loop.time()
        run_id = await run_ledger.create_run(
            product_id="product:platform", thought="x", meta_skills=[], depth=1, discipline=None
        )
        elapsed = loop.time() - start
    assert run_id is None  # hung write degrades fail-safe — caller proceeds with None
    assert elapsed < 5.0  # bounded by the timeout ceiling, not the 30s hang


@pytest.mark.integration
async def test_finalize_run_times_out_on_hung_query():
    """A hung finalize UPDATE must not block either — finalize_run returns normally (no raise)."""
    pool = _mock_hung_pool()
    loop = asyncio.get_event_loop()
    with patch("core.engine.core.db.pool", pool), patch.object(run_ledger, "_DB_TIMEOUT_S", 0.05):
        start = loop.time()
        await run_ledger.finalize_run(
            run_id="reasoning_run:abc", conclusion="x", phases=[], trace=[], status="complete"
        )
        elapsed = loop.time() - start
    assert elapsed < 5.0  # bounded by the timeout, not the hang


@pytest.mark.integration
async def test_finalize_run_skips_events_when_update_hangs():
    """When the primary UPDATE hangs, finalize must NOT attempt the event mirror (the wrote=False
    short-circuit) — otherwise a DB hang multiplies the block by (1 + n_phases + 1) timeouts."""
    captured = []
    pool = _mock_hung_pool(captured)
    with patch("core.engine.core.db.pool", pool), patch.object(run_ledger, "_DB_TIMEOUT_S", 0.05):
        await run_ledger.finalize_run(
            run_id="reasoning_run:abc",
            conclusion="x",
            phases=[{"phase_name": "a", "output": "o"}, {"phase_name": "b", "output": "o"}],
            trace=[],
            status="complete",
        )
    # Only the UPDATE was attempted; the hung UPDATE → wrote=False → zero reasoning_event writes.
    assert sum("UPDATE" in s for s in captured) == 1
    assert sum("reasoning_event" in s for s in captured) == 0


@pytest.mark.integration
async def test_finalize_run_breaks_event_loop_on_hung_event_write():
    """UPDATE succeeds but the event mirror goes unresponsive mid-sequence — finalize must break
    after the FIRST hung event (break-on-None), not attempt all N phases + the terminal event."""
    captured = []
    pool = _mock_pool_update_ok_events_hang(captured)
    loop = asyncio.get_event_loop()
    with patch("core.engine.core.db.pool", pool), patch.object(run_ledger, "_DB_TIMEOUT_S", 0.05):
        start = loop.time()
        await run_ledger.finalize_run(
            run_id="reasoning_run:abc",
            conclusion="x",
            phases=[
                {"phase_name": "a", "output": "o"},
                {"phase_name": "b", "output": "o"},
                {"phase_name": "c", "output": "o"},
            ],
            trace=[],
            status="complete",
        )
        elapsed = loop.time() - start
    # UPDATE (1) + exactly ONE event write attempted, then break — NOT all 3 phases + terminal (4).
    assert sum("UPDATE" in s for s in captured) == 1
    assert sum("reasoning_event" in s for s in captured) == 1
    assert elapsed < 1.0  # ~1 timeout (0.05s), not 4× timeout
