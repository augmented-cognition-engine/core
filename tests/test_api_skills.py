# tests/test_api_skills.py
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from core.engine.api.main import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_skills_requires_auth(client):
    resp = await client.get("/skills?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_skill_get_requires_auth(client):
    resp = await client.get("/skills/deep-research")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_skill_create_requires_auth(client):
    resp = await client.post(
        "/skills",
        json={
            "slug": "test",
            "name": "Test",
            "description": "test",
            "jobs": [{"name": "s1", "archetype": "executor", "mode": "reactive"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_skill_delete_requires_auth(client):
    resp = await client.delete("/skills/test")
    assert resp.status_code == 401
