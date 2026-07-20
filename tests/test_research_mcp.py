# tests/test_research_mcp.py
"""Tests for ace_research MCP tool."""

from unittest.mock import AsyncMock, patch

import pytest


def test_ace_research_importable():
    from core.engine.mcp.tools import ace_research

    assert callable(ace_research)


def test_research_agent_importable():
    from core.engine.research.agent import ResearchAgent, ResearchResult

    assert ResearchAgent is not None
    assert ResearchResult is not None


@pytest.mark.asyncio
async def test_ace_research_valid_type():
    from core.engine.mcp.tools import ace_research
    from core.engine.research.agent import ResearchResult

    mock_result = ResearchResult(
        topic="rate limiting",
        discipline="security",
        research_type="grounded_how_to",
        synthesis="Use token bucket.",
        confidence=0.75,
    )

    with patch("core.engine.research.agent.ResearchAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=mock_result)
        result = await ace_research(
            topic="rate limiting",
            research_type="grounded_how_to",
        )

    assert result["synthesis"] == "Use token bucket."
    assert result["discipline"] == "security"
    assert result["confidence"] == 0.75
    assert result["research_type"] == "grounded_how_to"


@pytest.mark.asyncio
async def test_ace_research_invalid_type_returns_error():
    from core.engine.mcp.tools import ace_research

    result = await ace_research(topic="something", research_type="made_up")
    assert "error" in result


@pytest.mark.asyncio
async def test_ace_research_defaults_to_grounded_how_to():
    from core.engine.mcp.tools import ace_research
    from core.engine.research.agent import ResearchResult

    mock_result = ResearchResult(
        topic="async patterns",
        discipline="architecture",
        research_type="grounded_how_to",
        synthesis="Use asyncio.gather for parallel I/O.",
        confidence=0.8,
    )

    with patch("core.engine.research.agent.ResearchAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=mock_result)
        result = await ace_research(topic="async patterns")

    assert result["research_type"] == "grounded_how_to"


@pytest.mark.asyncio
async def test_ace_research_handles_agent_exception():
    from core.engine.mcp.tools import ace_research

    with patch("core.engine.research.agent.ResearchAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("network error"))
        result = await ace_research(topic="something")

    assert "error" in result
    assert "network error" in result["error"]
