# tests/test_idea_promote.py
"""Test idea thread and promotion endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

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


class TestGetIdeaThread:
    @pytest.mark.asyncio
    async def test_returns_existing_linked_session(self, client):
        from unittest.mock import patch

        with patch("core.engine.api.ideas.pool") as mock_pool:
            mock_db = AsyncMock()
            mock_db.query = AsyncMock(
                side_effect=[
                    [
                        [
                            {
                                "id": "chat_session:abc",
                                "linked_to": "idea:123",
                                "status": "active",
                                "product": "product:test",
                                "user": "user:test",
                            }
                        ]
                    ],
                    [[]],  # messages
                ]
            )
            mock_pool.connection = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_db),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            response = await client.get("/ideas/idea:123/thread")

        assert response.status_code == 200
        body = response.json()
        assert body["session"]["id"] == "chat_session:abc"


class TestPromoteIdea:
    @pytest.mark.asyncio
    async def test_promote_to_task(self, client):
        from unittest.mock import patch

        with patch("core.engine.api.ideas.pool") as mock_pool:
            mock_db = AsyncMock()
            mock_db.query = AsyncMock(
                side_effect=[
                    [
                        [
                            {
                                "id": "idea:123",
                                "title": "Fix CSS overflow",
                                "raw_input": "Fix the overflow on mobile",
                                "status": "ready",
                                "product": "product:test",
                                "brief": {"what": "Fix overflow"},
                            }
                        ]
                    ],
                    [[{"id": "task:456"}]],
                    [[]],  # update status
                ]
            )
            mock_pool.connection = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_db),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            response = await client.post(
                "/ideas/idea:123/promote",
                json={"target": "task"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["target"] == "task"

    @pytest.mark.asyncio
    async def test_promote_to_initiative(self, client):
        from unittest.mock import patch

        with patch("core.engine.api.ideas.pool") as mock_pool:
            mock_db = AsyncMock()
            mock_db.query = AsyncMock(
                side_effect=[
                    [
                        [
                            {
                                "id": "idea:123",
                                "title": "Build feedback system",
                                "raw_input": "Customer feedback loop",
                                "status": "ready",
                                "product": "product:test",
                                "brief": {"what": "Feedback system", "why": "Need signals"},
                            }
                        ]
                    ],
                    [[{"id": "initiative:789"}]],
                    [[]],  # update status
                ]
            )
            mock_pool.connection = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_db),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            response = await client.post(
                "/ideas/idea:123/promote",
                json={"target": "initiative"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["target"] == "initiative"
