"""Tests for developer velocity metrics."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.velocity import VelocityCalculator, VelocityMetrics


@pytest.mark.asyncio
async def test_calculate_with_reviews():
    calc = VelocityCalculator()

    mock_reviews = [
        {"pr_number": 1, "findings_count": 3, "pass_quality_gate": True, "created_at": "2026-03-25T10:00:00Z"},
        {"pr_number": 2, "findings_count": 0, "pass_quality_gate": True, "created_at": "2026-03-26T10:00:00Z"},
        {"pr_number": 3, "findings_count": 5, "pass_quality_gate": False, "created_at": "2026-03-27T10:00:00Z"},
    ]

    with patch("core.engine.review.velocity.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [mock_reviews],  # reviews query
                [[]],  # reactions query
                [[]],  # git stats query
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        metrics = await calc.calculate("owner", "repo", period_days=30)

    assert metrics.total_reviews == 3
    assert metrics.avg_findings_per_review == pytest.approx(8 / 3, rel=0.1)
    assert metrics.review_pass_rate == pytest.approx(2 / 3, rel=0.1)


@pytest.mark.asyncio
async def test_calculate_empty():
    calc = VelocityCalculator()

    with patch("core.engine.review.velocity.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        metrics = await calc.calculate("owner", "repo")

    assert metrics.total_reviews == 0
    assert metrics.review_pass_rate == 0


def test_metrics_model_defaults():
    m = VelocityMetrics()
    assert m.deployment_frequency == 0.0
    assert m.period_days == 30
