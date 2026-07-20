"""Edit tracker — manages active_edit lifecycle + conflict detection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(mock_conn):
    """Build a MagicMock pool whose .connection() returns an async CM yielding mock_conn."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_claim_file_creates_edit():
    from core.engine.live.edit_tracker import EditTracker

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        side_effect=[
            [],  # no existing edits on file
            [{"id": "active_edit:abc", "state": "claimed", "product": "product:platform"}],  # CREATE result
            [],  # editing RELATE
        ]
    )
    mock_pool = _make_pool(mock_conn)

    with patch("core.engine.live.edit_tracker.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        tracker = EditTracker(db_pool=mock_pool)
        edit = await tracker.claim_file(
            product_id="product:platform",
            session_id="agent_session:s1",
            file_id="graph_file:f1",
        )
        assert edit["state"] == "claimed"
        # Should emit edit.state_changed
        assert any(call[0][0] == "edit.state_changed" for call in mock_bus.emit.call_args_list)


@pytest.mark.asyncio
async def test_claim_detects_conflict():
    from core.engine.live.edit_tracker import EditTracker

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        side_effect=[
            [
                {
                    "id": "active_edit:existing",
                    "state": "editing",
                    "agent_session": "agent_session:s2",
                    "product": "product:platform",
                }
            ],
            [{"id": "active_edit:new", "state": "conflict", "product": "product:platform"}],
            [],  # update existing to conflict
        ]
    )
    mock_pool = _make_pool(mock_conn)

    with patch("core.engine.live.edit_tracker.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        tracker = EditTracker(db_pool=mock_pool)
        edit = await tracker.claim_file(
            product_id="product:platform",
            session_id="agent_session:s1",
            file_id="graph_file:f1",
        )
        assert edit["state"] == "conflict"
        assert any(call[0][0] == "edit.conflict_detected" for call in mock_bus.emit.call_args_list)


@pytest.mark.asyncio
async def test_transition_emits_event():
    from core.engine.live.edit_tracker import EditTracker

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        side_effect=[
            [
                {
                    "id": "active_edit:abc",
                    "state": "claimed",
                    "product": "product:platform",
                    "file": "graph_file:f1",
                    "agent_session": "agent_session:s1",
                }
            ],
            [{"id": "active_edit:abc", "state": "editing"}],
        ]
    )
    mock_pool = _make_pool(mock_conn)

    with patch("core.engine.live.edit_tracker.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        tracker = EditTracker(db_pool=mock_pool)
        result = await tracker.transition("active_edit:abc", "editing")
        assert result["state"] == "editing"
        mock_bus.emit.assert_called_once()
        assert mock_bus.emit.call_args[0][0] == "edit.state_changed"
