"""Tests for POST /portal/voice-threads/{thread_id}/action.

Uses the same authed_client fixture pattern as test_voice_threads_api.py
(httpx.AsyncClient + dependency_overrides[get_current_user]).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.core.db import pool
from core.engine.voice.feature_flag import set_partner_panel_enabled
from core.engine.voice.thread import _ensure_thread

pytestmark = pytest.mark.usefixtures("db_pool")


@pytest.fixture
def mock_user():
    return {"sub": "user:1", "email": "test@example.com"}


@pytest.fixture
async def authed_client(mock_user):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# Apply T4 idempotency lesson — DELETE before _ensure_thread
async def _delete_thread(pid: str, topic: str) -> None:
    async with pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )


@pytest.mark.asyncio
async def test_snooze_sets_timestamp(authed_client):
    pid = "product:test_action_snooze"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "ux")
    thread = await _ensure_thread(pid, "ux", "canvas.score.changed")

    resp = await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "snooze", "snooze_days": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["new_status"] == "open"
    assert "audit_id" in data
    assert data["audit_id"] != "", "audit_id must be non-empty (regression: isoformat datetime silently failed)"


@pytest.mark.asyncio
async def test_resolve_flips_status(authed_client):
    pid = "product:test_action_resolve"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "ai")
    thread = await _ensure_thread(pid, "ai", "canvas.score.changed")

    resp = await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "resolve"},
    )
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "resolved"
    assert resp.json()["audit_id"] != ""


@pytest.mark.asyncio
async def test_commit_emits_canvas_event(authed_client):
    pid = "product:test_action_commit"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "qa")
    thread = await _ensure_thread(pid, "qa", "canvas.score.changed")

    # Mirror the T2 bus pattern — patch the module-level bus to capture events.
    import core.engine.events.canvas as canvas_module
    from core.engine.events.bus import EventBus

    original_bus = canvas_module.bus
    test_bus = EventBus()
    canvas_module.bus = test_bus
    received = []

    def handler(event_type, payload):
        received.append(payload)

    test_bus.on("canvas.thread.committed", handler)
    try:
        resp = await authed_client.post(
            f"/portal/voice-threads/{thread.id}/action",
            json={"kind": "commit"},
        )
        assert resp.status_code == 200
        assert resp.json()["audit_id"] != ""
        # Allow any fire-and-forget tasks to drain
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0]["payload"]["thread_id"] == thread.id
    finally:
        canvas_module.bus = original_bus


@pytest.mark.asyncio
async def test_409_on_stale_resolve(authed_client):
    pid = "product:test_action_stale"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "api")
    thread = await _ensure_thread(pid, "api", "canvas.score.changed")

    await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "resolve"},
    )
    resp = await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "resolve", "expected_status": "open"},
    )
    assert resp.status_code == 409
    assert "thread_state_changed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_kind_returns_422(authed_client):
    pid = "product:test_action_invalid"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "ops")
    thread = await _ensure_thread(pid, "ops", "canvas.score.changed")

    resp = await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "yeet"},
    )
    assert resp.status_code == 422
