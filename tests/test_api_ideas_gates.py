"""Tests for idea spec/plan generation and approval endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


def _make_mock_pool(db_mock):
    """Create a mock pool that returns the given db mock from connection()."""
    p = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db_mock)
    ctx.__aexit__ = AsyncMock(return_value=False)
    p.connection = MagicMock(return_value=ctx)
    p.init = AsyncMock()
    p.close = AsyncMock()
    return p


@pytest.mark.asyncio
@patch("core.engine.api.ideas.parse_one")
async def test_generate_spec_from_ready(mock_parse_one):
    """POST /ideas/{id}/generate-spec transitions ready -> speccing -> spec_review."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = _make_mock_pool(mock_db)

    import core.engine.api.ideas as ideas_mod

    orig_pool = ideas_mod.pool
    ideas_mod.pool = mock_pool

    # parse_one returns the idea on first call (SELECT), then None for UPDATEs
    mock_parse_one.side_effect = [
        {"id": "idea:1", "status": "ready", "title": "Webhooks", "capability_slug": "webhooks"},
        None,  # UPDATE to speccing
        None,  # UPDATE to spec_review
    ]

    mock_spec = {"id": "agent_spec:abc", "title": "Webhooks spec", "status": "generated"}
    mock_risk = {"risk_level": "low", "auto_approve": True, "reason": "Low risk", "risk_factors": []}

    with (
        patch(
            "core.engine.product.spec_generator.SpecGenerator.from_idea", new_callable=AsyncMock, return_value=mock_spec
        ),
        patch("core.engine.pm.gate_engine.GateEngine.evaluate_gate", new_callable=AsyncMock, return_value=mock_risk),
        patch("core.engine.pm.gate_engine.GateEngine.auto_approve_gate", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/ideas/idea:1/generate-spec")

        assert resp.status_code == 200
        data = resp.json()
        assert data["idea_id"] == "idea:1"
        assert data["spec"]["id"] == "agent_spec:abc"
        assert data["risk"]["risk_level"] == "low"

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool


@pytest.mark.asyncio
@patch("core.engine.api.ideas.parse_one")
async def test_generate_spec_wrong_state(mock_parse_one):
    """POST /ideas/{id}/generate-spec from captured state returns 400."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = _make_mock_pool(mock_db)

    import core.engine.api.ideas as ideas_mod

    orig_pool = ideas_mod.pool
    ideas_mod.pool = mock_pool

    mock_parse_one.return_value = {"id": "idea:1", "status": "captured", "title": "Raw idea"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/ideas/idea:1/generate-spec")

    assert resp.status_code == 400
    assert "captured" in resp.json()["detail"]

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool


@pytest.mark.asyncio
async def test_approve_spec():
    """POST /ideas/{id}/approve-spec calls gate engine approve."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_pool = _make_mock_pool(mock_db)

    import core.engine.api.ideas as ideas_mod

    orig_pool = ideas_mod.pool
    ideas_mod.pool = mock_pool

    mock_result = {
        "decision": {"id": "decision:1"},
        "entity": {"id": "idea:1", "status": "planned"},
    }

    with patch("core.engine.pm.gate_engine.GateEngine.approve_gate", new_callable=AsyncMock, return_value=mock_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/ideas/idea:1/approve-spec")

        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert data["entity"]["status"] == "planned"

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool


@pytest.mark.asyncio
@patch("core.engine.api.ideas.parse_one")
async def test_generate_plan(mock_parse_one):
    """POST /ideas/{id}/generate-plan calls SmartDecomposer and returns plan."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = _make_mock_pool(mock_db)

    import core.engine.api.ideas as ideas_mod

    orig_pool = ideas_mod.pool
    ideas_mod.pool = mock_pool

    mock_parse_one.side_effect = [
        {"id": "idea:1", "status": "planned", "spec_id": "agent_spec:abc", "title": "Webhooks"},
        None,  # UPDATE to plan_review
    ]

    # Create a mock plan with to_dict
    mock_plan = MagicMock()
    mock_plan.to_dict.return_value = {
        "spec_id": "agent_spec:abc",
        "units": [{"id": "wu:1", "title": "Create handler"}],
        "total_units": 1,
    }
    mock_risk = {"risk_level": "low", "auto_approve": False, "reason": "Needs review", "risk_factors": []}

    with (
        patch(
            "core.engine.product.smart_decompose.SmartDecomposer.decompose",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch("core.engine.pm.gate_engine.GateEngine.evaluate_gate", new_callable=AsyncMock, return_value=mock_risk),
        patch("core.engine.events.bus.bus.emit", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/ideas/idea:1/generate-plan")

        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data
        assert data["plan"]["spec_id"] == "agent_spec:abc"
        assert data["risk"]["risk_level"] == "low"

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool


@pytest.mark.asyncio
@patch("core.engine.api.ideas.parse_one")
async def test_approve_plan_creates_initiative(mock_parse_one):
    """POST /ideas/{id}/approve-plan approves and creates initiative."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])
    mock_pool = _make_mock_pool(mock_db)

    import core.engine.api.ideas as ideas_mod

    orig_pool = ideas_mod.pool
    ideas_mod.pool = mock_pool

    gate_result = {
        "decision": {"id": "decision:2"},
        "entity": {"id": "idea:1", "status": "promoted"},
    }

    # parse_one calls: first for idea SELECT, then for initiative CREATE
    mock_parse_one.side_effect = [
        {
            "id": "idea:1",
            "status": "promoted",
            "title": "Webhooks",
            "brief": {"what": "Add webhook support", "approach": "Event bus integration"},
            "raw_input": "We need webhooks",
        },
        {"id": "initiative:new", "title": "Webhooks", "status": "planning"},
    ]

    with (
        patch("core.engine.pm.gate_engine.GateEngine.approve_gate", new_callable=AsyncMock, return_value=gate_result),
        patch("core.engine.graph.edge_writer.create_edge", new_callable=AsyncMock, return_value={"id": "edge:1"}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/ideas/idea:1/approve-plan")

        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert data["initiative"]["id"] == "initiative:new"

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool
