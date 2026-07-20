"""Agent coordinator — manages agent_session lifecycle."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_pool(mock_conn):
    """Build a mock pool whose .connection() returns an async context manager."""
    pool = MagicMock()

    @asynccontextmanager
    async def _connection():
        yield mock_conn

    pool.connection = _connection
    return pool


@pytest.mark.asyncio
async def test_start_session_creates_record():
    from core.engine.live.coordinator import AgentCoordinator

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        return_value=[{"id": "agent_session:abc", "state": "starting", "product": "product:platform"}]
    )
    mock_pool = _mock_pool(mock_conn)

    with patch("core.engine.live.coordinator.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        coord = AgentCoordinator(db_pool=mock_pool)
        session = await coord.start_session(
            product_id="product:platform",
            work_item_id="work_item:123",
            user_id="user:default",
        )
        assert session["state"] == "starting"
        assert mock_conn.query.called
        mock_bus.emit.assert_called_once()


@pytest.mark.asyncio
async def test_transition_emits_event():
    from core.engine.live.coordinator import AgentCoordinator

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        side_effect=[
            [
                {
                    "id": "agent_session:abc",
                    "state": "starting",
                    "product": "product:platform",
                    "work_item": "",
                    "capabilities_touched": [],
                }
            ],
            [{"id": "agent_session:abc", "state": "active"}],
        ]
    )
    mock_pool = _mock_pool(mock_conn)

    with patch("core.engine.live.coordinator.bus") as mock_bus:
        mock_bus.emit = AsyncMock()
        coord = AgentCoordinator(db_pool=mock_pool)
        await coord.transition("agent_session:abc", "active")
        mock_bus.emit.assert_called_once()
        call_args = mock_bus.emit.call_args
        assert call_args[0][0] == "agent.state_changed"
        assert call_args[0][1]["new_state"] == "active"
        assert call_args[0][1]["old_state"] == "starting"


@pytest.mark.asyncio
async def test_heartbeat_updates_timestamp():
    from core.engine.live.coordinator import AgentCoordinator

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    mock_pool = _mock_pool(mock_conn)

    coord = AgentCoordinator(db_pool=mock_pool)
    await coord.heartbeat("agent_session:abc")
    query = mock_conn.query.call_args[0][0]
    assert "last_heartbeat" in query


@pytest.mark.asyncio
async def test_heartbeat_with_progress():
    from core.engine.live.coordinator import AgentCoordinator

    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    mock_pool = _mock_pool(mock_conn)

    coord = AgentCoordinator(db_pool=mock_pool)
    await coord.heartbeat("agent_session:abc", progress_pct=45)
    query = mock_conn.query.call_args[0][0]
    assert "progress_pct" in query
