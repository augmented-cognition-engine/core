# tests/test_strategic_prioritizer.py
"""Tests for S4 StrategicPrioritizer — 5-dimension strategic scoring.

Covers:
- _strategic_score: formula correctness for each dimension
- _load_whitespace / _load_signal_density: DB helpers
- StrategicPrioritizer.prioritize: end-to-end scoring with enrichment data
- ace_recommend: innovation gate + mode routing
- ace_briefing: pm_central overlay structure
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


# ── _strategic_score formula ─────────────────────────────────────────────────


def test_strategic_score_all_dimensions_present():
    """With full enrichment data, score should reflect all 5 dimensions."""
    from core.engine.product.strategic_prioritizer import _strategic_score

    gap = {"score": 0.2, "gaps": ["g1", "g2", "g3", "g4", "g5"]}  # 5 gaps = leverage=1.0
    cap = {"slug": "test_cap", "priority": "critical"}
    ws_data = {
        "pain_intensity": 0.9,
        "timing_coefficient": 0.8,
        "whitespace_score": 0.45,
    }

    score, dimensions = _strategic_score(gap, cap, ws_data, signal_score=0.7, leverage=1.0)

    assert score > 0.5, "High-quality gap with strong enrichment should score above 0.5"
    assert "gap_severity" in dimensions
    assert "defensibility" in dimensions
    assert "market_timing" in dimensions
    assert "leverage" in dimensions
    assert "compounding" in dimensions
    # gap_severity = 1.0 - 0.2 = 0.8
    assert abs(dimensions["gap_severity"] - 0.8) < 0.01


def test_strategic_score_no_enrichment_uses_defaults():
    """With no whitespace data, score should fall back to safe defaults."""
    from core.engine.product.strategic_prioritizer import _strategic_score

    gap = {"score": 0.4, "gaps": []}
    cap = {"slug": "basic_cap", "priority": "important"}

    score, dimensions = _strategic_score(gap, cap, ws_data={}, signal_score=0.0, leverage=0.0)

    assert 0.0 < score < 1.0
    assert dimensions["gap_severity"] == round(1.0 - 0.4, 3)
    assert dimensions["leverage"] == 0.0
    assert dimensions["compounding"] == 0.0


def test_strategic_score_weights_sum_to_one():
    """The STRATEGIC_WEIGHTS must sum to 1.0."""
    from core.engine.product.strategic_prioritizer import STRATEGIC_WEIGHTS

    total = sum(STRATEGIC_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


def test_strategic_score_market_timing_uses_max_of_ws_and_signals():
    """market_timing = max(ws_timing, signal_score) so either can drive urgency."""
    from core.engine.product.strategic_prioritizer import _strategic_score

    gap = {"score": 0.5, "gaps": []}
    cap = {}

    # Low ws_timing but high signal score
    _, dims_signal = _strategic_score(
        gap,
        cap,
        ws_data={"timing_coefficient": 0.2, "whitespace_score": 0.0, "pain_intensity": 0.5},
        signal_score=0.9,
        leverage=0.0,
    )
    assert dims_signal["market_timing"] == 0.9

    # High ws_timing, no signals
    _, dims_ws = _strategic_score(
        gap,
        cap,
        ws_data={"timing_coefficient": 0.85, "whitespace_score": 0.0, "pain_intensity": 0.5},
        signal_score=0.0,
        leverage=0.0,
    )
    assert dims_ws["market_timing"] == 0.85


def test_strategic_score_clamped_to_unit_interval():
    """All dimension scores should be in [0, 1]."""
    from core.engine.product.strategic_prioritizer import _strategic_score

    gap = {"score": -0.5, "gaps": ["g"] * 20}  # bad data
    cap = {}
    ws_data = {
        "pain_intensity": 1.5,  # out of range
        "timing_coefficient": 2.0,
        "whitespace_score": -0.3,
    }

    score, dimensions = _strategic_score(gap, cap, ws_data, signal_score=5.0, leverage=10.0)

    for k, v in dimensions.items():
        assert 0.0 <= v <= 1.0, f"Dimension {k}={v} out of [0,1]"
    assert 0.0 <= score <= 1.0


# ── _load_whitespace ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_whitespace_returns_slug_keyed_dict():
    from core.engine.product.strategic_prioritizer import _load_whitespace

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"slug": "cost_intelligence", "pain_intensity": 0.92, "timing_coefficient": 0.85, "whitespace_score": 0.45},
            {"slug": "runtime_enforcement", "pain_intensity": 0.75, "timing_coefficient": 0.7, "whitespace_score": 0.3},
        ]
    )

    result = await _load_whitespace("product:platform", mock_db)

    assert "cost_intelligence" in result
    assert result["cost_intelligence"]["pain_intensity"] == 0.92
    assert "runtime_enforcement" in result


@pytest.mark.asyncio
async def test_load_whitespace_returns_empty_on_error():
    from core.engine.product.strategic_prioritizer import _load_whitespace

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=Exception("db error"))

    result = await _load_whitespace("product:platform", mock_db)
    assert result == {}


# ── _load_signal_density ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_signal_density_normalizes_count():
    from core.engine.product.strategic_prioritizer import _load_signal_density

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"title": "Multi File Editing", "signal_count": 10},  # capped at 1.0
            {"title": "Cost Intelligence", "signal_count": 2},  # 0.4
        ]
    )

    result = await _load_signal_density("product:platform", mock_db)

    assert result.get("multi_file_editing") == 1.0
    assert abs(result.get("cost_intelligence", 0) - 0.4) < 0.01


@pytest.mark.asyncio
async def test_load_signal_density_empty_on_error():
    from core.engine.product.strategic_prioritizer import _load_signal_density

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=Exception("query failed"))

    result = await _load_signal_density("product:platform", mock_db)
    assert result == {}


# ── StrategicPrioritizer.prioritize ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategic_prioritizer_returns_dimensions(mock_pool):
    """Scored items include per-dimension breakdown."""
    from core.engine.product.strategic_prioritizer import StrategicPrioritizer

    mock_p, mock_db = mock_pool

    capabilities = [{"id": "capability:auth", "slug": "auth", "priority": "critical", "status": "active"}]
    gaps = [
        {
            "capability": "capability:auth",
            "dimension": "security",
            "score": 0.3,
            "gaps": ["gap1", "gap2"],
        }
    ]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return capabilities
        if call_count == 2:
            return gaps
        return []  # whitespace + signal queries

    mock_db.query = AsyncMock(side_effect=query_side)

    prioritizer = StrategicPrioritizer(mock_p)
    results = await prioritizer.prioritize("product:platform")

    assert len(results) == 1
    item = results[0]
    assert item["capability_slug"] == "auth"
    assert "dimensions" in item
    assert "gap_severity" in item["dimensions"]
    assert item["dimensions"]["gap_severity"] == round(1.0 - 0.3, 3)


@pytest.mark.asyncio
async def test_strategic_prioritizer_sorts_by_score(mock_pool):
    """Items are sorted descending by priority_score."""
    from core.engine.product.strategic_prioritizer import StrategicPrioritizer

    mock_p, mock_db = mock_pool

    capabilities = [
        {"id": "capability:auth", "slug": "auth", "priority": "nice_to_have", "status": "active"},
        {"id": "capability:api", "slug": "api", "priority": "critical", "status": "active"},
    ]
    gaps = [
        {"capability": "capability:auth", "dimension": "security", "score": 0.55, "gaps": []},
        {"capability": "capability:api", "dimension": "testing", "score": 0.1, "gaps": ["g1", "g2", "g3"]},
    ]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return capabilities
        if call_count == 2:
            return gaps
        return []

    mock_db.query = AsyncMock(side_effect=query_side)

    prioritizer = StrategicPrioritizer(mock_p)
    results = await prioritizer.prioritize("product:platform")

    assert len(results) == 2
    assert results[0]["priority_score"] >= results[1]["priority_score"]
    # api (score=0.1, 3 gaps, critical) should rank higher than auth (score=0.55, 0 gaps, nice_to_have)
    assert results[0]["capability_slug"] == "api"


@pytest.mark.asyncio
async def test_strategic_prioritizer_raises_database_error_on_failure(mock_pool):
    """DB failure raises DatabaseError, not a raw exception."""
    from core.engine.core.exceptions import DatabaseError
    from core.engine.product.strategic_prioritizer import StrategicPrioritizer

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(side_effect=Exception("connection refused"))

    prioritizer = StrategicPrioritizer(mock_p)
    with pytest.raises(DatabaseError):
        await prioritizer.prioritize("product:platform")


@pytest.mark.asyncio
async def test_strategic_prioritizer_invalid_product_id(mock_pool):
    """Malformed product_id raises ValidationError before hitting DB."""
    from core.engine.core.exceptions import ValidationError
    from core.engine.product.strategic_prioritizer import StrategicPrioritizer

    mock_p, _ = mock_pool
    prioritizer = StrategicPrioritizer(mock_p)

    with pytest.raises(ValidationError):
        await prioritizer.prioritize("bad_id_no_colon")


# ── ace_recommend: innovation gate ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_recommend_returns_mode_gap_driven(mock_pool):
    """When gaps exist, mode is 'gap_driven' with strategic recommendations."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool

    capabilities = [{"id": "capability:auth", "slug": "auth", "priority": "critical", "status": "active"}]
    gaps = [{"capability": "capability:auth", "dimension": "testing", "score": 0.2, "gaps": ["g1"]}]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return capabilities
        if call_count == 2:
            return gaps
        return []

    mock_db.query = AsyncMock(side_effect=query_side)

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_recommend(product_id="product:platform")

    assert result["mode"] == "gap_driven"
    assert len(result["recommendations"]) == 1
    assert "dimensions" in result["recommendations"][0]


