"""Test that briefing engine emits briefing.generated event."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_on_briefing_generated_dispatches_notification():
    """The briefing.generated handler should dispatch an actionable notification."""
    from core.engine.events.automations import on_briefing_generated

    with patch("core.engine.notifications.dispatcher.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await on_briefing_generated(
            "briefing.generated",
            {
                "product_id": "product:default",
                "briefing_id": "briefing:abc",
                "period": "2026-03-31",
                "summary": "3 decisions made, 1 gap detected",
            },
        )

        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["tier"] == "actionable"
        assert call_kwargs["category"] == "briefing"
        assert "briefing" in call_kwargs["title"].lower()
