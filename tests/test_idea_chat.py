# tests/test_idea_chat.py
"""Test idea-scoped chat system prompt injection."""

from unittest.mock import AsyncMock

import pytest


class TestGetIdeaContext:
    @pytest.mark.asyncio
    async def test_returns_context_for_linked_idea(self):
        from core.engine.chat.streaming import _get_idea_context

        mock_db = AsyncMock()
        mock_db.query = AsyncMock(
            side_effect=[
                [[{"linked_to": "idea:123", "linked_type": "idea"}]],
                [
                    [
                        {
                            "id": "idea:123",
                            "title": "Customer feedback loop",
                            "raw_input": "Build a customer feedback system",
                            "brief": {"what": "Feedback system", "why": "Need signals"},
                            "status": "open",
                        }
                    ]
                ],
            ]
        )
        context = await _get_idea_context(mock_db, "chat_session:abc")
        assert context is not None
        assert "Customer feedback loop" in context["title"]
        assert context["system_prompt"] is not None
        assert "EXPAND" in context["system_prompt"]

    @pytest.mark.asyncio
    async def test_returns_none_for_unlinked_session(self):
        from core.engine.chat.streaming import _get_idea_context

        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[{"linked_to": None, "linked_type": None}]])
        context = await _get_idea_context(mock_db, "chat_session:abc")
        assert context is None

    @pytest.mark.asyncio
    async def test_returns_none_for_non_idea_linked(self):
        from core.engine.chat.streaming import _get_idea_context

        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[[{"linked_to": "task:123", "linked_type": "task"}]])
        context = await _get_idea_context(mock_db, "chat_session:abc")
        assert context is None
