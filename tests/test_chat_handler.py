# tests/test_chat_handler.py
"""Tests for chat handler — orchestrator wrapper with conversation context."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_chat_handler_routes_through_orchestrator():
    """Chat message calls execute_task() with conversation context."""
    from core.engine.chat.handler import handle_message

    with (
        patch("core.engine.chat.handler.pool") as mock_pool,
        patch("core.engine.orchestrator.executor.execute_task", new_callable=AsyncMock) as mock_execute,
    ):
        mock_conn = AsyncMock()
        # First call: get_session_history returns empty
        # Subsequent calls: persist messages
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_execute.return_value = {
            "id": "task:chat1",
            "output": "Here is the answer.",
            "domain_path": "architecture",
            "archetype": "advisor",
            "mode": "reactive",
        }

        result = await handle_message(
            session_id="chat_session:s1",
            message="What's our API caching strategy?",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        )

    assert result["output"] == "Here is the answer."
    mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_chat_handler_persists_messages():
    """User + assistant messages written to chat_message table."""
    from core.engine.chat.handler import handle_message

    queries_run = []

    with (
        patch("core.engine.chat.handler.pool") as mock_pool,
        patch("core.engine.orchestrator.executor.execute_task", new_callable=AsyncMock) as mock_execute,
    ):
        mock_conn = AsyncMock()

        async def track_queries(query_str, params=None):
            queries_run.append(query_str)
            return [[]]

        mock_conn.query = track_queries
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_execute.return_value = {
            "id": "task:c2",
            "output": "Answer",
            "domain_path": "",
            "archetype": "",
            "mode": "",
        }

        await handle_message("chat_session:s1", "Hi", "product:test", "workspace:test", "user:test")

    # Should have CREATE chat_message calls for user and assistant
    create_queries = [q for q in queries_run if "CREATE chat_message" in q]
    assert len(create_queries) == 2


@pytest.mark.asyncio
async def test_chat_handler_session_context():
    """Prior messages loaded and passed to orchestrator."""
    from core.engine.chat.handler import handle_message

    call_count = 0
    prior_messages = [
        {"role": "user", "content": "What is our tech stack?"},
        {"role": "assistant", "content": "Python + FastAPI + SurrealDB"},
    ]

    with (
        patch("core.engine.chat.handler.pool") as mock_pool,
        patch("core.engine.orchestrator.executor.execute_task", new_callable=AsyncMock) as mock_execute,
    ):
        mock_conn = AsyncMock()

        async def context_query(query_str, params=None):
            nonlocal call_count
            call_count += 1
            if "FROM chat_message" in query_str:
                return [prior_messages]
            return [[]]

        mock_conn.query = context_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_execute.return_value = {
            "id": "task:c3",
            "output": "Follow-up answer",
            "domain_path": "",
            "archetype": "",
            "mode": "",
        }

        await handle_message(
            "chat_session:s1", "Tell me more about the DB", "product:test", "workspace:test", "user:test"
        )

    # The execute_task description should contain conversation context
    call_args = mock_execute.call_args
    description = call_args[1].get("description", "") if call_args[1] else call_args[0][0]
    assert "tech stack" in description.lower() or "Conversation context" in description


@pytest.mark.asyncio
async def test_create_session():
    """Create a new chat session."""
    from core.engine.chat.handler import create_session

    with patch("core.engine.chat.handler.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "chat_session:new1",
                        "status": "active",
                        "title": None,
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await create_session("product:test", "workspace:test", "user:test")

    assert result["status"] == "active"
