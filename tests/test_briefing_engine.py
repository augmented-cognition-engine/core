# tests/test_briefing_engine.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_aggregate_engine_results_empty():
    from core.engine.sentinel.engines.briefing import aggregate_engine_results

    metrics = aggregate_engine_results([])
    assert metrics["corrections_written"] == 0
    assert metrics["gaps_filled"] == 0
    assert metrics["insights_verified"] == 0
    assert metrics["insights_updated"] == 0
    assert metrics["changes_detected"] == 0
    assert metrics["engine_runs_summarized"] == 0


def test_aggregate_engine_results_sums_correctly():
    from core.engine.sentinel.engines.briefing import aggregate_engine_results

    runs = [
        {
            "engine": "failure_analysis",
            "results": {"failures_analyzed": 3, "corrections_written": 3, "research_queued": 1},
        },
        {"engine": "gap_researcher", "results": {"gaps_identified": 5, "insights_written": 8}},
        {
            "engine": "knowledge_verifier",
            "results": {"candidates": 15, "confirmed": 10, "updated": 2, "cannot_verify": 3},
        },
        {"engine": "specialty_deepener", "results": {"thin_specialties_found": 2, "research_queued": 4}},
        {"engine": "world_monitor", "results": {"changes_detected": 2}},
    ]
    metrics = aggregate_engine_results(runs)
    assert metrics["corrections_written"] == 3
    assert metrics["gaps_filled"] == 8
    assert metrics["insights_verified"] == 12
    assert metrics["insights_updated"] == 2
    assert metrics["changes_detected"] == 2
    assert metrics["engine_runs_summarized"] == 5


def test_build_briefing_prompt_contains_all_sections():
    from core.engine.sentinel.engines.briefing import build_briefing_prompt

    metrics = {
        "corrections_written": 3,
        "gaps_filled": 8,
        "insights_verified": 12,
        "insights_updated": 2,
        "changes_detected": 2,
        "conflicts_found": 2,
        "proposals_pending": 3,
        "staleness_warnings": 5,
        "total_active_insights": 347,
        "insights_delta": 14,
        "specialty_improvements": [],
        "engine_runs_summarized": 5,
    }
    engine_details = {
        "failure_analysis": {"failures_analyzed": 3, "corrections_written": 3},
    }

    prompt = build_briefing_prompt(metrics, engine_details, "Acme Design System")
    assert "ACE Intelligence Briefing" in prompt
    assert "OVERNIGHT IMPROVEMENTS" in prompt
    assert "ATTENTION NEEDED" in prompt
    assert "Acme Design System" in prompt


@pytest.mark.asyncio
async def test_run_briefing_generator_creates_briefing():
    from core.engine.sentinel.engines.briefing import run_briefing_generator

    # Voice rendering refactor (2026-04-29): build_briefing_payload + compose_morning_briefing
    # replace the LLM-prompt path. The test mocks those higher-level functions so it stays
    # a unit test of run_briefing_generator's orchestration logic, not an integration test
    # of the entire data pipeline.
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [[]],  # last briefing (none)
            [
                [
                    {
                        "id": "engine_run:001",
                        "engine": "failure_analysis",
                        "status": "completed",
                        "results": {"failures_analyzed": 2, "corrections_written": 2},
                        "started_at": datetime(2026, 3, 23, 3, 0, tzinfo=timezone.utc),
                    }
                ]
            ],
            [[]],  # evolution_run records (none)
            [[{"count": 100}]],  # active insights
            [[{"count": 1}]],  # pending conflicts
            [[{"count": 0}]],  # pending proposals
            [[{"count": 3}]],  # stale insights
            [[]],  # efficiency metrics (composition_signal)
            [[]],  # ROI events (roi_event)
            [[]],  # calibration data
            [[]],  # adversarial review (experiment_log)
            [[]],  # proactive_signal (new synthesis signals)
            [[]],  # experimentation summary (experiment_log intelligence_variant)
            [[]],  # session_digest records (none)
            [[{"id": "briefing_payload:001"}]],  # CREATE briefing_payload
            [[]],  # product health (capability_quality)
            [[]],  # prev_result (no prior briefing to chain)
            [[{"id": "briefing:001"}]],  # CREATE briefing
        ]
    )

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    fake_payload = {
        "product_id": "product:test",
        "current_phase": "poc",
        "days_in_phase": 30,
        "next_phase": "alpha",
        "phase_floors": {
            "experience": 0.7,
            "interface": 0.5,
            "logic": 0.7,
            "state": 0.55,
            "operations": 0.35,
            "evolution": 0.55,
            "trust": 0.4,
        },
        "demo_target": None,
        "target_drift_assessment": None,
        "pillar_scores": {},
        "discipline_breakdown": {},
        "sensor_coverage": {},
        "top_recommendations": [],
        "blocked_patterns": [],
        "open_uncertainty_queries": [],
        "recent_state_changes": [],
        "contributor_activity": {},
    }

    fake_briefing_md = (
        "We're 30 days into POC — no demo target set yet.\n\n"
        "## Focus this week\n\n"
        "(no recommendations)\n\n"
        "<details>\n<summary>Engine activity from this week ▸</summary>\n\n"
        "Collapsed: 1 engines summarized — 2 corrections written.\n\n</details>"
    )

    with (
        patch("core.engine.sentinel.engines.briefing.pool", mock_pool),
        patch(
            "core.engine.sentinel.engines.briefing.build_briefing_payload",
            new=AsyncMock(return_value=fake_payload),
        ),
        patch(
            "core.engine.voice.briefing.compose_morning_briefing",
            new=AsyncMock(return_value=fake_briefing_md),
        ),
        patch(
            "core.engine.extensions.registry.registered_briefing_sections",
            new=lambda: [],
        ),
    ):
        result = await run_briefing_generator("product:test")

    assert result["briefings_generated"] == 1
