"""Tests for the harness context builder and worker endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.worker.harness import (
    _format_greeting,
    _format_status_pulse,
    build_harness_context,
)
from core.engine.worker.models import HarnessContext


def test_harness_context_fields_present():
    ctx = HarnessContext(
        session_id="test-session",
        product_id="product:platform",
        greeting="we picked up where we left off — auth is still our open thread.",
        status_pulse="watching: authentication · 2 ideas ready",
        proactive_line="we noticed the OAuth callback path is untested",
        proactive_drill_down="/capabilities/auth?dimension=testing",
        recent_decisions=[{"title": "use OS keychain for token storage", "date": "2026-04-27"}],
        generated_at="2026-04-27T10:00:00Z",
    )
    assert ctx.greeting.startswith("we")
    assert "watching" in ctx.status_pulse
    assert ctx.proactive_line is not None


def test_harness_context_optional_fields_nullable():
    ctx = HarnessContext(
        session_id="s",
        greeting="we resumed — no open threads.",
        status_pulse="watching: general · 0 ideas ready",
    )
    assert ctx.proactive_line is None
    assert ctx.proactive_drill_down is None
    assert ctx.recent_decisions == []
    assert ctx.generated_at == ""


def test_harness_context_default_product_id():
    ctx = HarnessContext(
        session_id="s",
        greeting="we resumed.",
        status_pulse="watching: general · 0 ideas ready",
    )
    assert ctx.product_id == "product:platform"


# --- Task 2: builder tests ---


def test_format_greeting_uses_we_pronoun():
    g = _format_greeting(
        discipline="authentication",
        summary="working on the OAuth callback path",
        open_thread="OAuth callback gap is still unresolved",
        n_ideas=2,
    )
    assert g.lower().startswith("we"), f"Greeting must start with 'we': {g!r}"
    assert len(g) <= 200, f"Greeting must be ≤200 chars: {len(g)}"


def test_format_greeting_no_forbidden_strings():
    from core.engine.proactive.voice import FORBIDDEN_TONE_STRINGS

    g = _format_greeting("testing", "adding coverage", None, 0)
    for forbidden in FORBIDDEN_TONE_STRINGS:
        assert forbidden not in g, f"Forbidden string {forbidden!r} in greeting: {g!r}"


def test_format_greeting_open_thread_dominates():
    g = _format_greeting("security", "some summary", "auth regression is open", 5)
    assert "auth regression" in g


def test_format_status_pulse_includes_discipline():
    p = _format_status_pulse("authentication", 3, 1)
    assert "authentication" in p
    assert "watching" in p


def test_format_status_pulse_no_ideas_still_valid():
    p = _format_status_pulse("testing", 0, 0)
    assert "watching: testing" in p


@pytest.mark.asyncio
async def test_build_harness_context_graceful_on_db_failure():
    """build_harness_context must never raise — degraded fallback is acceptable."""
    with patch("core.engine.worker.harness._get_session_state", AsyncMock(side_effect=Exception("db down"))):
        ctx = await build_harness_context("session-x", "product:platform")
    assert ctx.greeting
    assert "watching" in ctx.status_pulse


# --- Task 3: endpoint tests ---


@pytest.mark.asyncio
async def test_harness_context_endpoint_returns_200():
    from datetime import datetime, timezone

    from httpx import ASGITransport, AsyncClient

    from core.engine.worker.app import app

    mock_ctx = HarnessContext(
        session_id="test-session",
        product_id="product:platform",
        greeting="we picked up where we left off — auth gap is open.",
        status_pulse="watching: authentication · 1 idea ready",
        proactive_line="we noticed the OAuth callback path is untested",
        proactive_drill_down="/capabilities/auth",
        recent_decisions=[],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    with patch("core.engine.worker.harness.build_harness_context", AsyncMock(return_value=mock_ctx)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/harness/context", params={"session_id": "test-session"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"].startswith("we")
    assert "watching" in data["status_pulse"]
    assert data["proactive_line"] is not None


@pytest.mark.asyncio
async def test_harness_context_endpoint_requires_session_id():
    from httpx import ASGITransport, AsyncClient

    from core.engine.worker.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/harness/context")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_harness_context_includes_health_warning_when_stale():
    """HarnessContext.worker_health is set when pipeline is stale."""
    import time

    from core.engine.worker.health import WorkerHealthState

    stale_state = WorkerHealthState()
    stale_state.last_hook_post_at = time.time() - (35 * 60)  # 35 min ago

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.harness.get_health_state", return_value=stale_state),
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[]),
    ):
        mock_pool.connection.return_value = mock_ctx
        ctx = await build_harness_context("session-test", "product:platform")

    assert ctx.worker_health is not None
    assert "stale" in ctx.worker_health.lower() or "capture" in ctx.worker_health.lower()


@pytest.mark.asyncio
async def test_harness_context_no_health_warning_when_active():
    """HarnessContext.worker_health is None when pipeline is active."""
    import time

    from core.engine.worker.health import WorkerHealthState

    active_state = WorkerHealthState()
    active_state.last_hook_post_at = time.time() - 30  # 30 sec ago

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.worker.harness.get_health_state", return_value=active_state),
        patch("core.engine.core.db.pool") as mock_pool,
        patch("core.engine.core.db.parse_rows", return_value=[]),
    ):
        mock_pool.connection.return_value = mock_ctx
        ctx = await build_harness_context("session-test-2", "product:platform")

    assert ctx.worker_health is None
