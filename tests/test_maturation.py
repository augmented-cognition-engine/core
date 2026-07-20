# tests/test_maturation.py
from unittest.mock import AsyncMock, patch

import pytest


def test_score_nascent():
    """Minimal metrics → Nascent phase."""
    from core.engine.intelligence.maturation import MaturationPhase, score_specialty

    metrics = {
        "insight_count": 2,
        "avg_confidence": 0.3,
        "verified_corrections": 0,
        "synapse_count": 0,
        "successful_tasks": 0,
        "verified_ratio": 0.0,
        "custom_skills": 0,
        "playbooks": 0,
        "domain_skills_used": 0,
    }
    result = score_specialty(metrics)
    assert result.phase == MaturationPhase.NASCENT
    assert result.score < 25


def test_score_forming():
    """Moderate metrics → Forming phase."""
    from core.engine.intelligence.maturation import MaturationPhase, score_specialty

    metrics = {
        "insight_count": 10,
        "avg_confidence": 0.6,
        "verified_corrections": 1,
        "synapse_count": 1,
        "successful_tasks": 5,
        "verified_ratio": 0.3,
        "custom_skills": 0,
        "playbooks": 0,
        "domain_skills_used": 0,
    }
    result = score_specialty(metrics)
    assert result.phase == MaturationPhase.FORMING
    assert 25 <= result.score < 45


def test_score_reliable():
    """Strong metrics → Reliable phase."""
    from core.engine.intelligence.maturation import MaturationPhase, score_specialty

    metrics = {
        "insight_count": 25,
        "avg_confidence": 0.75,
        "verified_corrections": 3,
        "synapse_count": 3,
        "successful_tasks": 15,
        "verified_ratio": 0.5,
        "custom_skills": 0,
        "playbooks": 0,
        "domain_skills_used": 1,
    }
    result = score_specialty(metrics)
    assert result.phase == MaturationPhase.RELIABLE
    assert 45 <= result.score < 65


def test_weighted_phase():
    """Weighted average of child phases."""
    from core.engine.intelligence.maturation import MaturationPhase, weighted_phase

    children = [
        (MaturationPhase.EXPERT, 20),  # 4 * 20 = 80
        (MaturationPhase.FORMING, 10),  # 2 * 10 = 20
        (MaturationPhase.NASCENT, 5),  # 1 * 5  = 5
    ]
    # Weighted avg: (80 + 20 + 5) / 35 = 3.0 → RELIABLE
    result = weighted_phase(children)
    assert result == MaturationPhase.RELIABLE


@pytest.mark.asyncio
async def test_calculate_maturation_caches():
    """calculate_maturation uses cache when fresh."""
    from core.engine.intelligence.maturation import calculate_maturation

    cached = {
        "phase": 2,
        "phase_name": "forming",
        "score": 32,
        "metrics": {},
        "calculated_at": "2026-03-21T12:00:00Z",
    }

    with patch("core.engine.intelligence.maturation.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[cached]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.intelligence.maturation._is_fresh", return_value=True):
            result = await calculate_maturation("specialty", "specialty:abc", "product:test")

    assert result["phase"] == 2
    assert result["phase_name"] == "forming"


@pytest.mark.asyncio
async def test_calculate_maturation_cache_miss():
    """calculate_maturation calculates fresh when cache is stale/empty."""
    from core.engine.intelligence.maturation import calculate_maturation

    with patch("core.engine.intelligence.maturation.pool") as mock_pool:
        mock_conn = AsyncMock()
        # Empty cache
        mock_conn.query = AsyncMock(
            side_effect=[
                [[]],  # cache query returns empty
                # _get_specialty_metrics query
                [[{"insight_count": 5, "avg_confidence": 0.5, "verified_corrections": 0, "successful_tasks": 0}]],
                [[]],  # UPSERT query
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await calculate_maturation("specialty", "specialty:test", "product:test")

    assert result["phase"] == 1  # NASCENT (ic=5→3pts; ac=0.5→6pts; all others 0; total=9 < 25)
    assert "phase_name" in result
    assert "score" in result
