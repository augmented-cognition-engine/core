# tests/test_api_tasks_feedback.py
"""Tests for the enhanced PATCH /tasks/{id} feedback endpoint with RLIF processing."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _mock_user():
    return {"sub": "user:test", "product": "product:test"}


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
async def test_patch_task_edited_feedback(client):
    """PATCH /tasks/{id} with edited feedback updates task output."""
    with patch("core.engine.api.tasks.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[{"id": "task:123"}])
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        response = await client.patch(
            "/tasks/task:123",
            json={
                "feedback_human": "edited",
                "edited_output": "Edited version",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["feedback_human"] == "edited"
    assert body["output_versions"] == 1


@pytest.mark.asyncio
async def test_patch_task_accepted_feedback(client):
    """PATCH /tasks/{id} with accepted feedback records acceptance."""
    with patch("core.engine.api.tasks.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[{"id": "task:123"}])
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        response = await client.patch(
            "/tasks/task:123",
            json={
                "feedback_human": "accepted",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["feedback_human"] == "accepted"


@pytest.mark.asyncio
async def test_patch_task_rejected_feedback(client):
    """PATCH /tasks/{id} with rejected feedback records rejection."""
    with patch("core.engine.api.tasks.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[{"id": "task:456"}])
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        response = await client.patch(
            "/tasks/task:456",
            json={
                "feedback_human": "rejected",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["feedback_human"] == "rejected"


@pytest.mark.asyncio
async def test_patch_task_edited_requires_edited_output(client):
    """PATCH /tasks/{id} with edited feedback but no edited_output returns 422."""
    response = await client.patch(
        "/tasks/task:123",
        json={
            "feedback_human": "edited",
        },
    )
    assert response.status_code == 422
