# tests/test_api_ideas.py
"""API tests for idea endpoints."""

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
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    import core.engine.api.ideas as ideas_mod
    import core.engine.api.templates as templates_mod

    orig_ideas_pool = ideas_mod.pool
    orig_templates_pool = templates_mod.pool
    ideas_mod.pool = mock_pool
    templates_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_ideas_pool
    templates_mod.pool = orig_templates_pool


@pytest.mark.asyncio
async def test_api_post_ideas(app_with_mocks):
    """POST /ideas with raw text returns 201."""
    app, mock_db = app_with_mocks
    from core.engine.ideas.schemas import IdeaClassification

    mock_classification = IdeaClassification(
        domain_path="architecture",
        type="feature",
        complexity="simple",
        title="Test idea",
        summary="A test.",
    )

    with patch("core.engine.ideas.capture.llm") as mock_llm, patch("core.engine.ideas.capture.pool", MagicMock()):
        mock_llm.complete_structured = AsyncMock(return_value=mock_classification)

        # The capture function patches its own pool, so we mock at that level
        with patch(
            "core.engine.ideas.capture.capture_idea",
            AsyncMock(
                return_value={
                    "id": "idea:test",
                    "status": "captured",
                    "title": "Test idea",
                }
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/ideas", json={"raw_input": "Test idea"})
                assert resp.status_code == 201
                assert resp.json()["status"] == "captured"


@pytest.mark.asyncio
async def test_api_get_ideas(app_with_mocks):
    """GET /ideas returns ideas list."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"id": "idea:1", "title": "Idea 1", "status": "captured"},
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ideas?product=product:test")
        assert resp.status_code == 200
        assert "ideas" in resp.json()


@pytest.mark.asyncio
async def test_api_get_idea_detail(app_with_mocks):
    """GET /ideas/{id} returns full idea."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "idea:1",
                    "title": "Test",
                    "status": "ready",
                    "brief": {
                        "what": "test",
                        "why": "test",
                        "what_we_know": "",
                        "open_questions": [],
                        "approach": "",
                        "effort": "",
                        "risks": [],
                        "first_step": "",
                    },
                }
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ideas/idea:1")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test"


@pytest.mark.asyncio
async def test_api_get_playbooks(app_with_mocks):
    """GET /templates returns templates list."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"id": "template:1", "name": "QBR Prep", "times_used": 3},
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/templates?product=product:test")
        assert resp.status_code == 200
        assert "templates" in resp.json()


@pytest.mark.asyncio
async def test_api_post_playbooks(app_with_mocks):
    """POST /templates creates a template."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "template:new",
                    "name": "New PB",
                    "times_used": 0,
                }
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/templates",
            json={
                "name": "New PB",
                "description": "Test",
                "domain_path": "architecture",
                "milestones": [],
                "variables": [],
            },
        )
        assert resp.status_code == 201
