# tests/test_briefing_proactive_signals.py
"""Tests for ProactiveSignal injection into ace_briefing.

Two behaviours:
  1. build_briefing_prompt includes a PROACTIVE INTELLIGENCE section when
     metrics["proactive_signals"] is non-empty; omits it when empty.
  2. run_briefing_generator queries proactive_signal and marks records seen
     after the briefing is persisted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Prompt-level tests (pure function) ───────────────────────────────────────


def test_build_briefing_prompt_includes_proactive_signals():
    """Prompt contains PROACTIVE INTELLIGENCE section when signals are present."""
    from core.engine.sentinel.engines.briefing import build_briefing_prompt

    metrics = {
        "corrections_written": 0,
        "gaps_filled": 0,
        "insights_verified": 0,
        "insights_updated": 0,
        "changes_detected": 0,
        "conflicts_found": 0,
        "proposals_pending": 0,
        "staleness_warnings": 0,
        "total_active_insights": 0,
        "insights_delta": 0,
        "specialty_improvements": [],
        "engine_runs_summarized": 1,
        "proactive_signals": [
            {
                "event_type": "pr.merged",
                "summary": "Merge introduced coupling between billing and auth modules",
            },
        ],
    }
    prompt = build_briefing_prompt(metrics, {}, "Acme Corp")
    assert "PROACTIVE INTELLIGENCE" in prompt
    assert "billing and auth" in prompt


def test_build_briefing_prompt_omits_section_when_no_signals():
    """PROACTIVE INTELLIGENCE section is absent when signals list is empty."""
    from core.engine.sentinel.engines.briefing import build_briefing_prompt

    metrics = {
        "corrections_written": 0,
        "gaps_filled": 0,
        "insights_verified": 0,
        "insights_updated": 0,
        "changes_detected": 0,
        "conflicts_found": 0,
        "proposals_pending": 0,
        "staleness_warnings": 0,
        "total_active_insights": 0,
        "insights_delta": 0,
        "specialty_improvements": [],
        "engine_runs_summarized": 1,
        "proactive_signals": [],
    }
    prompt = build_briefing_prompt(metrics, {}, "Acme Corp")
    assert "PROACTIVE INTELLIGENCE" not in prompt


def test_build_briefing_prompt_omits_section_when_key_absent():
    """PROACTIVE INTELLIGENCE section absent when key not in metrics (backward compat)."""
    from core.engine.sentinel.engines.briefing import build_briefing_prompt

    metrics = {
        "corrections_written": 0,
        "gaps_filled": 0,
        "insights_verified": 0,
        "insights_updated": 0,
        "changes_detected": 0,
        "conflicts_found": 0,
        "proposals_pending": 0,
        "staleness_warnings": 0,
        "total_active_insights": 0,
        "insights_delta": 0,
        "specialty_improvements": [],
        "engine_runs_summarized": 1,
        # No "proactive_signals" key
    }
    prompt = build_briefing_prompt(metrics, {}, "Acme Corp")
    assert "PROACTIVE INTELLIGENCE" not in prompt


# ── Generator-level tests (async, with DB mock) ───────────────────────────────

_ENGINE_RUN = {
    "id": "engine_run:001",
    "engine": "failure_analysis",
    "status": "completed",
    "results": {"failures_analyzed": 1, "corrections_written": 1},
    "started_at": datetime(2026, 3, 23, 3, 0, tzinfo=timezone.utc),
}

_PROACTIVE_SIGNAL_ROW = {
    "id": "proactive_signal:001",
    "event_type": "pr.merged",
    "summary": "Auth-billing coupling risk detected",
    "leverage_points": [],
    "status": "new",
    "product": "product:test",
}


def _build_mock_db(proactive_rows=None):
    """Build a mock DB with correct query side_effect sequence including proactive signals.

    Query order matches briefing.py post-voice-rendering refactor:
      last_briefing, engine_run, evolution_run,
      active_insights, conflicts, proposals, stale,
      efficiency, roi, calibration, adversarial,
      proactive_signal, experimentation, session_digest,
      CREATE briefing_payload (NEW post-refactor),
      product_health, prev_result, CREATE briefing, mark_seen UPDATE
    """
    if proactive_rows is None:
        proactive_rows = [_PROACTIVE_SIGNAL_ROW]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [[]],  # last briefing
            [[_ENGINE_RUN]],  # engine_run records
            [[]],  # evolution_run
            [[{"count": 50}]],  # active insights
            [[{"count": 0}]],  # conflicts
            [[{"count": 0}]],  # proposals
            [[{"count": 0}]],  # stale insights
            [[]],  # efficiency (composition_signal)
            [[]],  # ROI (roi_event)
            [[]],  # calibration
            [[]],  # adversarial (experiment_log)
            [proactive_rows],  # proactive_signal
            [[]],  # experimentation (experiment_log intelligence_variant)
            [[]],  # session_digest
            [[{"id": "briefing_payload:001"}]],  # CREATE briefing_payload (NEW)
            [[]],  # product health (capability_quality)
            [[]],  # prev_result
            [[{"id": "briefing:001"}]],  # CREATE briefing
            [[]],  # mark_seen UPDATE
        ]
    )
    return mock_db


_FAKE_PAYLOAD = {
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

_FAKE_BRIEFING_MD = "We're 30 days into POC.\n\n## Focus this week\n\n(none)\n"


@pytest.mark.asyncio
async def test_run_briefing_generator_queries_proactive_signals():
    """Briefing generator queries the proactive_signal table for new signals."""
    from core.engine.sentinel.engines.briefing import run_briefing_generator

    mock_db = _build_mock_db()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.sentinel.engines.briefing.pool", mock_pool),
        patch(
            "core.engine.sentinel.engines.briefing.build_briefing_payload",
            new=AsyncMock(return_value=_FAKE_PAYLOAD),
        ),
        patch(
            "core.engine.voice.briefing.compose_morning_briefing",
            new=AsyncMock(return_value=_FAKE_BRIEFING_MD),
        ),
        patch(
            "core.engine.extensions.registry.registered_briefing_sections",
            new=lambda: [],
        ),
    ):
        result = await run_briefing_generator("product:test")

    assert result["briefings_generated"] == 1
    # Verify a query to proactive_signal was made
    all_queries = [str(call.args[0]) for call in mock_db.query.call_args_list]
    assert any("proactive_signal" in q for q in all_queries)


@pytest.mark.asyncio
async def test_run_briefing_generator_marks_signals_seen_after_briefing():
    """After briefing is persisted, proactive_signal records are marked seen."""
    from core.engine.sentinel.engines.briefing import run_briefing_generator

    mock_db = _build_mock_db()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.sentinel.engines.briefing.pool", mock_pool),
        patch(
            "core.engine.sentinel.engines.briefing.build_briefing_payload",
            new=AsyncMock(return_value=_FAKE_PAYLOAD),
        ),
        patch(
            "core.engine.voice.briefing.compose_morning_briefing",
            new=AsyncMock(return_value=_FAKE_BRIEFING_MD),
        ),
        patch(
            "core.engine.extensions.registry.registered_briefing_sections",
            new=lambda: [],
        ),
    ):
        await run_briefing_generator("product:test")

    all_queries = [str(call.args[0]) for call in mock_db.query.call_args_list]
    # A mark-seen UPDATE must appear AFTER the CREATE briefing.
    # Note: post-voice-rendering refactor, the briefing CREATE has a payload_ref
    # field which contains "payload" — match "CREATE briefing SET" specifically
    # to distinguish from "CREATE briefing_payload SET".
    create_idx = next(
        (i for i, q in enumerate(all_queries) if "CREATE briefing SET" in q),
        None,
    )
    update_idx = next(
        (i for i, q in enumerate(all_queries) if "proactive_signal" in q and "seen" in q),
        None,
    )
    assert create_idx is not None, "CREATE briefing query not found"
    assert update_idx is not None, "mark-seen UPDATE not found"
    assert update_idx > create_idx, "mark-seen must happen after CREATE briefing"


@pytest.mark.skip(
    reason=(
        "Voice rendering refactor (2026-04-29) retired the LLM-prompt path. "
        "Proactive signals now flow through metrics into the briefing's structured "
        "content + the engine activity footer, not through an llm.complete() prompt. "
        "If proactive-signal surfacing in voice prose is needed, write a new test "
        "against compose_morning_briefing's footer rendering, not the LLM prompt."
    )
)
@pytest.mark.asyncio
async def test_run_briefing_generator_signals_included_in_prompt():
    pass
