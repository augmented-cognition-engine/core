"""Unit tests for engine.foresight.value_model.score_hypothetical_state."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_pool(rows: list[dict]):
    """Build a mock pool that returns `rows` for any db.query call."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[rows])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx
    return pool


@pytest.mark.asyncio
async def test_override_is_applied_not_ignored():
    """state_override replaces the score for matching capability IDs."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.4},
        {"capability": "capability:api", "dimension": "testing", "score": 0.5},
    ]
    pool = _make_pool(rows)

    result = await score_hypothetical_state(
        "product:platform",
        state_override={"capability:auth": 0.9},
        pool=pool,
    )

    assert result.capability_scores["capability:auth"] == pytest.approx(0.9)
    assert result.capability_scores["capability:api"] == pytest.approx(0.5)
    assert result.gap_score == pytest.approx(0.7)  # mean(0.9, 0.5)


@pytest.mark.asyncio
async def test_empty_override_returns_real_scores_unchanged():
    """Empty state_override returns real capability scores from DB."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.6},
        {"capability": "capability:api", "dimension": "testing", "score": 0.8},
    ]
    pool = _make_pool(rows)

    result = await score_hypothetical_state("product:platform", {}, pool=pool)

    assert result.gap_score == pytest.approx(0.7)  # mean(0.6, 0.8)
    assert result.top_risks == []  # neither is below 0.6


@pytest.mark.asyncio
async def test_top_risks_populated_for_low_scores():
    """Capabilities with post-override score < 0.6 appear in top_risks, ascending."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.3},
        {"capability": "capability:api", "dimension": "testing", "score": 0.5},
        {"capability": "capability:ui", "dimension": "testing", "score": 0.9},
    ]
    pool = _make_pool(rows)

    result = await score_hypothetical_state("product:platform", {}, pool=pool)

    assert result.top_risks == ["capability:auth", "capability:api"]  # ascending by score


@pytest.mark.asyncio
async def test_unknown_override_key_silently_ignored():
    """state_override key not present in DB has no effect."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.5},
    ]
    pool = _make_pool(rows)

    result = await score_hypothetical_state(
        "product:platform",
        state_override={"capability:nonexistent": 0.9},
        pool=pool,
    )

    assert result.gap_score == pytest.approx(0.5)
    assert result.capability_scores == {"capability:auth": pytest.approx(0.5)}


@pytest.mark.asyncio
async def test_empty_db_returns_zero_score():
    """No capability_quality rows → gap_score=0, empty collections."""
    from core.engine.foresight.value_model import score_hypothetical_state

    pool = _make_pool([])

    result = await score_hypothetical_state("product:platform", {}, pool=pool)

    assert result.gap_score == 0.0
    assert result.top_risks == []
    assert result.capability_scores == {}


@pytest.mark.asyncio
async def test_multiple_dimensions_per_capability_averaged():
    """When a capability has multiple dimension rows, score is their mean."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.4},
        {"capability": "capability:auth", "dimension": "security", "score": 0.8},
    ]
    pool = _make_pool(rows)

    result = await score_hypothetical_state("product:platform", {}, pool=pool)

    assert result.capability_scores["capability:auth"] == pytest.approx(0.6)  # mean(0.4, 0.8)
    assert result.gap_score == pytest.approx(0.6)
    assert result.top_risks == []  # 0.6 is not < 0.6


@pytest.mark.asyncio
async def test_override_score_clamped_to_unit_range():
    """Scores > 1.0 or < 0.0 in state_override are clamped to [0, 1]."""
    from core.engine.foresight.value_model import score_hypothetical_state

    rows = [
        {"capability": "capability:auth", "dimension": "testing", "score": 0.5},
    ]

    result_high = await score_hypothetical_state(
        "product:platform",
        state_override={"capability:auth": 1.5},
        pool=_make_pool(rows),
    )
    assert result_high.capability_scores["capability:auth"] == pytest.approx(1.0)

    result_low = await score_hypothetical_state(
        "product:platform",
        state_override={"capability:auth": -0.5},
        pool=_make_pool(rows),
    )
    assert result_low.capability_scores["capability:auth"] == pytest.approx(0.0)
