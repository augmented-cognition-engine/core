# tests/test_worker_health.py
"""Tests for WorkerHealthState module."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.worker.app import app
from core.engine.worker.health import WorkerHealthState, get_health_state


def test_initial_state():
    state = WorkerHealthState()
    assert state.hook_post_count == 0
    assert state.capture_count == 0
    assert state.last_hook_post_at is None
    assert state.last_synthesis_at is None
    assert state.last_error is None
    assert state.worker_start_time > 0
    assert state.lease_claim_count == 0
    assert state.recovered_lease_count == 0
    assert state.lease_loss_count == 0
    assert state.leased_outcomes_last_5m == 0


def test_record_hook_post():
    state = WorkerHealthState()
    state.record_hook_post()
    state.record_hook_post()
    assert state.hook_post_count == 2
    assert state.last_hook_post_at is not None
    assert state.last_hook_post_at <= time.time()


def test_record_capture():
    state = WorkerHealthState()
    state.record_capture()
    state.record_capture()
    assert state.capture_count == 2


def test_record_synthesis():
    state = WorkerHealthState()
    state.record_synthesis()
    assert state.last_synthesis_at is not None


def test_idle_seconds_none_when_no_posts():
    state = WorkerHealthState()
    assert state.idle_seconds is None


def test_idle_seconds_returns_elapsed():
    state = WorkerHealthState()
    state.record_hook_post()
    assert state.idle_seconds is not None
    assert state.idle_seconds >= 0


def test_pipeline_status_active():
    state = WorkerHealthState()
    state.record_hook_post()
    assert state.pipeline_status == "active"


def test_pipeline_status_never_used():
    state = WorkerHealthState()
    assert state.pipeline_status == "never_used"


def test_pipeline_status_stale():
    state = WorkerHealthState()
    # Simulate a post from 35 minutes ago
    state.last_hook_post_at = time.time() - (35 * 60)
    assert state.pipeline_status == "stale"


def test_get_health_state_returns_singleton():
    s1 = get_health_state()
    s2 = get_health_state()
    assert s1 is s2


def test_worker_lease_and_drain_health_metrics():
    state = WorkerHealthState()
    state.record_lease_claim(recovered=False)
    state.record_lease_claim(recovered=True)
    state.record_lease_loss("expired fence")
    state.record_leased_outcome()
    state.record_drain_cycle()

    assert state.lease_claim_count == 2
    assert state.recovered_lease_count == 1
    assert state.lease_loss_count == 1
    assert state.last_lease_loss == "expired fence"
    assert state.leased_outcome_count == 1
    assert state.leased_outcomes_last_5m == 1
    assert state.leased_outcomes_per_minute == 0.2
    assert state.drain_cycle_count == 1
    assert state.last_drain_at is not None


def test_pipeline_status_idle():
    """pipeline_status returns 'idle' for activity between 60s and 30 min ago."""
    state = WorkerHealthState()
    state.last_hook_post_at = time.time() - 120  # 2 min ago
    assert state.pipeline_status == "idle"


@pytest.mark.asyncio
async def test_health_status_endpoint_returns_fields():
    with patch(
        "core.engine.capture.lifecycle.observation_outcome_health",
        new=AsyncMock(return_value={"status": "healthy"}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_status" in data
    assert "hook_post_count" in data
    assert "capture_count" in data
    assert "uptime_seconds" in data
    assert "worker_version" in data
    assert "lease_claim_count" in data
    assert "recovered_lease_count" in data
    assert "lease_loss_count" in data
    assert "leased_outcomes_per_minute" in data
    assert "drain_cycle_count" in data


@pytest.mark.asyncio
async def test_health_status_fails_closed_when_queue_visibility_is_unavailable():
    from core.engine.worker.health import WorkerHealthState

    fresh_state = WorkerHealthState()
    with (
        patch("core.engine.worker.app.get_health_state", return_value=fresh_state),
        patch(
            "core.engine.capture.lifecycle.observation_outcome_health",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health/status")
    data = resp.json()
    assert data["pipeline_status"] == "degraded"
    assert data["hook_post_count"] == 0
    assert data["observation_outcomes"]["status"] == "unavailable"
