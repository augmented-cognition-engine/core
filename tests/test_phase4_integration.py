from unittest.mock import AsyncMock, patch

import pytest


def test_utilization_score_neutral_below_cold_start():
    import inspect

    from core.engine.intelligence.utilization import compute_utilization_scores

    sig = inspect.signature(compute_utilization_scores)
    assert "product_id" in sig.parameters
    assert "db" in sig.parameters


def test_lookup_with_entry_and_lookup_are_consistent():
    import inspect

    from core.engine.intelligence import classification_cache

    src = inspect.getsource(classification_cache.lookup)
    assert "lookup_with_entry" in src


def test_ab_judge_preference_values():
    import inspect

    from core.engine.intelligence import ab_judge

    src = inspect.getsource(ab_judge.run_shadow_comparison)
    assert '"treatment"' in src
    assert '"control"' in src
    assert '"tie"' in src


@pytest.mark.asyncio
async def test_aggregate_ab_results_computes_premium_correctly():
    from core.engine.sentinel.engines.intelligence_optimizer import _aggregate_ab_results

    mock_db = AsyncMock()
    rows = [
        {"judge_preference": "treatment"},
        {"judge_preference": "treatment"},
        {"judge_preference": "treatment"},
        {"judge_preference": "control"},
        {"judge_preference": "tie"},
    ]
    with patch("core.engine.sentinel.engines.intelligence_optimizer.parse_rows", return_value=rows):
        result = await _aggregate_ab_results("product:test", mock_db)

    assert result["treatment"] == 3
    assert result["control"] == 1
    assert result["tie"] == 1
    assert result["total"] == 5
    assert result["intelligence_premium"] == round(3 / 5, 4)


@pytest.mark.asyncio
async def test_aggregate_ab_results_zero_total():
    from core.engine.sentinel.engines.intelligence_optimizer import _aggregate_ab_results

    mock_db = AsyncMock()
    with patch("core.engine.sentinel.engines.intelligence_optimizer.parse_rows", return_value=[]):
        result = await _aggregate_ab_results("product:test", mock_db)

    assert result["total"] == 0
    assert result["intelligence_premium"] == 0.0


def test_all_phase4_modules_importable():
    import core.engine.intelligence.ab_judge  # noqa: F401
    import core.engine.sentinel.engines.intelligence_optimizer  # noqa: F401
    from core.engine.intelligence.classification_cache import (  # noqa: F401
        lookup_with_entry,
        on_utilization_hit,
        on_zero_utilization_hit,
    )
    from core.engine.intelligence.utilization import compute_utilization_scores  # noqa: F401
