# tests/test_sentinel_api_schedule.py
"""Tests for sentinel schedule override API — display names, cron validation,
PUT /sentinel/schedule/{engine_name}."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Display names
# ---------------------------------------------------------------------------


def test_display_name_map_covers_all_registered_engines():
    """ENGINE_DISPLAY_NAMES and ENGINE_GROUPS each contain all 22 production engines.

    We verify the maps are complete and consistent with each other. We don't
    check against the live registry because the registry is mutated by other
    tests (clear() calls), making it unreliable for this coverage assertion.
    """
    from core.engine.api.sentinel import ENGINE_DISPLAY_NAMES, ENGINE_GROUPS

    # All 22 known production engine slugs
    expected_engines = {
        "evaluator_honesty",
        "simplicity_audit",
        "knowledge_verifier",
        "failure_analysis",
        "calibration",
        "gap_analyzer",
        "gap_researcher",
        "domain_research",
        "specialty_deepener",
        "seam_analyzer",
        "perspective_gap_detector",
        "adversarial_synthesis",
        "question_generator",
        "self_optimizer",
        "template_detector",
        "pm_optimizer",
        "ecosystem_scanner",
        "competitive_observer",
        "briefing_generator",
        "idea_incubator",
        "decay_manager",
        "conflict_detector",
    }

    missing_display = expected_engines - set(ENGINE_DISPLAY_NAMES.keys())
    assert missing_display == set(), f"Production engines missing from ENGINE_DISPLAY_NAMES: {missing_display}"

    missing_groups = expected_engines - set(ENGINE_GROUPS.keys())
    assert missing_groups == set(), f"Production engines missing from ENGINE_GROUPS: {missing_groups}"

    assert len(ENGINE_DISPLAY_NAMES) == 22, (
        f"ENGINE_DISPLAY_NAMES should have 22 entries, got {len(ENGINE_DISPLAY_NAMES)}"
    )
    assert len(ENGINE_GROUPS) == 22, f"ENGINE_GROUPS should have 22 entries, got {len(ENGINE_GROUPS)}"


# ---------------------------------------------------------------------------
# Cron validation
# ---------------------------------------------------------------------------


def test_cron_validation_rejects_every_minute():
    """_validate_cron rejects a cron that fires every minute (below 15-min minimum)."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("* * * * *")
    assert not valid
    assert "minimum" in reason.lower() or "interval" in reason.lower()


def test_cron_validation_accepts_daily_430am():
    """_validate_cron accepts daily 4:30 AM schedule."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("30 4 * * *")
    assert valid, f"Expected valid, got reason: {reason}"
    assert reason == ""


def test_cron_validation_rejects_invalid_syntax():
    """_validate_cron rejects nonsense cron expression."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("not a cron expr")
    assert not valid


def test_cron_validation_rejects_6_field_cron():
    """_validate_cron rejects a 6-field cron (seconds prefix)."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("0 0 4 * * *")
    assert not valid
    assert "5 fields" in reason


def test_cron_validation_accepts_hourly():
    """_validate_cron accepts hourly schedule (exactly 60-minute interval)."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("0 * * * *")
    assert valid, f"Expected valid, got reason: {reason}"


def test_cron_validation_rejects_every_5_minutes():
    """_validate_cron rejects every-5-minute schedule (below 15-min minimum)."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("*/5 * * * *")
    assert not valid


def test_cron_validation_accepts_every_15_minutes():
    """_validate_cron accepts exactly 15-minute interval."""
    from core.engine.api.sentinel import _validate_cron

    valid, reason = _validate_cron("*/15 * * * *")
    assert valid, f"Expected valid, got reason: {reason}"


# ---------------------------------------------------------------------------
# PUT /sentinel/schedule — HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """FastAPI test client with mocked lifespan."""
    from contextlib import asynccontextmanager

    from httpx import ASGITransport, AsyncClient

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: {"product": "product:test", "sub": "user:test"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_schedule_unknown_engine_returns_404(client):
    """PUT /sentinel/schedule/{engine} with unknown engine returns 404."""
    from core.engine.sentinel.registry import engine_registry

    engine_registry.clear()

    response = await client.put(
        "/sentinel/schedule/nonexistent",
        json={"cron": "0 4 * * *", "enabled": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_schedule_invalid_cron_returns_422(client):
    """PUT /sentinel/schedule/{engine} with invalid cron returns 422."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="put_test_eng", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    response = await client.put(
        "/sentinel/schedule/put_test_eng",
        json={"cron": "* * * * *"},  # too frequent
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_schedule_valid_returns_ok(client):
    """PUT /sentinel/schedule/{engine} with valid cron returns {status: ok}."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="put_valid_eng", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    mock_db = AsyncMock()
    # existing override read returns empty
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    mock_sched = MagicMock()
    mock_sched.running = True
    mock_sched.reschedule_engine = MagicMock()

    with patch("core.engine.api.sentinel.pool", mock_pool), patch("core.engine.api.sentinel._scheduler", mock_sched):
        response = await client.put(
            "/sentinel/schedule/put_valid_eng",
            json={"cron": "30 4 * * *", "enabled": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["engine"] == "put_valid_eng"
    assert body["cron"] == "30 4 * * *"
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_put_schedule_disable_calls_disable_engine(client):
    """PUT /sentinel/schedule with enabled=False calls disable_engine."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="put_disable_eng", cron="0 2 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    mock_sched = MagicMock()
    mock_sched.running = True
    mock_sched.disable_engine = MagicMock()

    with patch("core.engine.api.sentinel.pool", mock_pool), patch("core.engine.api.sentinel._scheduler", mock_sched):
        response = await client.put(
            "/sentinel/schedule/put_disable_eng",
            json={"enabled": False},
        )

    assert response.status_code == 200
    mock_sched.disable_engine.assert_called_once_with("put_disable_eng")
