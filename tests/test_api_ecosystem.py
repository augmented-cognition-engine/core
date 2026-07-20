# tests/test_api_ecosystem.py
"""API tests for ecosystem and project hierarchy endpoints."""

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
async def test_list_ecosystems(app_client):
    """GET /ecosystems returns ecosystems list with count."""
    ecosystems = [
        {"id": "ecosystem:1", "slug": "platform", "name": "Platform"},
        {"id": "ecosystem:2", "slug": "data", "name": "Data"},
    ]

    with patch("core.engine.api.ecosystem.EcosystemManager") as MockEM:
        instance = MockEM.return_value
        instance.get_ecosystems = AsyncMock(return_value=ecosystems)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/ecosystems")

    assert resp.status_code == 200
    body = resp.json()
    assert "ecosystems" in body
    assert body["count"] == 2
    assert body["ecosystems"][0]["slug"] == "platform"


@pytest.mark.asyncio
async def test_create_ecosystem(app_client):
    """POST /ecosystems returns 201 with created ecosystem."""
    created = {
        "id": "ecosystem:new",
        "slug": "mobile",
        "name": "Mobile Apps",
        "description": "iOS and Android products",
    }

    with patch("core.engine.api.ecosystem.EcosystemManager") as MockEM:
        instance = MockEM.return_value
        instance.create_ecosystem = AsyncMock(return_value=created)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.post(
                "/ecosystems",
                json={"slug": "mobile", "name": "Mobile Apps", "description": "iOS and Android products"},
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "mobile"
    assert body["name"] == "Mobile Apps"


@pytest.mark.asyncio
async def test_get_hierarchy(app_client):
    """GET /hierarchy returns full hierarchy tree."""
    hierarchy = {
        "ecosystems": [
            {
                "id": "ecosystem:1",
                "slug": "platform",
                "name": "Platform",
                "projects": [
                    {"id": "project:1", "slug": "ace-api", "name": "ACE API", "capability_count": 12},
                ],
            }
        ],
        "standalone_projects": [{"id": "project:2", "slug": "docs-site", "name": "Docs Site", "capability_count": 3}],
    }

    with patch("core.engine.api.ecosystem.EcosystemManager") as MockEM:
        instance = MockEM.return_value
        instance.get_hierarchy = AsyncMock(return_value=hierarchy)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/hierarchy")

    assert resp.status_code == 200
    body = resp.json()
    assert "ecosystems" in body
    assert "standalone_projects" in body
    assert len(body["ecosystems"]) == 1
    assert body["ecosystems"][0]["slug"] == "platform"
    assert body["ecosystems"][0]["projects"][0]["capability_count"] == 12


@pytest.mark.asyncio
async def test_list_projects(app_client):
    """GET /projects returns projects list, supports ?ecosystem= filter."""
    projects = [
        {"id": "project:1", "slug": "ace-api", "name": "ACE API"},
        {"id": "project:2", "slug": "ace-portal", "name": "ACE Portal"},
    ]

    with patch("core.engine.api.ecosystem.EcosystemManager") as MockEM:
        instance = MockEM.return_value
        instance.get_projects = AsyncMock(return_value=projects)

        async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as client:
            resp = await client.get("/projects?ecosystem=platform")

    assert resp.status_code == 200
    body = resp.json()
    assert "projects" in body
    assert body["count"] == 2
    # Verify the ecosystem filter was forwarded
    instance.get_projects.assert_called_once_with("product:test", "platform")
