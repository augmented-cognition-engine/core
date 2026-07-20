"""Substrate acceptance — per spec v1.2 'Behavioral acceptance'.

Tests structural completeness of BriefingPayload, not voice. Calls
ace_briefing_payload (the structured-data MCP surface) instead of the
markdown-rendering ace_briefing.
"""

from __future__ import annotations

import pytest

from core.engine.mcp.tools import ace_briefing_payload, ace_pillar_status
from core.engine.product.feature_flags import set_phase_aware_ranking_enabled


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_briefing_payload_structurally_complete(db_pool):
    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    try:
        payload = await ace_briefing_payload(product_id=pid)
        required_keys = {
            "current_phase",
            "days_in_phase",
            "next_phase",
            "phase_floors",
            "demo_target",
            "pillar_scores",
            "discipline_breakdown",
            "sensor_coverage",
            "top_recommendations",
            "blocked_patterns",
            "open_uncertainty_queries",
        }
        assert required_keys.issubset(payload.keys())
        assert len(payload["phase_floors"]) == 7
        # sensor_coverage now reflects real data; assert SHAPE (the four
        # canonical sensor keys + bool values), not specific bools that
        # depend on whatever capability_quality data product:platform has.
        sensor_coverage = payload["sensor_coverage"]
        expected_sensor_keys = {
            "experience.aix",
            "experience.content_design.voice_consistency",
            "experience.aix.demo_readiness",
            "evolution.engineering_culture.contributor_coordination",
        }
        assert set(sensor_coverage.keys()) == expected_sensor_keys
        assert all(isinstance(v, bool) for v in sensor_coverage.values())
    finally:
        await set_phase_aware_ranking_enabled(db_pool, pid, False)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pillar_status_returns_all_seven(db_pool):
    result = await ace_pillar_status(product_id="product:platform")
    expected_pillars = {
        "experience",
        "interface",
        "logic",
        "state",
        "operations",
        "evolution",
        "trust",
    }
    assert expected_pillars.issubset(result.keys())
