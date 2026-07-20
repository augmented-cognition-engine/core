# tests/test_mcp_server_formatting.py
"""Tests for ace_status / ace_briefing / ace_recommend server-layer formatters.

These tools used to return raw dicts (JSON blobs to Claude). They now return
formatted markdown strings. Tests verify the output is readable prose, not JSON.
"""

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# ace_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_status_no_initiatives():
    """Empty state returns a readable summary, not a JSON blob."""
    with patch(
        "core.engine.mcp.tools.ace_status",
        new=AsyncMock(
            return_value={
                "initiatives": [],
                "ideas_ready": 1,
                "pending_approvals": 0,
            }
        ),
    ):
        from core.engine.mcp.server import ace_status

        result = await ace_status()

    assert isinstance(result, str)
    assert "No active initiatives" in result
    assert "Ideas ready for review: 1" in result or "1" in result
    # Sentinel: must NOT look like JSON
    assert result.strip()[0] != "{"


@pytest.mark.asyncio
async def test_ace_status_with_initiatives():
    """Active initiatives are listed by name with dimension and blocked flag."""
    with patch(
        "core.engine.mcp.tools.ace_status",
        new=AsyncMock(
            return_value={
                "initiatives": [
                    {"title": "Add OllamaProvider", "discipline": "architecture", "status": "active"},
                    {"title": "SurrealDB isolation", "discipline": "data_modeling", "status": "blocked"},
                ],
                "ideas_ready": 2,
                "pending_approvals": 1,
            }
        ),
    ):
        from core.engine.mcp.server import ace_status

        result = await ace_status()

    assert "OllamaProvider" in result
    assert "SurrealDB isolation" in result
    assert "BLOCKED" in result
    assert "2" in result  # ideas_ready
    assert "1" in result  # pending_approvals
    assert result.strip()[0] != "{"


# ---------------------------------------------------------------------------
# ace_briefing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_briefing_not_available():
    """Returns a readable message when no briefing exists yet."""
    with patch(
        "core.engine.mcp.tools.ace_briefing",
        new=AsyncMock(
            return_value={
                "available": False,
                "content": None,
                "pm_central": {},
            }
        ),
    ):
        from core.engine.mcp.server import ace_briefing

        result = await ace_briefing()

    assert isinstance(result, str)
    assert "No briefing available" in result
    assert result.strip()[0] != "{"


@pytest.mark.asyncio
async def test_ace_briefing_formats_content_and_pm_central():
    """Briefing merges content + whitespace + health into readable markdown."""
    with patch(
        "core.engine.mcp.tools.ace_briefing",
        new=AsyncMock(
            return_value={
                "available": True,
                "content": "ACE Briefing — Week of April 11\n\n- Architecture: 0.6",
                "period": "weekly",
                "created_at": "2026-04-11T04:25:16Z",
                "metrics": {"engine_runs_summarized": 68, "total_active_insights": 9727},
                "pm_central": {
                    "whitespace": [
                        {
                            "slug": "cross_session_memory",
                            "title": "Cross-session architectural memory",
                            "whitespace_score": 0.42,
                        },
                        {
                            "slug": "cost_intelligence",
                            "title": "Cost Intelligence from code patterns",
                            "whitespace_score": 0.45,
                        },
                    ],
                    "product_health": [
                        {"dimension": "deployment", "avg_score": 0.16, "gap_count": 10},
                        {"dimension": "observability", "avg_score": 0.27, "gap_count": 44},
                    ],
                    "market_moves": [],
                    "next_30_days": [],
                },
            }
        ),
    ):
        from core.engine.mcp.server import ace_briefing

        result = await ace_briefing()

    assert isinstance(result, str)
    # Core content preserved
    assert "ACE Briefing" in result
    assert "Architecture" in result
    # Whitespace section rendered
    assert "Whitespace" in result
    assert "Cross-session architectural memory" in result
    assert "0.42" in result
    # Health section rendered
    assert "deployment" in result
    assert "0.16" in result
    # Sentinel: raw metrics blob must NOT appear
    assert "engine_runs_summarized" not in result
    assert "total_active_insights" not in result
    assert result.strip()[0] != "{"


# ---------------------------------------------------------------------------
# ace_recommend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_recommend_gap_driven():
    """Gap-driven mode formats top 5 recommendations as readable bullets."""
    with patch(
        "core.engine.mcp.tools.ace_recommend",
        new=AsyncMock(
            return_value={
                "mode": "gap_driven",
                "recommendations": [
                    {
                        "capability_slug": "specialty_emergence",
                        "dimension": "observability",
                        "current_score": 0,
                        "gaps": [
                            "No trace ID propagation",
                            "No structured JSON logging",
                            "No health check endpoints",
                            "No OpenTelemetry SDK",
                        ],
                        "priority_score": 0.61,
                    },
                    {
                        "capability_slug": "live_file_watching",
                        "dimension": "deployment",
                        "current_score": 0,
                        "gaps": ["No HEALTHCHECK instruction", "No rollback procedures"],
                        "priority_score": 0.61,
                    },
                ],
            }
        ),
    ):
        from core.engine.mcp.server import ace_recommend

        result = await ace_recommend()

    assert isinstance(result, str)
    assert "observability" in result
    assert "specialty_emergence" in result
    assert "No trace ID propagation" in result
    assert "deployment" in result
    # 4-item gap list truncated to 3 + "more" indicator
    assert "+1 more" in result
    # Sentinel: must NOT be a JSON blob
    assert result.strip()[0] != "{"
    assert "priority_score" not in result  # internal score field must not leak through


@pytest.mark.asyncio
async def test_ace_recommend_innovate_mode():
    """Innovate mode shows whitespace opportunities and prompts ace_innovate."""
    with patch(
        "core.engine.mcp.tools.ace_recommend",
        new=AsyncMock(
            return_value={
                "mode": "innovate",
                "recommendations": [],
                "whitespace_preview": [
                    {"slug": "cost_intel", "title": "Cost Intelligence", "whitespace_score": 0.45},
                ],
            }
        ),
    ):
        from core.engine.mcp.server import ace_recommend

        result = await ace_recommend()

    assert isinstance(result, str)
    assert "Innovate" in result
    assert "Cost Intelligence" in result
    assert "ace_innovate" in result
    assert result.strip()[0] != "{"


@pytest.mark.asyncio
async def test_ace_recommend_empty_no_crash():
    """Empty recommendations list returns readable message, not an error."""
    with patch(
        "core.engine.mcp.tools.ace_recommend",
        new=AsyncMock(
            return_value={
                "mode": "gap_driven",
                "recommendations": [],
            }
        ),
    ):
        from core.engine.mcp.server import ace_recommend

        result = await ace_recommend()

    assert isinstance(result, str)
    assert result.strip()[0] != "{"
