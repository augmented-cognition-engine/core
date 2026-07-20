# tests/test_innovate.py
"""Tests for S3 ace_innovate — The No-Gap Engine.

Covers:
- run_innovate_mode: single mode execution + LLM response parsing
- run_all_modes: aggregation across 4 modes
- ace_innovate MCP tool: routing + error handling
"""

from unittest.mock import AsyncMock, patch

import pytest

# ── run_innovate_mode ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_innovate_frontier_returns_capabilities():
    from core.engine.product.innovate import run_innovate_mode

    llm_response = {
        "capabilities": [
            {
                "title": "Semantic Code Smell Detection",
                "description": "Uses embeddings to detect architectural drift before it compounds.",
                "source_domain": "research",
                "ace_application": "Weekly embedding diff against baseline graph",
                "impact_score": 0.82,
            }
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value=llm_response)

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_innovate_mode("frontier")

    assert result["mode"] == "frontier"
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Semantic Code Smell Detection"
    assert "error" not in result


@pytest.mark.asyncio
async def test_innovate_cross_domain_returns_patterns():
    from core.engine.product.innovate import run_innovate_mode

    llm_response = {
        "patterns": [
            {
                "industry": "Aviation",
                "pattern": "Pre-flight checklist",
                "ace_feature": "ace_preflight",
                "ace_description": "Run discipline checks before any deploy.",
                "implementation_hint": "Hook into CD pipeline",
                "compounding": True,
            }
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value=llm_response)

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_innovate_mode("cross_domain")

    assert result["count"] == 1
    assert result["results"][0]["ace_feature"] == "ace_preflight"


@pytest.mark.asyncio
async def test_innovate_emerging_tech_returns_capabilities():
    from core.engine.product.innovate import run_innovate_mode

    llm_response = {
        "capabilities": [
            {
                "trend": "1M token context",
                "ace_capability": "Hold entire codebase in active context",
                "implementation": "Full-file graph embedding pass",
                "activation_threshold": "1M tokens",
                "time_horizon": "now",
                "impact": 0.9,
            }
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value=llm_response)

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_innovate_mode("emerging_tech")

    assert result["count"] == 1
    assert result["results"][0]["time_horizon"] == "now"


@pytest.mark.asyncio
async def test_innovate_compounding_returns_compounds():
    from core.engine.product.innovate import run_innovate_mode

    llm_response = {
        "compounds": [
            {
                "feature_a": "ace_decisions",
                "feature_b": "ace_blast_radius",
                "data_flow": "Decision history enriches blast radius context",
                "compound_rate": "weekly",
                "current_gap": "blast_radius doesn't query decision history",
                "implementation": "Join decision table in blast_radius query",
            }
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value=llm_response)

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_innovate_mode("compounding")

    assert result["count"] == 1
    assert result["results"][0]["feature_a"] == "ace_decisions"


@pytest.mark.asyncio
async def test_innovate_unknown_mode_returns_error():
    from core.engine.product.innovate import run_innovate_mode

    result = await run_innovate_mode("bogus_mode")
    assert "error" in result
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_innovate_llm_failure_returns_empty():
    from core.engine.product.innovate import run_innovate_mode

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM timeout"))

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_innovate_mode("frontier")

    assert "error" in result
    assert result["count"] == 0
    assert result["results"] == []


# ── run_all_modes ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_all_modes_aggregates_count():
    from core.engine.product.innovate import run_all_modes

    frontier_resp = {"capabilities": [{"title": "A", "impact_score": 0.7}]}
    cross_resp = {"patterns": [{"industry": "Aviation", "ace_feature": "ace_preflight"}]}
    emerging_resp = {"capabilities": [{"trend": "1M ctx", "impact": 0.9}]}
    compound_resp = {"compounds": [{"feature_a": "decisions", "feature_b": "blast_radius"}]}

    responses = [frontier_resp, cross_resp, emerging_resp, compound_resp]
    call_idx = 0

    async def mock_complete_json(prompt):
        nonlocal call_idx
        r = responses[call_idx % len(responses)]
        call_idx += 1
        return r

    mock_llm = AsyncMock()
    mock_llm.complete_json = mock_complete_json

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_all_modes()

    assert "modes" in result
    assert result["total_count"] == 4  # 1 per mode
    assert result["top_impact"] >= 0.7


@pytest.mark.asyncio
async def test_run_all_modes_includes_all_four():
    from core.engine.product.innovate import run_all_modes

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={})

    with patch("core.engine.product.innovate.get_llm", return_value=mock_llm):
        result = await run_all_modes()

    assert set(result["modes"].keys()) == {"frontier", "cross_domain", "emerging_tech", "compounding"}


# ── ace_innovate MCP tool ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_innovate_all_mode():
    from core.engine.mcp import tools

    expected = {"modes": {"frontier": {"count": 1}}, "total_count": 1, "top_impact": 0.5}

    with patch("core.engine.product.innovate.run_all_modes", return_value=expected):
        result = await tools.ace_innovate(mode="all")

    assert result["total_count"] == 1
    assert "modes" in result


@pytest.mark.asyncio
async def test_ace_innovate_single_mode():
    from core.engine.mcp import tools

    expected = {"mode": "frontier", "results": [], "count": 0}

    with patch("core.engine.product.innovate.run_innovate_mode", return_value=expected):
        result = await tools.ace_innovate(mode="frontier")

    assert result["mode"] == "frontier"


@pytest.mark.asyncio
async def test_ace_innovate_unknown_mode_returns_error():
    from core.engine.mcp import tools

    result = await tools.ace_innovate(mode="unknown_mode")
    assert "error" in result
