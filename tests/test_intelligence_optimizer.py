from unittest.mock import AsyncMock, patch

import pytest


def test_optimizer_registered_with_correct_cron():
    import core.engine.sentinel.engines.intelligence_optimizer  # noqa: F401
    from core.engine.sentinel.registry import get_engine

    entry = get_engine("intelligence_optimizer")
    assert entry is not None
    assert entry["cron"] == "0 4 * * *"


@pytest.mark.asyncio
async def test_optimizer_calls_compute_utilization_scores():
    from core.engine.sentinel.engines.intelligence_optimizer import run_intelligence_optimizer

    with (
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer.compute_utilization_scores",
            new_callable=AsyncMock,
            return_value={"updated": 5, "low_utilization_count": 1},
        ) as mock_util,
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer._aggregate_ab_results",
            new_callable=AsyncMock,
            return_value={"treatment": 3, "control": 1, "tie": 1, "total": 5, "intelligence_premium": 0.6},
        ),
        patch("core.engine.sentinel.engines.intelligence_optimizer.write_engine_insight", new_callable=AsyncMock),
        patch("core.engine.sentinel.engines.intelligence_optimizer.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_intelligence_optimizer("product:platform")

    mock_util.assert_called_once()
    assert result["utilization"]["updated"] == 5


@pytest.mark.asyncio
async def test_optimizer_aggregates_ab_results():
    from core.engine.sentinel.engines.intelligence_optimizer import run_intelligence_optimizer

    with (
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer.compute_utilization_scores",
            new_callable=AsyncMock,
            return_value={"updated": 0, "low_utilization_count": 0},
        ),
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer._aggregate_ab_results",
            new_callable=AsyncMock,
            return_value={"treatment": 14, "control": 4, "tie": 2, "total": 20, "intelligence_premium": 0.7},
        ) as mock_ab,
        patch("core.engine.sentinel.engines.intelligence_optimizer.write_engine_insight", new_callable=AsyncMock),
        patch("core.engine.sentinel.engines.intelligence_optimizer.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_intelligence_optimizer("product:platform")

    mock_ab.assert_called_once()
    assert result["ab"]["intelligence_premium"] == 0.7


@pytest.mark.asyncio
async def test_optimizer_writes_insight():
    from core.engine.sentinel.engines.intelligence_optimizer import run_intelligence_optimizer

    with (
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer.compute_utilization_scores",
            new_callable=AsyncMock,
            return_value={"updated": 3, "low_utilization_count": 0},
        ),
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer._aggregate_ab_results",
            new_callable=AsyncMock,
            return_value={"treatment": 10, "control": 5, "tie": 5, "total": 20, "intelligence_premium": 0.5},
        ),
        patch(
            "core.engine.sentinel.engines.intelligence_optimizer.write_engine_insight", new_callable=AsyncMock
        ) as mock_insight,
        patch("core.engine.sentinel.engines.intelligence_optimizer.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_intelligence_optimizer("product:platform")

    mock_insight.assert_called_once()
    call_kwargs = mock_insight.call_args[1]
    assert "intelligence_premium" in call_kwargs["content"] or "50%" in call_kwargs["content"]
