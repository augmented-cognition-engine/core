"""Tests for gate API endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:test", "sub": "user:1"}


@pytest.mark.asyncio
@patch("core.engine.api.gates.GateEngine")
@patch("core.engine.api.gates._current_gate_state", new_callable=AsyncMock)
async def test_evaluate_gate(mock_state, MockGE):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_state.return_value = "spec_review"
    mock_ge = AsyncMock()
    MockGE.return_value = mock_ge
    mock_ge.evaluate_gate = AsyncMock(
        return_value={
            "risk_level": "low",
            "auto_approve": True,
            "reason": "Low risk",
            "risk_factors": [],
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/gates/idea/idea:1/evaluate")

    assert resp.status_code == 200
    assert resp.json()["risk_level"] == "low"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.gates.GateEngine")
@patch("core.engine.api.gates._current_gate_state", new_callable=AsyncMock)
async def test_approve_gate(mock_state, MockGE):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_state.return_value = "spec_review"
    mock_ge = AsyncMock()
    MockGE.return_value = mock_ge
    mock_ge.approve_gate = AsyncMock(
        return_value={
            "decision": {"id": "decision:1"},
            "entity": {"id": "idea:1", "status": "planned"},
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/gates/idea/idea:1/approve", json={"rationale": "Looks good"})

    assert resp.status_code == 200
    assert "decision" in resp.json()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.gates.GateEngine")
@patch("core.engine.api.gates._current_gate_state", new_callable=AsyncMock)
async def test_reject_gate(mock_state, MockGE):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_state.return_value = "spec_review"
    mock_ge = AsyncMock()
    MockGE.return_value = mock_ge
    mock_ge.reject_gate = AsyncMock(
        return_value={
            "decision": {"id": "decision:2"},
            "entity": {"id": "idea:1", "status": "ready"},
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/gates/idea/idea:1/reject", json={"reason": "Needs work"})

    assert resp.status_code == 200
    assert "decision" in resp.json()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.gates.GateEngine")
async def test_list_pending(MockGE):
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    mock_ge = AsyncMock()
    MockGE.return_value = mock_ge
    mock_ge.list_pending = AsyncMock(
        return_value=[
            {"entity_type": "idea", "entity_id": "idea:1", "gate_state": "spec_review", "title": "Webhooks"},
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/gates/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["gates"][0]["entity_type"] == "idea"
    app.dependency_overrides.clear()
