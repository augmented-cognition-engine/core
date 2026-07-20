# tests/test_api_experiments.py
"""Tests for experiments API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_with_mocks():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    mock_user = {"sub": "user:test", "product": "product:test"}
    mock_db = AsyncMock()
    mock_pool = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection = MagicMock(return_value=ctx)
    mock_pool.init = AsyncMock()
    mock_pool.close = AsyncMock()

    @asynccontextmanager
    async def mock_lifespan(a):
        yield

    app.router.lifespan_context = mock_lifespan
    app.dependency_overrides[get_current_user] = lambda: mock_user

    import core.engine.api.experiments as exp_mod

    orig_pool = exp_mod.pool
    exp_mod.pool = mock_pool

    yield app, mock_db

    app.dependency_overrides.clear()
    exp_mod.pool = orig_pool


@pytest.mark.asyncio
async def test_list_experiments(app_with_mocks):
    """GET /experiments returns experiment list."""
    app, mock_db = app_with_mocks
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "id": "experiment_log:1",
                    "domain": "architecture",
                    "experiment_type": "intelligence_variant",
                    "improvement": 0.05,
                    "significant": True,
                    "committed": True,
                },
            ]
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/experiments?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert "experiments" in data
        assert len(data["experiments"]) == 1


@pytest.mark.asyncio
async def test_experiment_summary(app_with_mocks):
    """GET /experiments/summary returns aggregate stats."""
    app, mock_db = app_with_mocks

    call_count = 0

    async def multi_query(query_str, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [[{"n": 10}]]  # total
        if call_count == 2:
            return [[{"n": 3}]]  # winners
        if call_count == 3:
            return [[{"avg_imp": 0.08}]]  # avg improvement
        return [[]]  # by_type

    mock_db.query = AsyncMock(side_effect=multi_query)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/experiments/summary?product=product:test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_experiments"] == 10
        assert data["winners_committed"] == 3
