# tests/test_executor_ranker_wired.py
"""Verify relevance ranker is called during orchestration."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ranker_called_on_execute():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="build a test feature",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={
            "insights": [],
            "specialty_insights": [],
            "org_insights": [],
            "total_count": 0,
        },
        classification_override={
            "discipline": "testing",
            "archetype": "creator",
            "mode": "reactive",
            "specialties": [],
        },
    )
    with patch("core.engine.intelligence.ranker.rank_insights", new_callable=AsyncMock) as mock_rank:
        mock_rank.return_value = req.intelligence_override
        try:
            await orchestrate(req)
        except Exception:
            pass
    mock_rank.assert_called_once()
    assert mock_rank.call_args[0][1] == "build a test feature"
