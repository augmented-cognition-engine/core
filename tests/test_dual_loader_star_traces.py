# tests/test_dual_loader_star_traces.py
"""Tests for star_traces loading in load_dual_intelligence (Gap 1 closure)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.dual_loader import load_dual_intelligence


async def _noop_loaders(*_a, **_kw):
    return []


@pytest.mark.asyncio
async def test_load_dual_intelligence_includes_star_traces_key():
    """snapshot always has star_traces key, even when empty."""
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.orchestrator.loader._load_failure_memory", new=AsyncMock(return_value=[])):
            with patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=[])):
                result = await load_dual_intelligence(
                    specialties=[],
                    product_id="product:test",
                    discipline="architecture",
                )

    assert "star_traces" in result


@pytest.mark.asyncio
async def test_load_dual_intelligence_star_traces_populated_from_loader():
    """When load_star_traces returns traces, snapshot['star_traces'] is non-empty."""
    fake_traces = [{"task_description": "refactor auth module", "final_output": "did it", "discipline": "architecture"}]

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.orchestrator.loader._load_failure_memory", new=AsyncMock(return_value=[])):
            with patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=[])):
                with patch(
                    "core.engine.cognition.star_trace.load_star_traces",
                    new=AsyncMock(return_value=fake_traces),
                ):
                    result = await load_dual_intelligence(
                        specialties=[],
                        product_id="product:test",
                        discipline="architecture",
                    )

    assert result["star_traces"] == fake_traces


@pytest.mark.asyncio
async def test_load_dual_intelligence_star_traces_empty_without_discipline():
    """No discipline → star_traces skipped, key present but empty."""
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.orchestrator.loader._load_failure_memory", new=AsyncMock(return_value=[])):
            with patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=[])):
                result = await load_dual_intelligence(
                    specialties=[],
                    product_id="product:test",
                    discipline="",
                )

    assert result["star_traces"] == []


@pytest.mark.asyncio
async def test_load_dual_intelligence_star_traces_failure_is_non_fatal():
    """If load_star_traces raises, star_traces defaults to [] and no exception propagates."""
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.orchestrator.loader._load_failure_memory", new=AsyncMock(return_value=[])):
            with patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=[])):
                with patch(
                    "core.engine.cognition.star_trace.load_star_traces",
                    side_effect=RuntimeError("db exploded"),
                ):
                    result = await load_dual_intelligence(
                        specialties=[],
                        product_id="product:test",
                        discipline="security",
                    )

    assert result["star_traces"] == []
