"""Tests for engine/sentinel/engines/effectiveness_recomputer.py"""

from unittest.mock import AsyncMock, patch

import pytest


def test_effectiveness_recomputer_registered():
    """effectiveness_recomputer sentinel engine is registered with correct cron."""
    import core.engine.sentinel.engines.effectiveness_recomputer  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "effectiveness_recomputer" in engine_registry
    entry = engine_registry["effectiveness_recomputer"]
    assert entry["cron"] == "30 6,18 * * *"


@pytest.mark.asyncio
async def test_effectiveness_recomputer_calls_compute_and_persist():
    """run_effectiveness_recomputer calls compute_effectiveness_scores and persist_scores."""
    from core.engine.sentinel.engines.effectiveness_recomputer import run_effectiveness_recomputer

    fake_scores = [object(), object()]  # 2 dummy score objects

    with (
        patch(
            "core.engine.learning.effectiveness.compute_effectiveness_scores",
            new_callable=AsyncMock,
            return_value=fake_scores,
        ) as mock_compute,
        patch(
            "core.engine.learning.effectiveness.persist_scores",
            new_callable=AsyncMock,
        ) as mock_persist,
    ):
        result = await run_effectiveness_recomputer("product:platform")

    mock_compute.assert_called_once_with("product:platform")
    mock_persist.assert_called_once_with(fake_scores)
    assert result["scores_computed"] == 2
    assert result["product_id"] == "product:platform"


@pytest.mark.asyncio
async def test_effectiveness_recomputer_empty_scores():
    """run_effectiveness_recomputer with no observations returns scores_computed=0."""
    from core.engine.sentinel.engines.effectiveness_recomputer import run_effectiveness_recomputer

    with (
        patch(
            "core.engine.learning.effectiveness.compute_effectiveness_scores",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "core.engine.learning.effectiveness.persist_scores",
            new_callable=AsyncMock,
        ),
    ):
        result = await run_effectiveness_recomputer("product:platform")

    assert result["scores_computed"] == 0
