"""Tests for greenfield capability generation from intent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_bootstrap_from_intent_returns_capabilities():
    """LLM returns valid capabilities from a project description."""
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "capabilities": [
                {
                    "name": "User Auth",
                    "slug": "user_auth",
                    "description": "Authentication system",
                    "priority": "critical",
                },
                {
                    "name": "Payment Flow",
                    "slug": "payment_flow",
                    "description": "Escrow payments",
                    "priority": "critical",
                },
            ],
            "vision": "A marketplace connecting designers with clients",
            "recommended_first": {"capability": "payment_flow", "reason": "Highest risk"},
        }
    )

    with patch("core.engine.product.capability_mapper.get_llm", return_value=mock_llm):
        from core.engine.product.capability_mapper import CapabilityMapper

        mock_pool = MagicMock()
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query = AsyncMock(return_value=[[]])

        mapper = CapabilityMapper(mock_pool)
        result = await mapper.bootstrap_from_intent(
            "A marketplace for freelance designers with escrow payments",
            "product:default",
        )

    assert "capabilities" in result
    assert len(result["capabilities"]) == 2
    assert result["capabilities"][0]["slug"] == "user_auth"
    assert result["vision"] is not None
    assert result["recommended_first"]["capability"] == "payment_flow"
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_bootstrap_from_intent_writes_to_db():
    """Capabilities and vision are written to the database."""
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "capabilities": [
                {"name": "User Auth", "slug": "user_auth", "description": "Auth", "priority": "critical"},
            ],
            "vision": "A marketplace",
            "recommended_first": {"capability": "user_auth", "reason": "Core"},
        }
    )

    with patch("core.engine.product.capability_mapper.get_llm", return_value=mock_llm):
        from core.engine.product.capability_mapper import CapabilityMapper

        mock_pool = MagicMock()
        mock_db = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.query = AsyncMock(return_value=[[{"id": "capability:1"}]])

        mapper = CapabilityMapper(mock_pool)
        result = await mapper.bootstrap_from_intent("A marketplace", "product:default")

    # Should have called query for: upsert capability + upsert vision
    assert mock_db.query.call_count >= 2
