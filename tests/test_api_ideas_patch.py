"""Tests for PATCH /ideas/{id} endpoint."""

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
async def test_patch_idea_valid_fields(mock_parse_one):
    """PATCH /ideas/{id} with valid fields returns 200 with updated idea."""
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

    existing_idea = {"id": "idea:1", "status": "captured", "title": "Old title", "product": "product:test"}
    updated_idea = {**existing_idea, "title": "New title"}

    # parse_one: first call is SELECT (existing idea), second is UPDATE result
    mock_parse_one.side_effect = [existing_idea, updated_idea]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/ideas/idea:1", json={"title": "New title"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New title"

    app.dependency_overrides.clear()
    ideas_mod.pool = orig_pool


@pytest.mark.asyncio
async def test_patch_idea_status_rejected():
    """PATCH /ideas/{id} with status field returns 400."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = _mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/ideas/idea:1", json={"status": "ready"})

    assert resp.status_code == 400
    assert "lifecycle endpoints" in resp.json()["detail"]

    app.dependency_overrides.clear()
