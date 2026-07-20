# tests/test_emergence.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_no_emergence_below_threshold():
    """No specialty created when fewer than 5 unparented insights in a subdomain."""
    from core.engine.intelligence.emergence import check_emergence

    with patch("core.engine.intelligence.emergence.pool") as mock_pool:
        mock_conn = AsyncMock()
        # 3 unparented insights — below threshold
        mock_conn.query = AsyncMock(return_value=[[{"count": 3, "source_domain": "architecture"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_emergence("product:test")

    assert result == []


@pytest.mark.asyncio
async def test_emergence_triggers_at_threshold():
    """Specialty created when 5+ unparented insights cluster in a subdomain."""
    from core.engine.intelligence.emergence import check_emergence

    mock_insights = [{"id": f"insight:{i}", "content": f"Token fact {i}", "source_domain": "ux"} for i in range(5)]

    mock_llm_response = {"name": "Token Pipeline", "slug": "token-pipeline"}

    with patch("core.engine.intelligence.emergence.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                # First call: count unparented insights per subdomain
                [[{"count": 5, "source_domain": "ux"}]],
                # Second call: fetch the actual insights for LLM
                [mock_insights],
                # Third call: create specialty
                [[{"id": "specialty:abc"}]],
                # Fourth call: update insights
                [[]],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("core.engine.intelligence.emergence.llm") as mock_llm:
            mock_llm.complete_json = AsyncMock(return_value=mock_llm_response)
            result = await check_emergence("product:test")

    assert len(result) == 1
    assert result[0]["slug"] == "token-pipeline"


@pytest.mark.asyncio
async def test_emergence_skips_if_specialty_exists():
    """No duplicate specialty if one already exists for this cluster."""
    from core.engine.intelligence.emergence import check_emergence

    with patch("core.engine.intelligence.emergence.pool") as mock_pool:
        mock_conn = AsyncMock()
        # Count returns empty (0 unparented)
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_emergence("product:test")

    assert result == []
