# tests/test_api_efficiency.py
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


def _mock_user():
    return {"sub": "user:test", "product": "product:default"}


@pytest.fixture
async def client():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_efficiency_summary(client):
    """GET /efficiency returns token savings summary."""
    mock_data = {"total_tokens": 50000, "estimated_saved": 12000, "task_count": 47}
    with patch("core.engine.api.efficiency._query_efficiency_summary", return_value=mock_data):
        resp = await client.get("/efficiency")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tokens" in data
    assert "estimated_saved" in data


@pytest.mark.asyncio
async def test_get_efficiency_compositions(client):
    """GET /efficiency/compositions returns ranked compositions."""
    mock_data = [
        {
            "discipline": "security",
            "perspectives": ["practitioner", "strategist"],
            "acceptance_rate": 0.85,
            "avg_tokens": 3200,
            "count": 12,
        }
    ]
    with patch("core.engine.api.efficiency._query_top_compositions", return_value=mock_data):
        resp = await client.get("/efficiency/compositions")
    assert resp.status_code == 200
    data = resp.json()
    assert "compositions" in data


@pytest.mark.asyncio
async def test_get_efficiency_baselines(client):
    """GET /efficiency/baselines returns baseline estimates."""
    mock_data = [
        {
            "discipline": "security",
            "complexity": "moderate",
            "avg_tokens_control": 3500,
            "avg_tokens_variant": 2800,
            "savings_pct": 0.2,
        }
    ]
    with patch("core.engine.api.efficiency._query_baselines", return_value=mock_data):
        resp = await client.get("/efficiency/baselines")
    assert resp.status_code == 200
    data = resp.json()
    assert "baselines" in data
