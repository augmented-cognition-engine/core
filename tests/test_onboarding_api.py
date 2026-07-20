# tests/test_onboarding_api.py
"""Tests for new onboarding API endpoints (status, greenfield, complete)."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_MOCK_USER = {"sub": "user:test", "product": "product:test"}


@pytest.fixture
def app_client():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.api
async def test_onboarding_status_new_org(app_client):
    """New org with no capabilities returns needs_onboarding=True."""
    with patch("core.engine.api.onboarding.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query.side_effect = [[[]], [[]], [[{"onboarding_complete": None}]]]

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_onboarding"] is True
    assert data["capabilities_count"] == 0


@pytest.mark.asyncio
@pytest.mark.api
async def test_onboarding_status_existing_org(app_client):
    """Org with capabilities returns needs_onboarding=False."""
    with patch("core.engine.api.onboarding.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query.side_effect = [[[{"count": 5}]], [[{"id": "project:1"}]], [[{"onboarding_complete": True}]]]

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_onboarding"] is False
    assert data["capabilities_count"] == 5


@pytest.mark.asyncio
@pytest.mark.api
async def test_onboarding_greenfield_returns_capabilities(app_client):
    """POST /onboarding/greenfield returns LLM-generated capabilities."""
    mock_result = {
        "capabilities": [{"name": "Auth", "slug": "auth", "description": "Auth system", "priority": "critical"}],
        "vision": "A great product",
        "recommended_first": {"capability": "auth", "reason": "Core"},
    }
    with patch("core.engine.api.onboarding.CapabilityMapper") as MockMapper:
        instance = MockMapper.return_value
        instance.bootstrap_from_intent = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/onboarding/greenfield",
                json={"description": "A marketplace for designers"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["capabilities"]) == 1
    assert data["vision"] == "A great product"


@pytest.mark.asyncio
@pytest.mark.api
async def test_onboarding_complete_creates_initiative(app_client):
    """POST /onboarding/complete creates an initiative and marks done."""
    with (
        patch("core.engine.api.onboarding.pool") as mock_pool,
        patch("core.engine.api.onboarding.needs_onboarding", new_callable=AsyncMock, return_value=False),
        patch("core.engine.api.onboarding.scaffold_project", new_callable=AsyncMock),
        patch("core.engine.api.onboarding.scaffold_specialties", new_callable=AsyncMock),
    ):
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query = AsyncMock(return_value=[[{"id": "initiative:abc"}]])

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/onboarding/complete",
                json={
                    "create_initiative": True,
                    "initiative_title": "Add auth tests",
                    "initiative_description": "Critical gap in auth module",
                    "capability_slug": "auth",
                    "path": "greenfield",
                },
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_complete"] is True


@pytest.mark.asyncio
@pytest.mark.api
async def test_onboarding_complete_skip_initiative(app_client):
    """POST /onboarding/complete with create_initiative=False skips initiative creation."""
    with (
        patch("core.engine.api.onboarding.pool") as mock_pool,
        patch("core.engine.api.onboarding.needs_onboarding", new_callable=AsyncMock, return_value=False),
    ):
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query = AsyncMock(return_value=[[]])

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/onboarding/complete",
                json={"create_initiative": False, "path": "existing"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_complete"] is True
    assert data.get("initiative_id") is None
