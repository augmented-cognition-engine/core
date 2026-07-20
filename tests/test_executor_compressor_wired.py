# tests/test_executor_compressor_wired.py
"""Verify insight compressor is called 3 times (once per insight list) during orchestration."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_compressor_called_on_execute():
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description="build a test feature",
        product_id="product:platform",
        workspace_id="workspace:default",
        user_id="user:test",
        intelligence_override={
            "insights": [{"id": "insight:1", "content": "x", "confidence": 0.9}],
            "specialty_insights": [],
            "org_insights": [],
            "total_count": 1,
        },
        classification_override={
            "discipline": "testing",
            "archetype": "creator",
            "mode": "reactive",
            "specialties": [],
        },
    )
    call_count = 0

    def _mock_compress(insights):
        nonlocal call_count
        call_count += 1
        return insights

    with patch("core.engine.intelligence.compressor.compress_insights", side_effect=_mock_compress):
        try:
            await orchestrate(req)
        except Exception:
            pass
    assert call_count == 3
