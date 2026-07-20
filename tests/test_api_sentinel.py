# tests/test_api_sentinel.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from contextlib import asynccontextmanager

    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: {"product": "product:test", "sub": "user:test"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sentinel_status_returns_engines(client):
    """GET /sentinel/status returns scheduler status and engine list."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_status_eng", cron="0 1 * * *", description="Test")
    async def run(product_id: str) -> dict:
        return {}

    with patch("core.engine.api.sentinel.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[]])
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        response = await client.get("/sentinel/status")

    assert response.status_code == 200
    body = response.json()
    assert "scheduler_running" in body
    assert "engines" in body
    assert len(body["engines"]) >= 1
    eng = next(e for e in body["engines"] if e["name"] == "test_status_eng")
    assert eng["cron"] == "0 1 * * *"


@pytest.mark.asyncio
async def test_sentinel_runs_returns_history(client):
    """GET /sentinel/runs returns engine run history."""
    with patch("core.engine.api.sentinel.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "engine_run:abc",
                        "engine": "decay_manager",
                        "status": "completed",
                        "started_at": "2026-03-21T02:00:00Z",
                        "completed_at": "2026-03-21T02:00:01Z",
                        "duration_ms": 1234,
                        "results": {"insights_decayed": 5},
                        "cost": 0.0,
                    }
                ]
            ]
        )
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        response = await client.get("/sentinel/runs?product=product:test&limit=10")
        assert response.status_code == 200
        body = response.json()
        assert "runs" in body


@pytest.mark.asyncio
async def test_sentinel_trigger_unknown_engine(client):
    """POST /sentinel/trigger/{engine} with unknown engine returns 404."""
    from core.engine.sentinel.registry import engine_registry

    engine_registry.clear()

    response = await client.post("/sentinel/trigger/nonexistent?product=product:test")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sentinel_trigger_known_engine(client):
    """POST /sentinel/trigger/{engine} triggers execution and returns run ID."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="trigger_test", cron="0 1 * * *", description="Trigger test")
    async def run(product_id: str) -> dict:
        return {"items": 3}

    with patch("core.engine.api.sentinel.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[{"id": "engine_run:triggered"}])
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        mock_sched = AsyncMock()
        mock_sched.execute_engine = AsyncMock(
            return_value={
                "engine_run_id": "engine_run:triggered",
                "status": "completed",
                "results": {"items": 3},
                "duration_ms": 100,
            }
        )

        with patch("core.engine.api.sentinel._scheduler", mock_sched):
            response = await client.post("/sentinel/trigger/trigger_test?product=product:test")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("completed", "running")
