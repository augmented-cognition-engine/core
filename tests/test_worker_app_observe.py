# tests/test_worker_app_observe.py
"""Tests for POST /observe endpoint in the ACE Session Intelligence Worker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.worker.app import app


@pytest.mark.asyncio
async def test_observe_writes_observation():
    """POST /observe must write to observation table with status=pending."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=MagicMock())
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[{"id": "observation:test123"}]),
    ):
        mock_pool.connection.return_value = mock_ctx
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/observe",
                json={
                    "content": "Always use get_llm() not raw ClaudeProvider",
                    "type": "pattern",
                    "domain_path": "code_conventions",
                },
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    # Sentinel: DB write must have been called — not a silent no-op
    mock_db.query.assert_called_once()
    call_sql = mock_db.query.call_args[0][0]
    assert "CREATE observation SET" in call_sql
    assert "status = 'pending'" in call_sql
    assert "discipline_hint" in call_sql


@pytest.mark.asyncio
async def test_observe_rejects_empty_content():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/observe", json={"content": ""})
    # Handler returns {"error": "content required"} with status 200
    assert resp.status_code == 200
    assert resp.json().get("error")


@pytest.mark.asyncio
async def test_live_observe_loop_calls_run_poll_cycle():
    """Sentinel: _live_observe_loop must call run_poll_cycle(PRODUCT_ID) on connect (drain step).

    Architecture changed from polling to SurrealDB LIVE SELECT + drain.
    run_poll_cycle is called once per connect to fill any gap during downtime.
    """
    import asyncio as _asyncio

    from core.engine.worker.app import PRODUCT_ID, _live_observe_loop

    called_with: list[str] = []
    first_call = _asyncio.Event()

    async def fake_run_poll_cycle(product_id: str) -> int:
        called_with.append(product_id)
        first_call.set()
        return 1

    # Blocking async generator so we can cancel after drain fires
    async def _blocking_sub():
        await _asyncio.sleep(100)
        if False:
            yield {}  # makes this an async generator

    mock_conn = AsyncMock()
    mock_conn.live.return_value = "test-live-uuid"
    mock_conn.subscribe_live.return_value = _blocking_sub()

    with (
        patch("surrealdb.AsyncSurreal", return_value=mock_conn),
        patch("core.engine.worker.processor.run_poll_cycle", fake_run_poll_cycle),
    ):
        task = _asyncio.create_task(_live_observe_loop())
        await _asyncio.wait_for(first_call.wait(), timeout=3.0)
        task.cancel()
        try:
            await task
        except _asyncio.CancelledError:
            pass

    assert called_with, "run_poll_cycle was never called — drain step is a silent no-op"
    assert called_with[0] == PRODUCT_ID, f"wrong product_id: {called_with[0]!r}"


@pytest.mark.asyncio
async def test_observe_surfaces_db_error_string():
    """A failed CREATE must NOT be reported as queued.

    SurrealDB returns per-statement failures (e.g. a required-field violation)
    as an error *string* instead of raising; parse_rows() maps strings to [].
    The handler used to fall through and answer {"status": "queued", "id": ""}
    — a success response for a write that never happened. The error must be
    surfaced in the response and recorded in worker health state.
    """
    db_error = "Found NONE for field `workspace`, with record `observation:x`, but expected a record<workspace>"
    mock_db = AsyncMock()
    # Real parse_rows runs against this string — no patch, exercises the actual mapping.
    mock_db.query = AsyncMock(return_value=db_error)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.return_value = mock_ctx
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/observe", json={"content": "something happened"})

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") != "queued", "failed write must not be reported as queued"
    assert "workspace" in data.get("error", ""), f"DB error not surfaced: {data}"

    from core.engine.worker.health import get_health_state

    assert "workspace" in (get_health_state().last_error or ""), "DB error not recorded in health state"


@pytest.mark.asyncio
async def test_observe_rejects_oversized_content():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/observe", json={"content": "x" * 11_000})
    # Handler returns {"error": "content exceeds..."} with status 200
    assert resp.status_code == 200
    assert resp.json().get("error")
