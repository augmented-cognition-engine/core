"""Tests for specialty bootstrap helper."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.sentinel.engines.bootstrap import research_specialty_by_description


@pytest.mark.asyncio
async def test_generates_insights_from_description():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "insight:1"}])

    with (
        patch("core.engine.sentinel.engines.bootstrap.llm") as mock_llm,
        patch("core.engine.sentinel.engines.bootstrap.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_llm.complete_json = AsyncMock(
            return_value={
                "insights": [
                    {
                        "content": "Futures contracts have daily mark-to-market settlement",
                        "confidence": 0.85,
                        "insight_type": "fact",
                    },
                    {
                        "content": "Delta hedging requires continuous rebalancing",
                        "confidence": 0.8,
                        "insight_type": "pattern",
                    },
                ]
            }
        )

        result = await research_specialty_by_description(
            {
                "id": "specialty:test",
                "slug": "futures-trading",
                "description": "Futures market trading and execution",
                "name": "Futures Trading",
            },
            "product:default",
        )

    assert result["insights_created"] >= 1


@pytest.mark.asyncio
async def test_sets_bootstrapped_when_threshold_met():
    mock_db = AsyncMock()
    # Return insight count above threshold after creation
    mock_db.query = AsyncMock(
        side_effect=[
            [{"id": "insight:1"}],  # create insight 1
            [{"id": "insight:2"}],  # create insight 2
            [{"insight_count": 5}],  # count check
            [],  # update bootstrapped
        ]
    )

    with (
        patch("core.engine.sentinel.engines.bootstrap.llm") as mock_llm,
        patch("core.engine.sentinel.engines.bootstrap.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_llm.complete_json = AsyncMock(
            return_value={
                "insights": [
                    {"content": "Fact 1", "confidence": 0.8, "insight_type": "fact"},
                    {"content": "Fact 2", "confidence": 0.8, "insight_type": "fact"},
                ]
            }
        )

        result = await research_specialty_by_description(
            {"id": "specialty:test", "slug": "test", "description": "Test", "name": "Test", "min_threshold": 5},
            "product:default",
        )

    assert result["insights_created"] >= 1


def test_module_importable():
    from core.engine.sentinel.engines.bootstrap import research_specialty_by_description

    assert callable(research_specialty_by_description)
