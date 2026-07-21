"""Tests for intelligence maturation scoring — lives in tests/observability/.

Extends tests/test_maturation.py (which covers NASCENT/FORMING/RELIABLE).
This file covers EXPERT, AUTHORITATIVE, synapse_count wiring, and aggregate rollup.
"""

import pytest

# ── Phase threshold coverage ──────────────────────────────────────────────────


def test_score_expert():
    """Metrics in the 65-84 range → EXPERT phase."""
    from core.engine.intelligence.maturation import MaturationPhase, score_specialty

    metrics = {
        "insight_count": 36,  # 20pts (≥36)
        "avg_confidence": 0.9,  # 20pts (≥0.9)
        "verified_corrections": 3,  # 10pts (≥3)
        "synapse_count": 3,  # 7pts  (≥3)
        "successful_tasks": 10,  # 8pts  (≥10)
        "verified_ratio": 0.3,  # 4pts  (≥0.3)
        "custom_skills": 0,
        "playbooks": 0,
        "domain_skills_used": 0,  # 0pts
    }
    # Total: 20+20+10+7+8+4+0 = 69 → EXPERT
    result = score_specialty(metrics)
    assert result.phase == MaturationPhase.EXPERT
    assert 65 <= result.score < 85


def test_score_authoritative():
    """Maximum metrics → AUTHORITATIVE phase (score=100)."""
    from core.engine.intelligence.maturation import MaturationPhase, score_specialty

    metrics = {
        "insight_count": 75,  # 25pts (≥75)
        "avg_confidence": 0.9,  # 20pts (≥0.9)
        "verified_corrections": 5,  # 15pts (≥5)
        "synapse_count": 5,  # 10pts (≥5)
        "successful_tasks": 50,  # 15pts (≥50)
        "verified_ratio": 0.9,  # 10pts (≥0.9)
        "custom_skills": 0,
        "playbooks": 1,  # 5pts  (≥1)
        "domain_skills_used": 0,
    }
    # Total: 25+20+15+10+15+10+5 = 100 → AUTHORITATIVE
    result = score_specialty(metrics)
    assert result.phase == MaturationPhase.AUTHORITATIVE
    assert result.score >= 85


# ── synapse_count wiring ──────────────────────────────────────────────────────


def test_synapse_count_in_query():
    """_get_specialty_metrics query string references specialty_affinity table."""
    import inspect

    from core.engine.intelligence.maturation import _get_specialty_metrics

    source = inspect.getsource(_get_specialty_metrics)
    assert "specialty_affinity" in source
    assert "RETURN {" in source


@pytest.mark.asyncio
async def test_synapse_count_returned_from_db():
    """synapse_count is read from DB result, not hardcoded 0."""
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import _get_specialty_metrics

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    with patch(
        "core.engine.intelligence.maturation.parse_one",
        return_value={
            "synapse_count": 7,
            "insight_count": 10,
            "avg_confidence": 0.8,
            "verified_corrections": 3,
            "successful_tasks": 5,
        },
    ):
        result = await _get_specialty_metrics(mock_db, "specialty:sec", "product:test")

    assert result["synapse_count"] == 7


@pytest.mark.asyncio
async def test_empty_specialty_mean_normalizes_nan_to_zero():
    """SurrealDB 3.1 returns NaN for the mean of an empty subquery."""
    from math import nan
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import _get_specialty_metrics

    mock_db = AsyncMock()
    with patch(
        "core.engine.intelligence.maturation.parse_one",
        return_value={
            "insight_count": 0,
            "avg_confidence": nan,
            "verified_corrections": 0,
            "successful_tasks": 0,
            "synapse_count": 0,
        },
    ):
        result = await _get_specialty_metrics(mock_db, "specialty:empty", "product:test")

    assert result["avg_confidence"] == 0


# ── _calculate_aggregate() ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aggregate_empty_discipline():
    """No specialties in a discipline → NASCENT, score 0."""
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import MaturationPhase, _calculate_aggregate

    mock_db = AsyncMock()
    with patch("core.engine.intelligence.maturation.parse_rows", return_value=[]):
        result = await _calculate_aggregate(mock_db, "discipline", "security", "product:test")

    assert result.phase == MaturationPhase.NASCENT
    assert result.score == 0


@pytest.mark.asyncio
async def test_aggregate_no_cache_entry():
    """Specialty with no maturation cache entry → treated as NASCENT (phase 1, weight 1)."""
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import MaturationPhase, _calculate_aggregate

    specialties = [{"slug": "auth", "insight_count": 0}]
    mock_db = AsyncMock()

    call_count = 0

    def side_effect(coro):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return specialties  # specialty list
        return []  # no cache entry

    with patch("core.engine.intelligence.maturation.parse_rows", side_effect=side_effect):
        result = await _calculate_aggregate(mock_db, "discipline", "security", "product:test")

    # Single NASCENT specialty → phase NASCENT
    assert result.phase == MaturationPhase.NASCENT
    assert result.score == int(MaturationPhase.NASCENT) * 20


@pytest.mark.asyncio
async def test_aggregate_weighted_by_insight_count():
    """High-insight specialty dominates over low-insight specialty in weighted phase."""
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import MaturationPhase, _calculate_aggregate

    mock_db = AsyncMock()
    # specialty A: AUTHORITATIVE (phase 5), 75 insights
    # specialty B: NASCENT (phase 1), 1 insight
    # weighted avg = (5*75 + 1*1) / (75+1) = 376/76 ≈ 4.9 → rounds to AUTHORITATIVE
    specialties = [
        {"slug": "auth", "insight_count": 75},
        {"slug": "crypt", "insight_count": 1},
    ]
    cache_responses = [
        [{"phase": 5}],  # auth → AUTHORITATIVE
        [{"phase": 1}],  # crypt → NASCENT
    ]

    call_count = 0

    def side_effect(coro):
        nonlocal call_count
        if call_count == 0:
            call_count += 1
            return specialties
        idx = call_count - 1
        call_count += 1
        return cache_responses[idx] if idx < len(cache_responses) else []

    with patch("core.engine.intelligence.maturation.parse_rows", side_effect=side_effect):
        result = await _calculate_aggregate(mock_db, "discipline", "security", "product:test")

    assert result.phase == MaturationPhase.AUTHORITATIVE


@pytest.mark.asyncio
async def test_aggregate_product_level():
    """Product-level aggregation over disciplines works with weighted_phase."""
    from unittest.mock import AsyncMock, patch

    from core.engine.intelligence.maturation import MaturationPhase, _calculate_aggregate

    mock_db = AsyncMock()
    disc_rows = [
        {"disc": "discipline:security", "specialty_count": 5},
        {"disc": "discipline:testing", "specialty_count": 3},
    ]
    cache_responses = [
        [{"phase": 3}],  # security → RELIABLE
        [{"phase": 2}],  # testing → FORMING
    ]

    call_count = 0

    def side_effect(coro):
        nonlocal call_count
        if call_count == 0:
            call_count += 1
            return disc_rows
        idx = call_count - 1
        call_count += 1
        return cache_responses[idx] if idx < len(cache_responses) else []

    with patch("core.engine.intelligence.maturation.parse_rows", side_effect=side_effect):
        result = await _calculate_aggregate(mock_db, "product", "myproduct", "product:test")

    # weighted avg = (3*5 + 2*3) / (5+3) = 21/8 = 2.625 → rounds to RELIABLE (3)
    assert result.phase == MaturationPhase.RELIABLE
    assert result.score == int(MaturationPhase.RELIABLE) * 20
