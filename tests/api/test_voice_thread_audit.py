"""Tests for voice_thread_action audit log persistence + briefing_id on GET.

Uses the authed_client fixture pattern (httpx.AsyncClient + dependency_overrides).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.core.db import parse_rows, pool
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


# T4 idempotency lesson — DELETE before _ensure_thread
async def _delete_thread(pid: str, topic: str) -> None:
    async with pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )


@pytest.mark.asyncio
async def test_action_writes_audit_row(authed_client):
    pid = "product:test_audit_writes"
    await set_partner_panel_enabled(pool, pid, True)
    await _delete_thread(pid, "ux")
    thread = await _ensure_thread(pid, "ux", "canvas.score.changed")

    await authed_client.post(
        f"/portal/voice-threads/{thread.id}/action",
        json={"kind": "snooze", "snooze_days": 14, "note": "back from PTO next sprint"},
    )

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM voice_thread_action WHERE thread_id = <record>$tid",
                {"tid": thread.id},
            )
        )
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "snooze"
    assert row["note"] == "back from PTO next sprint"
    assert row["created_by"] is not None
    assert row["created_at"] is not None


@pytest.mark.asyncio
async def test_get_returns_latest_briefing_id(authed_client):
    pid = "product:test_audit_briefing_id"
    await set_partner_panel_enabled(pool, pid, True)

    async with pool.connection() as db:
        await db.query(
            """DELETE briefing WHERE product = <record>$pid""",
            {"pid": pid},
        )
        await db.query(
            """CREATE briefing CONTENT {
                product: <record>$pid,
                period: 'weekly',
                content: <string>$content,
                metrics: {}
            }""",
            {
                "pid": pid,
                "content": '{"narrative":"test","highlights":[],"recommendations":[],"risks":[],"score_deltas":[]}',
            },
        )

    resp = await authed_client.get(f"/portal/voice-threads/{pid}")
    assert resp.status_code == 200
    assert resp.json()["briefing_id"] is not None
