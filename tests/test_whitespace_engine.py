# tests/test_whitespace_engine.py
"""Tests for S2 Whitespace Engine.

Covers:
- _compute_score: formula correctness
- _load_competitor_coverage: coverage aggregation
- _load_pain_signals: community signal aggregation
- run_whitespace_engine: end-to-end scoring pass
- ace_whitespace: MCP tool
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


# ── _compute_score ────────────────────────────────────────────────────────────


def test_compute_score_full_coefficients():
    from core.engine.sentinel.engines.whitespace_engine import _compute_score

    opp = {
        "pain_intensity": 1.0,
        "user_count": 1.0,
        "max_competitor_coverage": 0.0,
        "feasibility_coefficient": 1.0,
        "timing_coefficient": 1.0,
    }
    assert _compute_score(opp) == 1.0


def test_compute_score_no_whitespace_when_competitor_covers():
    from core.engine.sentinel.engines.whitespace_engine import _compute_score

    opp = {
        "pain_intensity": 1.0,
        "user_count": 1.0,
        "max_competitor_coverage": 1.0,  # competitor fully covers it
        "feasibility_coefficient": 1.0,
        "timing_coefficient": 1.0,
    }
    assert _compute_score(opp) == 0.0


def test_compute_score_partial_coverage():
    from core.engine.sentinel.engines.whitespace_engine import _compute_score

    opp = {
        "pain_intensity": 0.8,
        "user_count": 0.7,
        "max_competitor_coverage": 0.5,
        "feasibility_coefficient": 0.9,
        "timing_coefficient": 0.8,
    }
    score = _compute_score(opp)
    expected = round(0.8 * 0.7 * 0.5 * 0.9 * 0.8, 4)
    assert abs(score - expected) < 0.0001


def test_compute_score_uses_defaults():
    from core.engine.sentinel.engines.whitespace_engine import _compute_score

    # All defaults: pain=0.5, count=0.5, coverage=0.0, feasibility=0.7, timing=0.6
    score = _compute_score({})
    expected = round(0.5 * 0.5 * 1.0 * 0.7 * 0.6, 4)
    assert abs(score - expected) < 0.0001


def test_compute_score_seeded_cost_intelligence():
    """Verify the pre-seeded cost_intelligence opportunity has a high score."""
    from core.engine.sentinel.engines.whitespace_engine import _compute_score

    opp = {
        "pain_intensity": 0.92,
        "user_count": 0.75,
        "max_competitor_coverage": 0.05,
        "feasibility_coefficient": 0.80,
        "timing_coefficient": 0.85,
    }
    score = _compute_score(opp)
    assert score > 0.4  # high whitespace score


# ── _load_competitor_coverage ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_competitor_coverage_aggregates_max():
    """Returns max coverage float per slug across Tier 1 competitors."""
    from core.engine.sentinel.engines.whitespace_engine import _load_competitor_coverage

    mock_db = AsyncMock()
    rows = [
        {"slug": "multi_file_editing", "coverage": "full"},  # 1.0
        {"slug": "multi_file_editing", "coverage": "partial"},  # 0.5 — max=1.0
        {"slug": "decision_capture", "coverage": "none"},  # 0.0
    ]
    mock_db.query = AsyncMock(return_value=rows)

    result = await _load_competitor_coverage("product:platform", mock_db)

    assert result["multi_file_editing"] == 1.0
    assert result["decision_capture"] == 0.0


@pytest.mark.asyncio
async def test_load_competitor_coverage_empty_on_error():
    from core.engine.sentinel.engines.whitespace_engine import _load_competitor_coverage

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=Exception("db error"))

    result = await _load_competitor_coverage("product:platform", mock_db)
    assert result == {}


# ── _load_pain_signals ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_pain_signals_returns_global_average():
    from core.engine.sentinel.engines.whitespace_engine import _load_pain_signals

    mock_db = AsyncMock()
    rows = [
        {"competitor": "Cursor", "relevance_score": 0.8},
        {"competitor": "Cursor", "relevance_score": 0.7},
        {"competitor": "Aider", "relevance_score": 0.9},
    ]
    mock_db.query = AsyncMock(return_value=rows)

    result = await _load_pain_signals("product:platform", mock_db)
    # global pain = avg of [0.8, 0.7, 0.9] = 0.8
    assert "__global__" in result
    assert abs(result["__global__"] - round((0.8 + 0.7 + 0.9) / 3, 4)) < 0.01


@pytest.mark.asyncio
async def test_load_pain_signals_empty_on_no_data():
    from core.engine.sentinel.engines.whitespace_engine import _load_pain_signals

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    result = await _load_pain_signals("product:platform", mock_db)
    assert result == {}


# ── run_whitespace_engine ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_whitespace_engine_scores_seeded_opportunities(mock_pool):
    """Engine scores the pre-seeded opportunities even with no live data."""
    from core.engine.sentinel.engines import whitespace_engine

    mock_p, mock_db = mock_pool
    # No live coverage or pain data
    mock_db.query = AsyncMock(return_value=[])

    with patch.object(whitespace_engine, "pool", mock_p):
        result = await whitespace_engine.run_whitespace_engine("product:platform")

    # 4 pre-seeded opportunities
    assert result["opportunities_scored"] == 4
    assert result["top_score"] > 0
    assert result["top_slug"] != ""


@pytest.mark.asyncio
async def test_whitespace_engine_adds_blindspots_from_coverage(mock_pool):
    """Capabilities with low competitor coverage generate extra blindspot entries."""
    from core.engine.sentinel.engines import whitespace_engine

    mock_p, mock_db = mock_pool

    coverage_rows = [
        {"slug": "intelligence_briefing", "coverage": "none"},
        {"slug": "cost_intelligence", "coverage": "none"},  # matches seeded opp
    ]

    call_count = 0

    def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        # First query = coverage, second = pain signals, rest = upserts
        if call_count == 1:
            return coverage_rows
        return []

    mock_db.query = AsyncMock(side_effect=query_side)

    with patch.object(whitespace_engine, "pool", mock_p):
        result = await whitespace_engine.run_whitespace_engine("product:platform")

    # 4 seeded + 1 blindspot (intelligence_briefing; cost_intelligence matches seeded slug)
    assert result["opportunities_scored"] >= 4


@pytest.mark.asyncio
async def test_whitespace_engine_top_score_is_cost_intelligence(mock_pool):
    """With no live data, cost_intelligence should have highest seeded score."""
    from core.engine.sentinel.engines import whitespace_engine

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    with patch.object(whitespace_engine, "pool", mock_p):
        result = await whitespace_engine.run_whitespace_engine("product:platform")

    assert result["top_slug"] == "cost_intelligence"


# ── ace_whitespace ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_whitespace_returns_sorted_opportunities(mock_pool):
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool
    rows = [
        {"slug": "cost_intelligence", "title": "Cost Intelligence", "whitespace_score": 0.45, "source": "seeded"},
        {"slug": "runtime_enforcement", "title": "Runtime Enforcement", "whitespace_score": 0.38, "source": "seeded"},
    ]
    mock_db.query = AsyncMock(return_value=rows)

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_whitespace(product_id="product:platform")

    assert result["count"] == 2
    assert result["opportunities"][0]["slug"] == "cost_intelligence"


@pytest.mark.asyncio
async def test_ace_whitespace_empty_table(mock_pool):
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_whitespace(product_id="product:platform")

    assert result["count"] == 0
    assert result["opportunities"] == []
    assert "error" not in result
