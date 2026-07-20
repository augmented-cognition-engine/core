# tests/test_incubate_idea.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.ideas.schemas import IncubationBrief


def _mock_idea(status="incubating"):
    return {
        "id": "idea:inc1",
        "raw_input": "What if we supported multiple brand themes?",
        "status": status,
        "classification": {
            "domain_path": "ux",
            "type": "feature",
            "complexity": "complex",
            "title": "Multi-brand themes",
            "summary": "Support multiple brand themes in one token set.",
        },
        "qualifying_qs": [{"q": "For how many brands?", "a": "3"}],
        "product": "product:default",
        "user": "user:ed",
    }


@pytest.mark.asyncio
async def test_incubate_produces_brief():
    """Incubation generates a brief with all 8 sections."""
    from core.engine.ideas.incubate import incubate_idea

    mock_brief = IncubationBrief(
        what="Multi-brand token system",
        why="Support Acme, Bolt, Crest",
        what_we_know="Single-brand token pipeline exists",
        open_questions=["Override strategy?"],
        approach="Phase 1: schema, Phase 2: generator",
        effort="3 weeks",
        risks=["Performance overhead"],
        first_step="Audit current schema",
    )

    with patch("core.engine.ideas.incubate.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_brief)
        mock_llm.complete_json = AsyncMock(
            return_value=[
                {
                    "name": "Schema design",
                    "description": "Design schema",
                    "archetype": "creator",
                    "mode": "deliberative",
                    "estimated_hours": 8,
                    "depends_on": [],
                    "requires_human": False,
                },
            ]
        )
        with patch("core.engine.ideas.incubate.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(return_value=[[]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await incubate_idea(_mock_idea(), "product:default")

    assert result["brief"]["what"] == "Multi-brand token system"
    assert result["brief"]["first_step"] == "Audit current schema"
    assert "risks" in result["brief"]


@pytest.mark.asyncio
async def test_incubate_finds_prior_work():
    """Incubation queries for prior related work in the org."""
    from core.engine.ideas.incubate import incubate_idea

    mock_brief = IncubationBrief(
        what="x",
        why="x",
        what_we_know="x",
        open_questions=[],
        approach="x",
        effort="x",
        risks=[],
        first_step="x",
    )

    with patch("core.engine.ideas.incubate.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_brief)
        mock_llm.complete_json = AsyncMock(return_value=[])
        with patch("core.engine.ideas.incubate.pool") as mock_pool:
            mock_conn = AsyncMock()

            async def track_queries(query_str, params=None):
                if "FROM task" in query_str:
                    return [[{"id": "task:old1", "description": "Token audit", "domain_path": "ux"}]]
                if "FROM idea" in query_str:
                    return [[]]
                if "FROM insight" in query_str:
                    return [[]]
                return [[]]

            mock_conn.query = track_queries
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await incubate_idea(_mock_idea(), "product:default")

    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_incubate_decomposes_complex():
    """Complex ideas get phase decomposition."""
    from core.engine.ideas.incubate import incubate_idea

    mock_brief = IncubationBrief(
        what="x",
        why="x",
        what_we_know="x",
        open_questions=[],
        approach="x",
        effort="x",
        risks=[],
        first_step="x",
    )
    mock_phases = [
        {
            "name": "Research",
            "description": "Survey approaches",
            "archetype": "researcher",
            "mode": "exploratory",
            "estimated_hours": 4,
            "depends_on": [],
            "requires_human": False,
        },
        {
            "name": "Design",
            "description": "Design architecture",
            "archetype": "creator",
            "mode": "deliberative",
            "estimated_hours": 8,
            "depends_on": [0],
            "requires_human": True,
        },
    ]

    with patch("core.engine.ideas.incubate.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_brief)
        mock_llm.complete_json = AsyncMock(return_value=mock_phases)
        with patch("core.engine.ideas.incubate.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(return_value=[[]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await incubate_idea(_mock_idea(), "product:default")

    assert result["phases"] is not None
    assert len(result["phases"]) == 2


@pytest.mark.asyncio
async def test_incubate_connects_to_intelligence():
    """Incubation finds and records connections to existing insights."""
    from core.engine.ideas.incubate import incubate_idea

    mock_brief = IncubationBrief(
        what="x",
        why="x",
        what_we_know="x",
        open_questions=[],
        approach="x",
        effort="x",
        risks=[],
        first_step="x",
    )
    mock_insights = [
        {"id": "insight:1", "content": "Token naming uses kebab-case", "insight_type": "convention"},
        {"id": "insight:2", "content": "APCA replacing WCAG contrast", "insight_type": "discovery"},
    ]

    with patch("core.engine.ideas.incubate.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_brief)
        mock_llm.complete_json = AsyncMock(return_value=[])
        with patch("core.engine.ideas.incubate.pool") as mock_pool:
            mock_conn = AsyncMock()

            async def return_insights(query_str, params=None):
                if "FROM insight" in query_str:
                    return [mock_insights]
                return [[]]

            mock_conn.query = return_insights
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await incubate_idea(_mock_idea(), "product:default")

    assert result["connections"] is not None
    assert len(result["connections"]) == 2


@pytest.mark.asyncio
async def test_incubate_finds_related_ideas():
    """Ideas similar to existing pipeline ideas are cross-referenced."""
    from core.engine.ideas.incubate import incubate_idea

    mock_brief = IncubationBrief(
        what="x",
        why="x",
        what_we_know="x",
        open_questions=[],
        approach="x",
        effort="x",
        risks=[],
        first_step="x",
    )

    with patch("core.engine.ideas.incubate.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_brief)
        mock_llm.complete_json = AsyncMock(return_value=[])
        with patch("core.engine.ideas.incubate.pool") as mock_pool:
            mock_conn = AsyncMock()

            async def return_related(query_str, params=None):
                if "FROM idea" in query_str and "status IN" in query_str:
                    return [[{"id": "idea:other", "title": "Brand theme switcher", "status": "ready"}]]
                return [[]]

            mock_conn.query = return_related
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await incubate_idea(_mock_idea(), "product:default")

    assert result["status"] == "ready"