@pytest.mark.asyncio
async def test_ace_recommend_returns_mode_innovate_when_no_gaps(mock_pool):
    """When no gaps exist, mode is 'innovate' with whitespace preview."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool

    ws_preview = [
        {"slug": "cost_intelligence", "title": "Cost Intelligence", "whitespace_score": 0.45},
    ]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []  # no capabilities → no gaps
        if call_count == 2:
            return []  # no gaps
        # whitespace preview query
        return ws_preview

    mock_db.query = AsyncMock(side_effect=query_side)

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_recommend(product_id="product:platform")

    assert result["mode"] == "innovate"
    assert result["recommendations"] == []
    assert "message" in result
    assert "whitespace_preview" in result


@pytest.mark.asyncio
async def test_ace_recommend_error_returns_empty():
    """DB failure returns safe empty result, not an exception."""
    from core.engine.mcp import tools

    mock_p = MagicMock()
    mock_conn = MagicMock()
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=Exception("db down"))
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p.connection.return_value = mock_conn

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_recommend(product_id="product:platform")

    assert "error" in result
    assert result["recommendations"] == []


# ── ace_briefing: pm_central overlay ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_briefing_includes_pm_central(mock_pool):
    """ace_briefing response always includes pm_central dict."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool

    briefing_row = {
        "content": "ACE Intelligence Briefing",
        "period": "weekly",
        "created_at": "2026-04-12T06:00:00Z",
        "metrics": {},
    }

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [briefing_row]  # briefing query
        return []  # pm_central sub-queries

    mock_db.query = AsyncMock(side_effect=query_side)

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_briefing(product_id="product:platform")

    assert result["available"] is True
    assert "pm_central" in result
    assert "market_moves" in result["pm_central"]
    assert "whitespace" in result["pm_central"]
    assert "product_health" in result["pm_central"]
    assert "next_30_days" in result["pm_central"]


@pytest.mark.asyncio
async def test_ace_briefing_pm_central_market_moves(mock_pool):
    """PM Central market_moves contains recent competitive signals."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool

    briefing_row = {"content": "Briefing", "period": "weekly", "created_at": "", "metrics": {}}
    signal_rows = [
        {
            "competitor": "cursor:cursor",
            "title": "Cursor 3.0 released",
            "signal_type": "release",
            "created_at": "2026-04-12",
        },
    ]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [briefing_row]
        if call_count == 2:
            return signal_rows  # market_moves query
        return []

    mock_db.query = AsyncMock(side_effect=query_side)

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_briefing(product_id="product:platform")

    moves = result["pm_central"]["market_moves"]
    assert len(moves) == 1
    assert moves[0]["summary"] == "Cursor 3.0 released"


@pytest.mark.asyncio
async def test_ace_briefing_no_briefing_still_has_pm_central(mock_pool):
    """Even when no briefing exists, pm_central is still returned."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_briefing(product_id="product:platform")

    assert result["available"] is False
    assert "pm_central" in result
    assert isinstance(result["pm_central"], dict)
