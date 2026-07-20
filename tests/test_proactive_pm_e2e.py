"""End-to-end test: session compression → briefing → Discord notification."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_compression_to_briefing_to_discord_pipeline():
    """Verify the full pipeline routes correctly."""
    from core.engine.events.automations import on_briefing_generated

    dispatched = []

    async def mock_dispatch(**kwargs):
        dispatched.append(kwargs)
        return {"id": "notif:test", **kwargs}

    with patch("core.engine.notifications.dispatcher.dispatch", side_effect=mock_dispatch):
        await on_briefing_generated(
            "briefing.generated",
            {
                "product_id": "product:default",
                "briefing_id": "briefing:test",
                "period": "2026-03-31",
                "summary": "2 sessions compressed, 1 security gap found",
            },
        )

    assert len(dispatched) == 1
    assert dispatched[0]["tier"] == "actionable"
    assert dispatched[0]["category"] == "briefing"
    assert "2026-03-31" in dispatched[0]["title"]


@pytest.mark.asyncio
async def test_session_digest_event_emitted():
    """session_compressor should emit session_digest.created when sessions exist."""
    from core.engine.events.bus import bus

    events_received = []

    async def capture_event(event_type, payload):
        events_received.append((event_type, payload))

    bus.on("session_digest.created", capture_event)

    try:
        task_rows = [
            {
                "session_id": "sess-e2e",
                "description": "Test",
                "domain_path": "testing",
                "status": "completed",
                "created_at": "2026-03-31T10:00:00Z",
            }
        ]
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [task_rows],  # tasks
                [[]],  # observations
                [[]],  # orchestration_runs
                [[]],  # decisions
                [[{"id": "session_digest:e2e"}]],  # CREATE digest
            ]
        )

        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(
            return_value={
                "summary": "Test session",
                "decisions": [],
                "blockers": [],
                "outcomes": [],
                "quality_signals": {},
            }
        )

        with (
            patch("core.engine.sentinel.engines.session_compressor.pool") as mock_pool,
            patch("core.engine.sentinel.engines.session_compressor.get_llm", return_value=mock_llm),
        ):
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            from core.engine.sentinel.engines.session_compressor import run_session_compressor

            await run_session_compressor("product:default")

        # Give background task time to run (bus.emit uses asyncio.create_task)
        await asyncio.sleep(0.1)

        assert len(events_received) == 1
        assert events_received[0][0] == "session_digest.created"
    finally:
        bus.off("session_digest.created", capture_event)
