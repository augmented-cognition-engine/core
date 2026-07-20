from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_estimate_with_data():
    """Returns avg_tokens_control when matching baseline exists."""
    from core.engine.intelligence.token_baseline import estimate_baseline

    mock_rows = [{"avg_tokens_control": 3500, "discipline": "security", "complexity": "moderate"}]
    with patch("core.engine.intelligence.token_baseline._query_baseline", return_value=mock_rows):
        result = await estimate_baseline("security", "moderate", "product:default")
    assert result == 3500


@pytest.mark.asyncio
async def test_fallback_to_discipline():
    """Falls back to discipline average when complexity doesn't match."""
    from core.engine.intelligence.token_baseline import estimate_baseline

    with patch(
        "core.engine.intelligence.token_baseline._query_baseline",
        side_effect=[
            [],  # exact match fails
            [{"avg_tokens_control": 3000}],  # discipline fallback
        ],
    ):
        result = await estimate_baseline("security", "complex", "product:default")
    assert result == 3000


@pytest.mark.asyncio
async def test_fallback_to_none():
    """Returns None when no baseline data exists at all."""
    from core.engine.intelligence.token_baseline import estimate_baseline

    with patch("core.engine.intelligence.token_baseline._query_baseline", return_value=[]):
        result = await estimate_baseline("unknown", "simple", "product:default")
    assert result is None


@pytest.mark.asyncio
async def test_update_baseline_running_average():
    """update_baseline computes running average with new data."""
    from core.engine.intelligence.token_baseline import update_baseline

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{}])

    with patch("core.engine.intelligence.token_baseline.pool") as mock_pool:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await update_baseline("security", "moderate", "product:default", 3500, 2800)

    mock_db.query.assert_called_once()
    query = mock_db.query.call_args[0][0]
    assert "UPSERT" in query


@pytest.mark.asyncio
async def test_savings_pct_calculation():
    """savings_pct is 1 - (variant / control)."""
    from core.engine.intelligence.token_baseline import _compute_savings_pct

    assert _compute_savings_pct(3500, 2800) == pytest.approx(0.2, abs=0.01)
    assert _compute_savings_pct(3500, 3500) == 0.0
    assert _compute_savings_pct(0, 100) == 0.0  # guard against division by zero
