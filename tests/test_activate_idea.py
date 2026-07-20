# tests/test_activate_idea.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.ideas.state_machine import IdeaStateError


@pytest.mark.asyncio
async def test_activate_creates_initiative():
    """Activating a ready idea creates an initiative with source='idea'."""
    from core.engine.ideas.activate import activate_idea

    ready_idea = {
        "id": "idea:rdy1",
        "status": "ready",
        "title": "Multi-brand token architecture",
        "raw_input": "What if we supported multi-brand themes?",
        "classification": {"domain_path": "ux", "type": "feature", "complexity": "complex"},
        "brief": {
            "what": "Multi-brand token system",
            "why": "Support Acme, Bolt, Crest",
            "what_we_know": "Single-brand exists",
            "open_questions": [],
            "approach": "Phased rollout",
            "effort": "3 weeks",
            "risks": [],
            "first_step": "Audit schema",
        },
        "phases": [{"name": "Research", "archetype": "researcher", "mode": "exploratory"}],
        "connections": [],
    }

    with patch("core.engine.ideas.activate.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[{"id": "idea:rdy1", "status": "promoted"}]],
                [
                    [
                        {
                            "id": "initiative:new1",
                            "source": "idea",
                            "source_idea": "idea:rdy1",
                            "title": "Multi-brand token architecture",
                        }
                    ]
                ],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await activate_idea(idea=ready_idea, user_id="user:ed", product_id="product:default")

    assert result["source"] == "idea"
    assert result["source_idea"] == "idea:rdy1"


@pytest.mark.asyncio
async def test_activate_only_ready_ideas():
    """Activating a non-ready idea raises IdeaStateError."""
    from core.engine.ideas.activate import activate_idea

    with pytest.raises(IdeaStateError):
        await activate_idea(
            idea={"id": "idea:cap1", "status": "captured", "title": "Some idea"},
            user_id="user:ed",
            product_id="product:default",
        )


@pytest.mark.asyncio
async def test_activate_incubating_idea_raises():
    """Activating an incubating idea raises IdeaStateError."""
    from core.engine.ideas.activate import activate_idea

    with pytest.raises(IdeaStateError):
        await activate_idea(
            idea={"id": "idea:inc1", "status": "incubating", "title": "Some idea"},
            user_id="user:ed",
            product_id="product:default",
        )


@pytest.mark.asyncio
async def test_activate_passes_brief_to_initiative():
    """The initiative's context includes the idea's brief and connections."""
    from core.engine.ideas.activate import activate_idea

    ready_idea = {
        "id": "idea:rdy2",
        "status": "ready",
        "title": "API caching",
        "raw_input": "Add caching to the API",
        "classification": {"domain_path": "architecture", "type": "feature", "complexity": "moderate"},
        "brief": {
            "what": "API caching layer",
            "why": "Performance",
            "what_we_know": "Redis available",
            "open_questions": ["Cache invalidation strategy?"],
            "approach": "Redis + TTL",
            "effort": "1 week",
            "risks": ["Stale data"],
            "first_step": "Define cache keys",
        },
        "phases": [],
        "connections": [{"insight_id": "insight:1", "content_preview": "Redis is available", "relevance": "direct"}],
    }

    with patch("core.engine.ideas.activate.pool") as mock_pool:
        mock_conn = AsyncMock()
        created_initiative = None

        async def track_create(query_str, params=None):
            nonlocal created_initiative
            if "CREATE initiative" in query_str:
                created_initiative = params
                return [
                    [{"id": "initiative:new2", "source": "idea", "source_idea": "idea:rdy2", "title": "API caching"}]
                ]
            return [[{"id": "idea:rdy2", "status": "promoted"}]]

        mock_conn.query = track_create
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await activate_idea(idea=ready_idea, user_id="user:ed", product_id="product:default")

    assert created_initiative is not None
    assert created_initiative["source"] == "idea"
    assert created_initiative["source_idea"] == "idea:rdy2"
    assert "API caching layer" in str(created_initiative.get("context", ""))
