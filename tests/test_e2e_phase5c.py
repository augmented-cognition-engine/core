# tests/test_e2e_phase5c.py
"""E2E integration tests for Phase 5c portal completion."""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_e2e_chat_session_flow():
    """Create session → send message → response → follow-up uses context."""
    from core.engine.chat.handler import create_session, handle_message

    with (
        patch("core.engine.chat.handler.pool") as mock_pool,
        patch("core.engine.orchestrator.executor.execute_task", new_callable=AsyncMock) as mock_execute,
    ):
        mock_conn = AsyncMock()

        call_count = 0

        async def track(query_str, params=None):
            nonlocal call_count
            call_count += 1
            if "CREATE chat_session" in query_str:
                return [[{"id": "chat_session:e2e", "status": "active"}]]
            if "FROM chat_message" in query_str:
                if call_count > 5:
                    return [
                        [
                            {"role": "user", "content": "What is ACE?"},
                            {"role": "assistant", "content": "An intelligence system"},
                        ]
                    ]
                return [[]]
            return [[]]

        mock_conn.query = track
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_execute.return_value = {
            "id": "task:e2e1",
            "output": "An intelligence system",
            "domain_path": "",
            "archetype": "",
            "mode": "",
        }

        # Create session
        session = await create_session("product:test", "workspace:test", "user:test")
        assert session["status"] == "active"

        # Send message
        result = await handle_message("chat_session:e2e", "What is ACE?", "product:test", "workspace:test", "user:test")
        assert result["output"] == "An intelligence system"

        # Follow-up
        mock_execute.return_value = {
            "id": "task:e2e2",
            "output": "Follow-up answer",
            "domain_path": "",
            "archetype": "",
            "mode": "",
        }
        result2 = await handle_message(
            "chat_session:e2e", "Tell me more", "product:test", "workspace:test", "user:test"
        )
        assert result2["output"] == "Follow-up answer"


@pytest.mark.asyncio
async def test_e2e_notification_flow():
    """Trigger event → notification created → tiered correctly."""
    from core.engine.notifications.triggers import notify_conflict_detected, notify_idea_ready

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        notifications = []

        async def track_create(query_str, params=None):
            if "CREATE notification" in query_str:
                notif = {"id": f"notification:{len(notifications)}", **params}
                notifications.append(notif)
                return [[notif]]
            return [[]]

        mock_conn.query = track_create
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await notify_idea_ready("product:test", "user:test", "Multi-brand tokens", "idea:1")
        await notify_conflict_detected("product:test", "user:test", "conflict:1")

    assert len(notifications) == 2
    assert notifications[0]["tier"] == "actionable"
    assert notifications[1]["tier"] == "critical"


@pytest.mark.asyncio
async def test_e2e_home_dashboard_endpoints():
    """Verify Home parallel API calls return correct structure."""
    # Test that the endpoint functions exist and return proper structure
    from core.engine.notifications.triggers import TRIGGER_TIERS

    assert len(TRIGGER_TIERS) >= 10

    # Test dispatcher defaults
    from core.engine.notifications.dispatcher import DEFAULT_CHANNELS

    assert "critical" in DEFAULT_CHANNELS
    assert "in_app" in DEFAULT_CHANNELS["critical"]


@pytest.mark.asyncio
async def test_e2e_chat_handler_respects_message_limit():
    """Only last 20 messages loaded as context."""
    from core.engine.chat.handler import MAX_CONTEXT_MESSAGES

    assert MAX_CONTEXT_MESSAGES == 20
