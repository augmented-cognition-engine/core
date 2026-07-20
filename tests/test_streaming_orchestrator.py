# tests/test_streaming_orchestrator.py
"""Tests for streaming orchestrator — yields events during execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_yields_classification_event_first():
    """First event should be classification metadata."""
    from core.engine.orchestrator.streaming import stream_task

    async def mock_stream(*a, **kw):
        yield "Hello "
        yield "world"

    with (
        patch("core.engine.orchestrator.streaming.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.streaming.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.streaming.llm") as mock_llm,
        patch("core.engine.orchestrator.streaming.pool") as mock_pool,
    ):
        mock_classify.return_value = {
            "domain_path": "api_design",
            "archetype": "advisor",
            "mode": "reactive",
            "complexity": "moderate",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.stream_messages = MagicMock(side_effect=mock_stream)

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:1"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        events = []
        async for event in stream_task(
            description="How to cache API responses?",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ):
            events.append(event)

    assert events[0]["type"] == "classification"
    assert events[0]["domain_path"] == "api_design"
    assert events[0]["archetype"] == "advisor"


@pytest.mark.asyncio
async def test_yields_intelligence_event_after_classification():
    """Second event should be intelligence loading summary."""
    from core.engine.orchestrator.streaming import stream_task

    async def mock_stream(*a, **kw):
        yield "response"

    with (
        patch("core.engine.orchestrator.streaming.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.streaming.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.streaming.llm") as mock_llm,
        patch("core.engine.orchestrator.streaming.pool") as mock_pool,
    ):
        mock_classify.return_value = {
            "domain_path": "ux",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "simple",
        }
        mock_load.return_value = {
            "insights": [
                {"insight_type": "pattern", "content": "Use rem", "confidence": 0.9},
                {"insight_type": "correction", "content": "Not px", "confidence": 0.95},
                {"insight_type": "correction", "content": "Use APCA", "confidence": 0.8},
            ],
            "total_count": 3,
        }
        mock_llm.stream_messages = MagicMock(side_effect=mock_stream)

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:2"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        events = []
        async for event in stream_task(
            description="Token audit",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ):
            events.append(event)

    intel_event = events[1]
    assert intel_event["type"] == "intelligence"
    assert intel_event["insights_count"] == 3
    assert intel_event["corrections_count"] == 2


@pytest.mark.asyncio
async def test_yields_token_events_from_llm():
    """Token events stream from the LLM provider."""
    from core.engine.orchestrator.streaming import stream_task

    async def mock_stream(*a, **kw):
        yield "Token1 "
        yield "Token2 "
        yield "Token3"

    with (
        patch("core.engine.orchestrator.streaming.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.streaming.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.streaming.llm") as mock_llm,
        patch("core.engine.orchestrator.streaming.pool") as mock_pool,
    ):
        mock_classify.return_value = {
            "domain_path": "test",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.stream_messages = MagicMock(side_effect=mock_stream)

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:3"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        events = []
        async for event in stream_task(
            description="Test",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ):
            events.append(event)

    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 3
    assert token_events[0]["text"] == "Token1 "
    assert token_events[1]["text"] == "Token2 "
    assert token_events[2]["text"] == "Token3"


@pytest.mark.asyncio
async def test_done_event_contains_full_output():
    """Done event includes concatenated output and task_id."""
    from core.engine.orchestrator.streaming import stream_task

    async def mock_stream(*a, **kw):
        yield "Hello "
        yield "world"

    with (
        patch("core.engine.orchestrator.streaming.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.streaming.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.streaming.llm") as mock_llm,
        patch("core.engine.orchestrator.streaming.pool") as mock_pool,
    ):
        mock_classify.return_value = {
            "domain_path": "test",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.stream_messages = MagicMock(side_effect=mock_stream)

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:abc"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        events = []
        async for event in stream_task(
            description="Test",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ):
            events.append(event)

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["full_output"] == "Hello world"
    assert done_event["task_id"] == "task:abc"


@pytest.mark.asyncio
async def test_event_sequence_order():
    """Events must come in order: classification -> intelligence -> token+ -> done."""
    from core.engine.orchestrator.streaming import stream_task

    async def mock_stream(*a, **kw):
        yield "response"

    with (
        patch("core.engine.orchestrator.streaming.classify_task", new_callable=AsyncMock) as mock_classify,
        patch("core.engine.orchestrator.streaming.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.orchestrator.streaming.llm") as mock_llm,
        patch("core.engine.orchestrator.streaming.pool") as mock_pool,
    ):
        mock_classify.return_value = {
            "domain_path": "test",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.stream_messages = MagicMock(side_effect=mock_stream)

        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "task:seq"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        event_types = []
        async for event in stream_task(
            description="Test",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ):
            event_types.append(event["type"])

    assert event_types[0] == "classification"
    assert event_types[1] == "intelligence"
    assert event_types[-1] == "done"
    assert "token" in event_types
