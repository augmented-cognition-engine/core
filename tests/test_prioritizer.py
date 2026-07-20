# tests/test_prioritizer.py
"""Tests for ProductPrioritizer — multi-dimensional scoring for work prioritization."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.fixture
def prioritizer(mock_pool):
    from core.engine.product.prioritizer import ProductPrioritizer

    return ProductPrioritizer(mock_pool)


# ---------------------------------------------------------------------------
# test_prioritizer_returns_sorted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prioritizer_returns_sorted(prioritizer, mock_db):
    """auth (critical priority, low quality score) ranks above ui (nice_to_have, high score)."""
    caps = [
        {"id": "capability:auth", "slug": "auth", "priority": "critical", "status": "built"},
        {"id": "capability:ui", "slug": "ui", "priority": "nice_to_have", "status": "built"},
    ]
    gaps = [
        {
            "id": "capability_quality:g1",
            "capability": "capability:auth",
            "dimension": "security",
            "score": 0.2,
            "gaps": ["no rate limiting", "no MFA"],
            "product": "product:test",
        },
        {
            "id": "capability_quality:g2",
            "capability": "capability:ui",
            "dimension": "accessibility",
            "score": 0.55,
            "gaps": ["missing aria labels"],
            "product": "product:test",
        },
    ]

    mock_db.query = AsyncMock(
        side_effect=[
            caps,  # capabilities
            gaps,  # capability_quality
        ]
    )

    result = await prioritizer.prioritize("product:test")

    assert len(result) == 2
    # auth (critical + low score) should outrank ui (nice_to_have + higher score)
    assert result[0]["capability_slug"] == "auth"
    assert result[1]["capability_slug"] == "ui"
    # Higher priority score first
    assert result[0]["priority_score"] > result[1]["priority_score"]


# ---------------------------------------------------------------------------
# test_prioritizer_empty_no_crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prioritizer_empty_no_crash(prioritizer, mock_db):
    """No capabilities, no gaps → returns empty list without error."""
    mock_db.query = AsyncMock(
        side_effect=[
            [],  # capabilities
            [],  # capability_quality
        ]
    )

    result = await prioritizer.prioritize("org:empty")

    assert result == []


# ---------------------------------------------------------------------------
# test_score_calculation
# ---------------------------------------------------------------------------


def test_score_calculation(prioritizer):
    """_score returns expected value for critical capability with low quality score."""
    from core.engine.product.prioritizer import PRIORITY_WEIGHTS

    # Verify weights are defined
    assert "critical" in PRIORITY_WEIGHTS
    assert "important" in PRIORITY_WEIGHTS
    assert "nice_to_have" in PRIORITY_WEIGHTS

    gap = {
        "score": 0.1,  # very low quality — high severity
        "dimension": "security",
        "gaps": ["vuln1", "vuln2", "vuln3"],
    }
    capability = {"priority": "critical"}

    score = prioritizer._score(gap, capability)

    # With critical priority + low score + 3 gaps, score must exceed 0.5
    assert score > 0.5

    # Verify components make sense
    # severity = 1.0 - 0.1 = 0.9  → 0.9 * 0.45 = 0.405
    # cap_priority = 1.0 (critical) → 1.0 * 0.35 = 0.35
    # blast_radius = min(1.0, 3/5) = 0.6 → 0.6 * 0.20 = 0.12
    # total = 0.405 + 0.35 + 0.12 = 0.875
    assert abs(score - 0.875) < 0.001
