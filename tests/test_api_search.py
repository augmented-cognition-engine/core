# tests/test_api_search.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_search_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/intel/search?q=test&product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_maturation_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/intel/technology.engineering/maturation?product=product:test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_feedback_requires_auth():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/tasks/task:abc", json={"feedback_human": "accepted"})
    assert resp.status_code == 401
