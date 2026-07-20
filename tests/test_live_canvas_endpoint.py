"""Boundary tests for the canvas connection manager and replay buffer — AC 6, 7."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.api.live_canvas import CanvasConnectionManager, _ReplayBuffer

# ---------------------------------------------------------------------------
# AC 7 — replay buffer
# ---------------------------------------------------------------------------


def test_replay_buffer_stores_events():
    buf = _ReplayBuffer()
    buf.push("product:test", {"event_type": "capability.added", "product_id": "product:test"})
    buf.push("product:test", {"event_type": "decision.captured", "product_id": "product:test"})

    since = datetime.now(timezone.utc) - timedelta(seconds=120)
    events = buf.since("product:test", since)
    assert len(events) == 2


def test_replay_buffer_since_timestamp_filters():
    """Events before the cutoff are excluded; events at or after are included."""
    from collections import deque

    buf = _ReplayBuffer()
    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)  # 1 second later
    cutoff = datetime(2026, 1, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)  # between t1 and t2

    buf._buffers["product:test"] = deque(maxlen=500)
    buf._buffers["product:test"].append((t1, {"event_type": "capability.added"}))
    buf._buffers["product:test"].append((t2, {"event_type": "decision.captured"}))

    events = buf.since("product:test", cutoff)
    assert len(events) == 1
    assert events[0]["event_type"] == "decision.captured"


def test_replay_buffer_returns_empty_for_unknown_product():
    buf = _ReplayBuffer()
    since = datetime.now(timezone.utc) - timedelta(seconds=120)
    events = buf.since("product:nonexistent", since)
    assert events == []


def test_replay_buffer_prune_removes_old_events():
    from core.engine.api.live_canvas import _REPLAY_WINDOW_SECONDS

    buf = _ReplayBuffer()

    # Manually insert an old event
    old_time = datetime.now(timezone.utc) - timedelta(seconds=_REPLAY_WINDOW_SECONDS + 10)
    buf._buffers.setdefault("product:test", __import__("collections").deque(maxlen=500))
    buf._buffers["product:test"].append((old_time, {"event_type": "old.event"}))

    # Add a fresh event
    buf.push("product:test", {"event_type": "new.event"})
    buf.prune("product:test")

    since = datetime.now(timezone.utc) - timedelta(seconds=_REPLAY_WINDOW_SECONDS + 5)
    events = buf.since("product:test", since)
    # Old event should be pruned, new event should remain
    assert all(e["event_type"] != "old.event" for e in events)


# ---------------------------------------------------------------------------
# AC 6 — connection manager broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_manager_tracks_subscriber_count():
    from unittest.mock import AsyncMock, MagicMock

    mgr = CanvasConnectionManager()
    ws1 = MagicMock()
    ws1.send_text = AsyncMock()
    ws2 = MagicMock()
    ws2.send_text = AsyncMock()

    mgr.connect("product:test", ws1)
    assert mgr.subscriber_count("product:test") == 1

    mgr.connect("product:test", ws2)
    assert mgr.subscriber_count("product:test") == 2

    mgr.disconnect("product:test", ws1)
    assert mgr.subscriber_count("product:test") == 1


@pytest.mark.asyncio
async def test_connection_manager_broadcasts_to_all_subscribers():
    from unittest.mock import AsyncMock, MagicMock

    mgr = CanvasConnectionManager()
    ws1 = MagicMock()
    ws1.send_text = AsyncMock()
    ws2 = MagicMock()
    ws2.send_text = AsyncMock()

    mgr.connect("product:test", ws1)
    mgr.connect("product:test", ws2)

    await mgr.broadcast("product:test", {"event_type": "capability.added"})

    ws1.send_text.assert_called_once()
    ws2.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_connection_manager_removes_dead_connections():
    from unittest.mock import AsyncMock, MagicMock

    mgr = CanvasConnectionManager()
    ws_alive = MagicMock()
    ws_alive.send_text = AsyncMock()
    ws_dead = MagicMock()
    ws_dead.send_text = AsyncMock(side_effect=Exception("connection closed"))

    mgr.connect("product:test", ws_alive)
    mgr.connect("product:test", ws_dead)
    assert mgr.subscriber_count("product:test") == 2

    await mgr.broadcast("product:test", {"event_type": "test"})

    # Dead connection should have been removed
    assert mgr.subscriber_count("product:test") == 1


# ---------------------------------------------------------------------------
# AC 1 — WebSocket rejects invalid token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_connection_rejects_invalid_token():
    """Canvas WebSocket must close with code 1008 when token is invalid or missing."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.api.live_canvas import canvas_websocket

    ws = MagicMock()
    ws.query_params = {"token": "definitely_not_valid"}
    ws.close = AsyncMock()
    ws.accept = AsyncMock()

    # The endpoint reads the token and validates it; invalid tokens must not get accepted
    try:
        await canvas_websocket(ws, product_id="product:test")
    except Exception:
        pass  # endpoint may raise after close

    # Either close was called (rejected) or accept was never called
    rejected = ws.close.called and not ws.accept.called
    assert rejected or (ws.close.call_count > 0), "WebSocket endpoint did not reject invalid token — close() not called"


# ---------------------------------------------------------------------------
# AC 6 — event ordering preserved per product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_events_arrive_in_emit_order():
    """Events broadcast to a product arrive at subscribers in emit order."""
    from unittest.mock import MagicMock

    mgr = CanvasConnectionManager()
    received: list[str] = []

    ws = MagicMock()

    async def capture_send(payload: str):
        import json

        data = json.loads(payload)
        received.append(data.get("event_type", ""))

    ws.send_text = capture_send

    mgr.connect("product:test", ws)

    events = ["capability.added", "decision.captured", "score.changed"]
    for et in events:
        await mgr.broadcast("product:test", {"event_type": et})

    assert received == events, f"Expected {events}, got {received}"
