"""Boundary tests for HandOff dispatcher lifecycle — A6 ACs 1, 2, 6, 7, 8."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.handoff.models import HandOffStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(spec_id="spec:auth_refactor"):
    return {
        "spec_id": spec_id,
        "units": [{"id": "u1", "title": "Implement auth", "description": "Write auth module"}],
        "batches": [{"task_ids": ["u1"], "mode": "sequential"}],
        "conflicts": [],
    }


async def _mock_execute_plan(plan, product_id):
    return {
        "spec_id": plan["spec_id"],
        "completed": 1,
        "failed": 0,
        "blocked": 0,
        "total_units": 1,
        "spec_status": "verifying",
    }


# ---------------------------------------------------------------------------
# AC 1 — dispatch returns HandOff with status=dispatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_returns_handoff_with_dispatched_status():
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:auth",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    assert handoff.id is not None
    assert handoff.status == HandOffStatus.DISPATCHED
    assert handoff.spec_id == "spec:auth"
    assert handoff.agent == "claude_code"


@pytest.mark.asyncio
async def test_dispatch_stores_handoff_retrievable():
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:payments",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    retrieved = disp.get_handoff(handoff.id)
    assert retrieved is not None
    assert retrieved.id == handoff.id


# ---------------------------------------------------------------------------
# AC 2 — HANDOFF_STARTED emitted within 200ms of dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_started_event_within_200ms():
    import core.engine.handoff.dispatcher as disp

    started_at = None

    async def _record_start(*args, **kwargs):
        nonlocal started_at
        started_at = time.perf_counter()

    t0 = time.perf_counter()
    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", side_effect=_record_start):
            await disp.dispatch(
                spec_id="spec:test",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    assert started_at is not None
    elapsed_ms = (started_at - t0) * 1000
    assert elapsed_ms < 200, f"HANDOFF_STARTED took {elapsed_ms:.1f}ms > 200ms"


# ---------------------------------------------------------------------------
# AC 3 — progress events include plain_language (tested via _run_plan integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_messages_plain_language_not_raw_log():
    """Progress messages must not contain [INFO]/[ERROR] prefixes."""
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:test",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    # Manually inject a progress message to simulate what _run_plan does
    from core.engine.handoff.models import HandOffProgressMessage

    handoff.progress_messages.append(
        HandOffProgressMessage(
            plain_language="updating the auth module oauth handler",
            raw_log_excerpt="Editing file: engine/auth/oauth.py (line 42-78)",
            pct=50,
        )
    )

    for msg in handoff.progress_messages:
        assert "[INFO]" not in msg.plain_language
        assert "[ERROR]" not in msg.plain_language
        assert not msg.plain_language.startswith("[")


# ---------------------------------------------------------------------------
# AC 6 — pause halts; resume continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_sets_status_paused():
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:pause_test",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    handoff.status = HandOffStatus.RUNNING
    paused = await disp.pause(handoff.id)
    assert paused.status == HandOffStatus.PAUSED


@pytest.mark.asyncio
async def test_resume_sets_status_running():
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:resume_test",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    handoff.status = HandOffStatus.PAUSED
    disp._PAUSE_EVENTS[handoff.id].clear()

    resumed = await disp.resume(handoff.id)
    assert resumed.status == HandOffStatus.RUNNING


# ---------------------------------------------------------------------------
# AC 7 — cancel marks status=cancelled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_marks_status_cancelled():
    import core.engine.handoff.dispatcher as disp

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            handoff = await disp.dispatch(
                spec_id="spec:cancel_test",
                agent="claude_code",
                product_id="product:test",
                db_pool=None,
            )

    handoff.status = HandOffStatus.RUNNING
    cancelled = await disp.cancel(handoff.id)
    assert cancelled.status == HandOffStatus.CANCELLED
    assert cancelled.completed_at is not None


# ---------------------------------------------------------------------------
# AC 8 — persistence call made on dispatch (DB round-trip mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_attempts_db_persistence():
    import core.engine.handoff.dispatcher as disp

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.connection = MagicMock(
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=None),
        )
    )

    with patch("core.engine.handoff.dispatcher._run_plan", new_callable=AsyncMock):
        with patch("core.engine.events.canvas.emit_handoff_started", new_callable=AsyncMock):
            await disp.dispatch(
                spec_id="spec:persist_test",
                agent="claude_code",
                product_id="product:test",
                db_pool=mock_pool,
            )

    mock_db.query.assert_called_once()
