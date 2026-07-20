"""Tests for gated idea activation — verify existing ready→promoted path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.ideas.activate import activate_idea


@pytest.mark.asyncio
async def test_activate_ready_idea_creates_initiative():
    """Ready ideas still go through activate_idea for the simple path."""
    idea = {
        "id": "idea:1",
        "status": "ready",
        "title": "Simple fix",
        "brief": {"what": "Fix a small bug", "approach": "Direct fix"},
        "connections": [],
    }

    mock_db = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    initiative_row = {"id": "initiative:1", "title": "Simple fix", "status": "planning"}

    # First query: UPDATE idea status — returns None
    # Second query: CREATE initiative — returns a result that parse_one will unwrap
    mock_db.query = AsyncMock(
        side_effect=[
            None,
            [initiative_row],
        ]
    )

    mock_bus = MagicMock()
    mock_bus.emit = AsyncMock()

    with (
        patch("core.engine.ideas.activate.pool", mock_pool),
        patch("core.engine.events.bus.bus", mock_bus),
        patch("core.engine.core.db.parse_one", return_value=initiative_row),
        patch("core.engine.graph.edge_writer.create_edge", new_callable=AsyncMock),
    ):
        result = await activate_idea(idea, "user:1", "product:test")

    # The function should return an initiative
    assert result is not None
    # Bus should have emitted at least the state_changed event
    assert mock_bus.emit.call_count >= 1
