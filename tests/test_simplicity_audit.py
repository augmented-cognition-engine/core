# tests/test_simplicity_audit.py
"""Tests for Verification V2 — simplicity audit sentinel engine.

Tests:
1. Bootstrapping guard: skip when insufficient data
2. Dormancy detection: flag unused patterns, perspectives, archetypes
3. Complexity score calculation
4. Briefing integration: simplicity audit metrics aggregated
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_db_mock(*side_effects):
    """Flexible DB mock that returns [] after side effects exhausted."""
    effects = list(side_effects)

    async def _query(*args, **kwargs):
        if effects:
            return effects.pop(0)
        return []

    db = AsyncMock()
    db.query = AsyncMock(side_effect=_query)
    return db


# ---------------------------------------------------------------------------
# Bootstrapping guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_insufficient_data():
    """Engine skips when fewer than 50 orchestration runs exist."""
    mock_db = _make_db_mock(
        [{"cnt": 10}],  # total runs count
    )

    with patch("core.engine.sentinel.engines.simplicity_audit.pool") as mock_pool:
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        from core.engine.sentinel.engines.simplicity_audit import run_simplicity_audit

        result = await run_simplicity_audit("product:test")

    assert result["skipped"] is True
    assert "Insufficient data" in result["reason"]


# ---------------------------------------------------------------------------
# Dormancy detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_dormant_patterns():
    """Engine flags patterns with 0 runs in 90 days."""
    mock_db = _make_db_mock(
        [{"cnt": 100}],  # total runs — enough data
        [{"pattern": "independent", "cnt": 80}, {"pattern": "pipeline", "cnt": 20}],  # only 2 of 5 patterns used
        [],  # perspective signals (none)
        [],  # engine_run (none)
        [],  # archetype signals (none)
        # Pass 2 queries will return [] via flexible mock
    )

    with (
        patch("core.engine.sentinel.engines.simplicity_audit.pool") as mock_pool,
        patch("core.engine.sentinel.engines.simplicity_audit.get_llm") as mock_llm_factory,
        patch("core.engine.sentinel.registry.list_engines", return_value=[]),
    ):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(
            return_value=[
                {
                    "component": "adversarial",
                    "action": "deprecate",
                    "reason": "0 runs in 90 days",
                    "impact": "Remove ~200 lines",
                }
            ]
        )
        mock_llm_factory.return_value = mock_llm

        from core.engine.sentinel.engines.simplicity_audit import run_simplicity_audit

        result = await run_simplicity_audit("product:test")

    assert result["dormant_count"] > 0
    dormant_components = [d["component"] for d in result["dormant"]]
    # adversarial, fanout, team should be dormant (independent + pipeline are active)
    assert "adversarial" in dormant_components
    assert "fanout" in dormant_components
    assert "team" in dormant_components


# ---------------------------------------------------------------------------
# Complexity score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complexity_score_calculation():
    """Complexity score = (total - justified) / total."""
    mock_db = _make_db_mock(
        [{"cnt": 100}],  # enough data
        [{"pattern": "independent", "cnt": 90}],  # only 1 pattern used
        [],  # no perspective signals
        [],  # no engine runs
        [],  # no archetype signals
    )

    with (
        patch("core.engine.sentinel.engines.simplicity_audit.pool") as mock_pool,
        patch("core.engine.sentinel.engines.simplicity_audit.get_llm") as mock_llm_factory,
        patch("core.engine.sentinel.registry.list_engines", return_value=[]),
    ):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_db)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.connection.return_value = cm

        mock_llm = MagicMock()
        mock_llm.complete_json = AsyncMock(return_value=[])
        mock_llm_factory.return_value = mock_llm

        from core.engine.sentinel.engines.simplicity_audit import run_simplicity_audit

        result = await run_simplicity_audit("product:test")

    # With 15 total components (5 patterns + 4 perspectives + 6 archetypes)
    # and very few justified, complexity score should be > 0
    assert result["complexity_score"] > 0
    assert result["complexity_score"] <= 1.0


# ---------------------------------------------------------------------------
# Briefing integration
# ---------------------------------------------------------------------------


def test_briefing_aggregates_simplicity_audit():
    """Briefing engine aggregates simplicity audit metrics."""
    from core.engine.sentinel.engines.briefing import aggregate_engine_results

    runs = [
        {
            "engine": "simplicity_audit",
            "results": {
                "dormant_count": 5,
                "low_value_count": 2,
                "complexity_score": 0.35,
                "recommendations": [{"component": "adversarial", "action": "deprecate"}],
            },
        },
    ]

    metrics = aggregate_engine_results(runs)
    assert metrics["simplicity_dormant"] == 5
    assert metrics["simplicity_low_value"] == 2
    assert metrics["simplicity_score"] == 0.35
    assert len(metrics["simplicity_recommendations"]) == 1
