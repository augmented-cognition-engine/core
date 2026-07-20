# tests/test_orchestration_ws_handler.py
"""A.7 — Orchestration WebSocket: connect, hello frame, route registration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI


def make_app():
    from core.engine.api.orchestration_ws import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_hello_sent_on_connect(monkeypatch):
    """On connect, server sends a 'hello' frame with session_id."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(
        return_value=[[{"id": "canvas_session:s1", "project_id": "product:p1", "title": "test"}]]
    )
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    sent_messages = []

    class FakeWS:
        async def accept(self):
            pass

        async def send_json(self, data):
            sent_messages.append(data)

        async def receive_json(self):
            raise Exception("disconnect")

        async def close(self):
            pass

    with patch("core.engine.api.orchestration_ws.default_pool", mock_pool):
        from core.engine.api.orchestration_ws import _handle_connection

        ws = FakeWS()
        try:
            await _handle_connection(ws, "canvas_session:s1")
        except Exception:
            pass

    assert len(sent_messages) >= 1
    assert sent_messages[0]["type"] == "hello"
    assert sent_messages[0]["session_id"] == "canvas_session:s1"


def test_orchestration_ws_route_registered():
    """The /canvas/sessions/{id}/orchestration WebSocket route must exist."""
    from core.engine.api.orchestration_ws import router

    routes = [r.path for r in router.routes]
    assert any("orchestration" in r for r in routes)


def test_route_path_matches_spec():
    """Route path must be /canvas/sessions/{session_id}/orchestration."""
    from core.engine.api.orchestration_ws import router

    paths = [r.path for r in router.routes]
    assert any("/canvas/sessions/" in p and "orchestration" in p for p in paths)


@pytest.mark.asyncio
async def test_handle_user_message_sets_active_bus(monkeypatch):
    """Active bus is set in context for the duration of render_via_orchestration."""
    from core.engine.api import orchestration_ws
    from core.engine.orchestration import context as ctx

    captured_bus = {}

    async def fake_render(**kwargs):
        captured_bus["bus"] = ctx.get_active_bus()
        return None

    async def fake_save_message(**kwargs):
        return "msg_id"

    async def fake_save_turn(**kwargs):
        return "turn_id"

    monkeypatch.setattr("core.engine.canvas.conversation.save_message", fake_save_message)
    monkeypatch.setattr("core.engine.canvas.conversation.save_turn", fake_save_turn)
    monkeypatch.setattr("core.engine.canvas.orchestrated_renderer.render_via_orchestration", fake_render)

    class FakeWS:
        sent = []

        async def send_json(self, data):
            self.sent.append(data)

    ws = FakeWS()
    await orchestration_ws._handle_user_message(
        ws, session_id="sess_1", product_id="product:test", data={"content": "hello"}
    )

    assert captured_bus.get("bus") is not None
    # Context must be reset after the call completes
    assert ctx.get_active_bus() is None
