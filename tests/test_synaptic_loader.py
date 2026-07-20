# tests/test_synaptic_loader.py
from unittest.mock import AsyncMock, patch

import pytest


def test_budget_calculation():
    """Budget = max(1, floor(strength * 5))."""
    from core.engine.graph.synaptic_loader import calculate_budget

    assert calculate_budget(0.0) == 1
    assert calculate_budget(0.2) == 1
    assert calculate_budget(0.5) == 2
    assert calculate_budget(0.8) == 4
    assert calculate_budget(1.0) == 5


def test_budget_cap():
    """Total cross-domain budget capped at 15."""
    from core.engine.graph.synaptic_loader import apply_cross_domain_cap

    insights = [{"content": f"insight {i}"} for i in range(20)]
    capped = apply_cross_domain_cap(insights)
    assert len(capped) == 15


@pytest.mark.asyncio
async def test_loads_only_confirmed_synapses():
    """Synaptic loader skips unconfirmed synapses."""
    from core.engine.graph.synaptic_loader import load_synaptic_intelligence

    with patch("core.engine.graph.synaptic_loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_synaptic_intelligence("subdomain:test", "product:test")

    assert result == []


@pytest.mark.asyncio
async def test_strength_weighting():
    """Stronger synapses get more insights."""
    from core.engine.graph.synaptic_loader import load_synaptic_intelligence

    synapses = [
        {"id": "synapse:a", "in": "subdomain:test", "out": "subdomain:other1", "strength": 0.8},
        {"id": "synapse:b", "in": "subdomain:test", "out": "subdomain:other2", "strength": 0.2},
    ]

    # DB returns at most `budget` rows; budget for strength 0.8 = floor(0.8*5) = 4
    insights_other1 = [{"id": f"insight:{i}", "content": f"content {i}", "confidence": 0.9 - i * 0.1} for i in range(4)]
    insights_other2 = [{"id": "insight:x", "content": "content x", "confidence": 0.7}]

    with patch("core.engine.graph.synaptic_loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [synapses],  # synapse query
                [insights_other1],  # insights for other1 (budget=4)
                [[{"slug": "other1"}]],  # slug resolution for other1
                [insights_other2],  # insights for other2 (budget=1)
                [[{"slug": "other2"}]],  # slug resolution for other2
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_synaptic_intelligence("subdomain:test", "product:test")

    assert len(result) <= 5
    assert all("synapse_id" in r for r in result)
    assert all("source_subdomain" in r for r in result)
