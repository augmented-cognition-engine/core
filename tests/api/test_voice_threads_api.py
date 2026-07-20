"""Tests for GET /portal/voice-threads/{product_id}.

Auth pattern matches tests/api/test_briefing_endpoints.py:
- httpx.AsyncClient + ASGITransport (NOT FastAPI TestClient)
- app.dependency_overrides[get_current_user] = lambda: mock_user
- Bearer tokens in headers do NOT validate; the override is what authenticates.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.core.db import pool
from core.engine.voice.feature_flag import set_partner_panel_enabled
from core.engine.voice.thread import _ensure_thread, apply_snooze

pytestmark = pytest.mark.usefixtures("db_pool")


async def _delete_thread(pid: str, topic: str) -> None:
    """Delete any existing voice_thread row for pid+topic to guarantee a clean slate."""
    async with pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )


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


@pytest.mark.asyncio
async def test_returns_404_when_flag_off(authed_client):
    pid = "product:test_voice_threads_flag_off"
    await set_partner_panel_enabled(pool, pid, False)
    resp = await authed_client.get(f"/portal/voice-threads/{pid}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_returns_threads_when_flag_on(authed_client):
    pid = "product:test_voice_threads_basic"
    await _delete_thread(pid, "ux")
    await _delete_thread(pid, "ai")
    await set_partner_panel_enabled(pool, pid, True)
    await _ensure_thread(pid, "ux", "canvas.score.changed")
    await _ensure_thread(pid, "ai", "canvas.score.changed")

    resp = await authed_client.get(f"/portal/voice-threads/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "threads" in data
    assert len(data["threads"]) >= 2
    topics = [t["topic"] for t in data["threads"]]
    assert "ux" in topics


@pytest.mark.asyncio
async def test_filters_snoozed_threads(authed_client):
    pid = "product:test_voice_threads_snooze_filter"
    await _delete_thread(pid, "qa")
    await _delete_thread(pid, "ops")
    await set_partner_panel_enabled(pool, pid, True)
    open_t = await _ensure_thread(pid, "qa", "canvas.score.changed")
    snoozed_t = await _ensure_thread(pid, "ops", "canvas.score.changed")
    await apply_snooze(snoozed_t.id, datetime.now(timezone.utc) + timedelta(days=7))

    resp = await authed_client.get(f"/portal/voice-threads/{pid}")
    topics = [t["topic"] for t in resp.json()["threads"]]
    assert "qa" in topics
    assert "ops" not in topics
