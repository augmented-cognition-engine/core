"""Tests for initiative gate endpoints — decompose, start, review, complete."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user():
    return {"sub": "user:test", "product": "product:test"}


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[[]])
    return db


@pytest.fixture
def mock_pool(mock_db):
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    p.init = AsyncMock()
    p.close = AsyncMock()
    return p


@pytest.fixture
def app_with_mocks(mock_user, mock_pool, mock_db):
    """Create an app with mocked auth and DB."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    import core.engine.api.initiatives as init_mod

    original_pool = init_mod.pool
    init_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    init_mod.pool = original_pool


@pytest.mark.asyncio
@patch("core.engine.pm.tracker.InitiativeTracker.get_initiative")
async def test_decompose_initiative_from_planning(mock_get, app_with_mocks):
    """POST /initiatives/{id}/decompose transitions planning -> decomposing -> ready.

    Updated for the defensive-guard fix in engine/api/initiatives.py: an
    initiative MUST carry a spec_id (or source_spec) for decomposition to
    proceed. Previously the no-spec branch flipped status to ready with
    a placeholder plan_data {"note": "manual decomposition needed"} —
    same lazy fast-path bug class as the qualify→ready transition. The
    test now mocks a spec_id and stubs SmartDecomposer so a real LLM
    isn't called.
    """
    app, mock_db = app_with_mocks

    mock_get.return_value = {
        "id": "initiative:abc",
        "status": "planning",
        "spec_id": "agent_spec:fake",
        "milestones_detail": [],
        "progress": 0.0,
        "computed_status": "pending",
        "budget_status": {"status": "ok", "percentage": 0.0},
    }

    fake_plan = MagicMock()
    fake_plan.to_dict.return_value = {
        "spec_id": "agent_spec:fake",
        "units": [],
        "schedule": {"batches": [], "conflicts": []},
    }
    fake_decomposer = MagicMock()
    fake_decomposer.decompose = AsyncMock(return_value=fake_plan)

    with patch("core.engine.product.smart_decompose.SmartDecomposer", return_value=fake_decomposer):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/initiatives/initiative:abc/decompose")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["initiative_id"] == "initiative:abc"
    assert "plan" in data
    assert data["plan"]["spec_id"] == "agent_spec:fake"


@pytest.mark.asyncio
@patch("core.engine.pm.tracker.InitiativeTracker.get_initiative")
async def test_decompose_rejects_non_planning(mock_get, app_with_mocks):
    """POST /initiatives/{id}/decompose rejects if not in planning state."""
    app, mock_db = app_with_mocks

    mock_get.return_value = {
        "id": "initiative:abc",
        "status": "active",
        "milestones_detail": [],
        "progress": 0.0,
        "computed_status": "active",
        "budget_status": {"status": "ok", "percentage": 0.0},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/decompose")

    assert resp.status_code == 400
    assert "Cannot decompose" in resp.json()["detail"]


@pytest.mark.asyncio
@patch("core.engine.pm.tracker.InitiativeTracker.activate_initiative")
async def test_start_initiative_from_ready(mock_activate, app_with_mocks):
    """POST /initiatives/{id}/start transitions ready -> active."""
    app, mock_db = app_with_mocks

    mock_activate.return_value = {
        "id": "initiative:abc",
        "status": "active",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/start")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"


@pytest.mark.asyncio
@patch("core.engine.pm.tracker.InitiativeTracker.activate_initiative")
async def test_start_initiative_rejects_bad_state(mock_activate, app_with_mocks):
    """POST /initiatives/{id}/start returns 400 if state machine rejects."""
    app, mock_db = app_with_mocks

    mock_activate.return_value = {"error": "Cannot activate from state 'planning'"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/start")

    assert resp.status_code == 400
    assert "Cannot activate" in resp.json()["detail"]


@pytest.mark.asyncio
@patch("core.engine.events.bus.bus.emit", new_callable=AsyncMock)
@patch("core.engine.pm.tracker.InitiativeTracker.get_initiative")
async def test_review_initiative_from_completing(mock_get, mock_emit, app_with_mocks):
    """POST /initiatives/{id}/review transitions completing -> review."""
    app, mock_db = app_with_mocks

    mock_get.return_value = {
        "id": "initiative:abc",
        "status": "completing",
        "milestones_detail": [],
        "progress": 100.0,
        "computed_status": "completed",
        "budget_status": {"status": "ok", "percentage": 50.0},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/review")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "review"
    assert data["initiative_id"] == "initiative:abc"
    mock_emit.assert_called_once()
    call_args = mock_emit.call_args[0]
    assert call_args[0] == "gate.pending"
    assert call_args[1]["entity_type"] == "initiative"


@pytest.mark.asyncio
@patch("core.engine.pm.tracker.InitiativeTracker.get_initiative")
async def test_review_rejects_non_completing(mock_get, app_with_mocks):
    """POST /initiatives/{id}/review rejects if not in completing state."""
    app, mock_db = app_with_mocks

    mock_get.return_value = {
        "id": "initiative:abc",
        "status": "active",
        "milestones_detail": [],
        "progress": 50.0,
        "computed_status": "active",
        "budget_status": {"status": "ok", "percentage": 30.0},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/review")

    assert resp.status_code == 400
    assert "Cannot review" in resp.json()["detail"]


@pytest.mark.asyncio
@patch("core.engine.pm.gate_engine.GateEngine.approve_gate", new_callable=AsyncMock)
async def test_complete_initiative_from_review(mock_approve, app_with_mocks):
    """POST /initiatives/{id}/complete approves via GateEngine."""
    app, mock_db = app_with_mocks

    mock_approve.return_value = {
        "decision": {"id": "decision:1"},
        "entity": {"id": "initiative:abc", "status": "completed"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/initiatives/initiative:abc/complete")

    assert resp.status_code == 200
    data = resp.json()
    assert data["entity"]["status"] == "completed"
    mock_approve.assert_called_once_with(
        "initiative", "initiative:abc", "review", "Quality acceptable", "product:test", "user:test"
    )
