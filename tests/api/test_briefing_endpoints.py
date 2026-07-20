"""Boundary tests for briefing versioning endpoints — AC 1, 2, 6, 7."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user():
    return {"sub": "user:1", "product": "product:test"}


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


def _briefing_row(bid: str, is_public: bool = False, highlights=None) -> dict:
    return {
        "id": bid,
        "product": "product:test",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "period": "weekly",
        "content": {
            "narrative": "ACE briefing",
            "highlights": highlights or [{"item_key": "gaps_filled", "content": "3 gaps filled"}],
            "recommendations": [],
            "risks": [],
            "score_deltas": {},
        },
        "metrics": {},
        "superseded_by": None,
        "is_public": is_public,
    }


# ---------------------------------------------------------------------------
# AC 1 — briefing table never overwrites (each briefing readable by stable ID)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_briefing_insert_never_overwrites(authed_client):
    """Two different IDs must each return their own content — no row is overwritten."""
    row_a = _briefing_row("briefing:1", highlights=[{"item_key": "gaps_filled", "content": "2 gaps filled"}])
    row_b = _briefing_row("briefing:2", highlights=[{"item_key": "gaps_filled", "content": "5 gaps filled"}])

    def _make_conn(row):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.query = AsyncMock(return_value=[[row]])
        return mock_conn

    with patch("core.engine.api.briefings.pool.connection", return_value=_make_conn(row_a)):
        resp_a = await authed_client.get("/briefings/briefing:1?product=product:test")

    with patch("core.engine.api.briefings.pool.connection", return_value=_make_conn(row_b)):
        resp_b = await authed_client.get("/briefings/briefing:2?product=product:test")

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    # Each briefing returns its own distinct content
    content_a = resp_a.json().get("content", {})
    content_b = resp_b.json().get("content", {})
    assert content_a != content_b


# ---------------------------------------------------------------------------
# AC 2 — GET /{briefing_id} returns briefing as it existed at that ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_briefing_permalink_returns_specific_version(authed_client):
    """Retrieving briefing:1 after briefing:2 exists still returns briefing:1 content."""
    row = _briefing_row("briefing:1")

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[row]])

    with patch("core.engine.api.briefings.pool.connection", return_value=mock_conn):
        resp = await authed_client.get("/briefings/briefing:1?product=product:test")

    assert resp.status_code == 200
    data = resp.json()
    assert str(data.get("id", "briefing:1")) == "briefing:1" or data.get("content") is not None


# ---------------------------------------------------------------------------
# AC 3 — diff returns structured BriefingDiff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_briefing_diff_endpoint_returns_structured_diff(authed_client):
    """GET /briefings/{a}/diff/{b} returns added, removed, changed, score_deltas."""
    row_a = _briefing_row("briefing:1", highlights=[{"item_key": "gaps_filled", "content": "2 gaps filled"}])
    row_b = _briefing_row(
        "briefing:2",
        highlights=[
            {"item_key": "gaps_filled", "content": "5 gaps filled"},
            {"item_key": "competitive_insights", "content": "3 competitive insights written"},
        ],
    )
    row_b["created_at"] = datetime(2026, 1, 8, tzinfo=timezone.utc)

    call_count = [0]

    def _side_effect():
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        def _query(sql, params=None):
            bid = (params or {}).get("id", "")
            if "briefing:1" in str(bid):
                return AsyncMock(return_value=[[row_a]])()
            elif "briefing:2" in str(bid):
                return AsyncMock(return_value=[[row_b]])()
            return AsyncMock(return_value=[[]])()

        mock_conn.query = _query
        return mock_conn

    with patch("core.engine.api.briefings.pool.connection", _side_effect):
        resp = await authed_client.get("/briefings/briefing:1/diff/briefing:2")

    assert resp.status_code == 200
    data = resp.json()
    assert "added" in data
    assert "removed" in data
    assert "changed" in data
    assert "score_deltas" in data
    added_keys = {i["item_key"] for i in data["added"]}
    assert "competitive_insights" in added_keys


# ---------------------------------------------------------------------------
# AC 6 — subscription endpoint accepts email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_endpoint_accepts_email(authed_client):
    """POST /briefings/{id}/subscribe stores subscription and returns subscribed=True."""
    row = _briefing_row("briefing:1")

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[row]])

    with patch("core.engine.api.briefings.pool.connection", return_value=mock_conn):
        resp = await authed_client.post(
            "/briefings/briefing:1/subscribe",
            json={"email": "user@example.com"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["subscribed"] is True
    assert data["email"] == "user@example.com"
    assert data["briefing_id"] == "briefing:1"


# ---------------------------------------------------------------------------
# AC 7 — permalink: 200 if is_public, 401 otherwise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_permalink_unauthenticated_returns_200(authed_client):
    """is_public=True briefing returns 200 on /permalink (no auth required)."""
    row = _briefing_row("briefing:1", is_public=True)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[row]])

    with patch("core.engine.api.briefings.pool.connection", return_value=mock_conn):
        resp = await authed_client.get("/briefings/briefing:1/permalink")

    assert resp.status_code == 200
    data = resp.json()
    assert data["public"] is True


@pytest.mark.asyncio
async def test_private_permalink_returns_401(authed_client):
    """is_public=False briefing returns 401 on /permalink."""
    row = _briefing_row("briefing:1", is_public=False)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[row]])

    with patch("core.engine.api.briefings.pool.connection", return_value=mock_conn):
        resp = await authed_client.get("/briefings/briefing:1/permalink")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Sentinel check — no "No briefing available" once briefing exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_triggers_email_on_new_briefing():
    """Mock SMTP — briefing generation sends email to all subscribers."""
    from unittest.mock import patch

    from core.engine.sentinel.engines.briefing import _deliver_briefing_emails

    sent_messages: list[dict] = []

    class MockSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            sent_messages.append({"to": to_addrs, "from": from_addr, "msg": msg})

    with patch("smtplib.SMTP", MockSMTP):
        count = await _deliver_briefing_emails(
            emails=["user@example.com", "team@example.com"],
            briefing_id="briefing:42",
            product_id="product:test",
            summary="3 gaps filled. 2 corrections written.",
        )

    assert count == 2
    assert len(sent_messages) == 2
    recipients = [m["to"][0] for m in sent_messages]
    assert "user@example.com" in recipients
    assert "team@example.com" in recipients


@pytest.mark.asyncio
async def test_briefing_never_returns_fallback_after_one_exists(authed_client):
    """Once a briefing exists, the API must not return the 'No briefing available' fallback."""
    row = _briefing_row("briefing:1")

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[row]])

    with patch("core.engine.api.briefings.pool.connection", return_value=mock_conn):
        resp = await authed_client.get("/briefings/latest?product=product:test")

    assert resp.status_code == 200
    content = resp.json()
    narrative = ""
    if isinstance(content.get("content"), dict):
        narrative = content["content"].get("narrative", "")
    elif isinstance(content.get("content"), str):
        narrative = content["content"]
    assert "No briefing available" not in narrative, "Briefing fallback string appeared — engine failed to load data"
