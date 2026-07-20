# tests/test_api_product.py
"""API tests for product awareness layer endpoints."""

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
async def test_list_capabilities(app_client):
    """GET /product/capabilities returns capabilities list with count."""
    capabilities = [
        {"id": "capability:1", "slug": "auth", "name": "Authentication", "status": "built"},
        {"id": "capability:2", "slug": "billing", "name": "Billing", "status": "planned"},
    ]

    with patch("core.engine.api.product.ProductMap") as MockPM:
        instance = MockPM.return_value
        instance.get_capabilities = AsyncMock(return_value=capabilities)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/product/capabilities")

    assert resp.status_code == 200
    body = resp.json()
    assert "capabilities" in body
    assert body["count"] == 2
    assert body["capabilities"][0]["slug"] == "auth"


@pytest.mark.asyncio
async def test_create_capability(app_client):
    """POST /product/capabilities returns 201 with created capability."""
    created = {
        "id": "capability:new",
        "slug": "search",
        "name": "Search",
        "description": "Full-text search across entities",
        "status": "built",
    }

    with patch("core.engine.api.product.ProductMap") as MockPM:
        instance = MockPM.return_value
        instance.upsert_capability = AsyncMock(return_value=created)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/product/capabilities",
                json={
                    "name": "Search",
                    "slug": "search",
                    "description": "Full-text search across entities",
                    "status": "built",
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "search"


@pytest.mark.asyncio
async def test_get_vision(app_client):
    """GET /product/vision returns active vision."""
    vision = {
        "id": "product_vision:1",
        "name": "DevOps-native AI PM",
        "description": "Bootstrap from git, learn from usage",
        "goals": [{"title": "Ship faster", "metric": "deploy freq"}],
        "active": True,
    }

    with patch("core.engine.api.product.ProductMap") as MockPM:
        instance = MockPM.return_value
        instance.get_vision = AsyncMock(return_value=vision)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/product/vision")

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "DevOps-native AI PM"
    assert body["active"] is True


@pytest.mark.asyncio
async def test_get_health(app_client):
    """GET /product/health returns aggregate quality summary with dimensions."""
    health = {
        "dimensions": {
            "testing": {"avg_score": 0.75, "min_score": 0.5, "assessed_count": 4, "total_gaps": 2},
            "security": {"avg_score": 0.9, "min_score": 0.85, "assessed_count": 3, "total_gaps": 0},
        },
        "total_capabilities": 10,
        "by_status": {"built": 7, "planned": 2, "partial": 1},
    }

    with patch("core.engine.api.product.ProductMap") as MockPM:
        instance = MockPM.return_value
        instance.health_summary = AsyncMock(return_value=health)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/product/health")

    assert resp.status_code == 200
    body = resp.json()
    assert "dimensions" in body
    assert "total_capabilities" in body
    assert body["total_capabilities"] == 10
    assert "testing" in body["dimensions"]
