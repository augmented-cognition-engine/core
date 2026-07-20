# tests/test_proposals.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_proposals_returns_unconfirmed_at_threshold():
    """Proposals are unconfirmed synapses where co_occurrence >= dismiss_threshold."""
    from core.engine.graph.proposals import list_proposals

    proposals = [
        {
            "id": "synapse:a",
            "in": "subdomain:x",
            "out": "subdomain:y",
            "co_occurrence": 12,
            "dismiss_threshold": 10,
            "confirmed": False,
            "dismissed_at": None,
            "strength": 0.24,
            "from_slug": "x",
            "to_slug": "y",
        },
    ]

    with patch("core.engine.graph.proposals.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[proposals])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await list_proposals("product:test")

    assert len(result) == 1
    assert result[0]["id"] == "synapse:a"


@pytest.mark.asyncio
async def test_confirm_sets_confirmed_true():
    """Confirming a proposal sets confirmed=true."""
    from core.engine.graph.proposals import confirm_proposal

    with patch("core.engine.graph.proposals.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "synapse:a", "confirmed": True}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await confirm_proposal("synapse:a", "user:test")

    assert result["confirmed"] is True


@pytest.mark.asyncio
async def test_dismiss_doubles_threshold():
    """Dismissing a proposal doubles the dismiss_threshold."""
    from core.engine.graph.proposals import dismiss_proposal

    with patch("core.engine.graph.proposals.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [[{"dismiss_threshold": 10}]],
                [[{"id": "synapse:a", "dismiss_threshold": 20, "dismissed_at": "2026-03-21T00:00:00Z"}]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dismiss_proposal("synapse:a")

    assert result["dismiss_threshold"] == 20
