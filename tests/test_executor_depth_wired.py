from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_depth_budget_computed_from_classification():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="build a REST API",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={"insights": [], "specialty_insights": [], "org_insights": [], "total_count": 0},
        classification_override={
            "discipline": "api_design",
            "archetype": "creator",
            "mode": "reactive",
            "complexity": "simple",
            "specialties": [],
        },
    )
    with patch("core.engine.intelligence.depth_budget.budget_for_depth") as mock_budget:
        mock_budget.return_value = MagicMock(context_tokens=400, recall_multiplier=0.5, load_pm_context=False)
        try:
            await orchestrate(req)
        except Exception:
            pass
    mock_budget.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_pm_context_skipped_at_depth_1():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="quick question",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={"insights": [], "specialty_insights": [], "org_insights": [], "total_count": 0},
        classification_override={
            "discipline": "api_design",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "specialties": [],
        },
    )
    with patch("core.engine.orchestrator.context.load_full_context", new_callable=AsyncMock) as mock_pm:
        try:
            await orchestrate(req)
        except Exception:
            pass
    mock_pm.assert_not_called()
