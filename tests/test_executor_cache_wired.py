# tests/test_executor_cache_wired.py
"""Verify classification cache is wired into executor."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_cache_lookup_called_without_override():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="fix the authentication bug",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={
            "insights": [],
            "specialty_insights": [],
            "org_insights": [],
            "total_count": 0,
        },
    )
    with patch(
        "core.engine.intelligence.classification_cache.lookup_with_entry", new_callable=AsyncMock, return_value=None
    ) as mock_lookup:
        try:
            await orchestrate(req)
        except Exception:
            pass
    mock_lookup.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_classifier():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="build a new REST endpoint",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={
            "insights": [],
            "specialty_insights": [],
            "org_insights": [],
            "total_count": 0,
        },
    )
    cached = {"discipline": "api_design", "archetype": "creator", "mode": "reactive", "specialties": []}
    with (
        patch(
            "core.engine.intelligence.classification_cache.lookup_with_entry",
            new_callable=AsyncMock,
            return_value=(cached, "classification_cache:abc"),
        ),
        patch("core.engine.orchestrator.classifier.classify_task", new_callable=AsyncMock) as mock_classify,
    ):
        try:
            await orchestrate(req)
        except Exception:
            pass
    mock_classify.assert_not_called()
