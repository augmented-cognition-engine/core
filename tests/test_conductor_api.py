# tests/test_conductor_api.py
"""Tests for conductor API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_lifecycle_returns_tracks():
    with (
        patch("core.engine.api.conductor.pool") as mock_pool,
        patch("core.engine.api.conductor.parse_rows", return_value=[{"state": "met"}]),
    ):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        cm.__aexit__ = AsyncMock()
        mock_pool.connection.return_value = cm

        from core.engine.api.conductor import lifecycle_view

        result = await lifecycle_view("product:test", user={"product": "product:test"})
        assert "tracks" in result
        assert result["count"] == 1


@pytest.mark.asyncio
async def test_health_returns_metrics():
    with (
        patch("core.engine.api.conductor.pool") as mock_pool,
        patch(
            "core.engine.api.conductor.parse_rows",
            side_effect=[
                [{"state": "met", "cnt": 5}],  # tracks by state
                [{"cnt": 1}],  # stuck
                [{"cnt": 10}],  # executions
            ],
        ),
    ):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        cm.__aexit__ = AsyncMock()
        mock_pool.connection.return_value = cm

        from core.engine.api.conductor import conductor_health

        result = await conductor_health("product:test", user={"product": "product:test"})
        assert "tracks_total" in result
        assert "stuck_count" in result
