# tests/test_api_decisions.py
"""Tests for the decisions REST API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def mock_lifespan(app):
    yield


def _mock_user():
    return {"product": "product:default", "sub": "user:test"}


@pytest.mark.asyncio
@patch("core.engine.api.decisions.create_decision", new_callable=AsyncMock)
async def test_post_decisions(mock_create):
    """POST /decisions creates a decision."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user
    mock_create.return_value = {
        "id": "decision:abc",
        "title": "Use SurrealDB",
        "decision_type": "architecture",
        "rationale": "Graph + document store",
        "outcome": "accepted",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/decisions",
            json={
                "title": "Use SurrealDB",
                "decision_type": "architecture",
                "rationale": "Graph + document store",
            },
        )

    assert resp.status_code == 201
    assert resp.json()["title"] == "Use SurrealDB"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.decisions.list_decisions", new_callable=AsyncMock)
async def test_get_decisions(mock_list):
    """GET /decisions lists decisions."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user
    mock_list.return_value = [
        {"id": "decision:a", "title": "A", "decision_type": "architecture"},
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/decisions")

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("core.engine.api.decisions.get_decision", new_callable=AsyncMock)
async def test_get_decision_by_id(mock_get):
    """GET /decisions/{id} returns a single decision."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user
    mock_get.return_value = {
        "id": "decision:abc",
        "title": "Use SurrealDB",
        "decision_type": "architecture",
        "rationale": "Graph + document store",
        "outcome": "accepted",
        "edges": {"affected": [], "led_to": [], "supersedes": []},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/decisions/decision:abc")

    assert resp.status_code == 200
    assert resp.json()["title"] == "Use SurrealDB"
    assert "edges" in resp.json()
    app.dependency_overrides.clear()
