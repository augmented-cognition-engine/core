import pytest


def _payload_fixture(*, n_blocked: int = 0, n_total: int = 15):
    return {
        "product_id": "product:platform",
        "current_phase": "poc",
        "days_in_phase": 45,
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
        "demo_target": {
            "name": "demo",
            "target_date": "2026-06-19",
            "required_patterns": ["a", "b"],
            "acceptance_criteria": [],
        },
        "target_drift_assessment": {
            "n_total": n_total,
            "n_blocked": n_blocked,
            "blocking_pillars": ["experience"] if n_blocked else [],
        },
        "pillar_scores": {"experience": 0.38},
        "discipline_breakdown": {"experience": {"accessibility": 0.20}},
        "sensor_coverage": {},
        "top_recommendations": [
            {"pillar": "experience", "discipline": "accessibility", "gap": 0.50, "blocking_patterns": ["a", "b"]},
            {"pillar": "experience", "discipline": "ux", "gap": 0.30, "blocking_patterns": []},
            {"pillar": "evolution", "discipline": "testing", "gap": 0.55, "blocking_patterns": []},
        ],
        "blocked_patterns": [],
        "open_uncertainty_queries": [],
        "recent_state_changes": [],
        "contributor_activity": {},
    }


@pytest.mark.asyncio
async def test_compose_morning_briefing_has_lede_focus_no_questions():
    from core.engine.voice.briefing import compose_morning_briefing

    md = await compose_morning_briefing(_payload_fixture(n_blocked=11), engine_runs=[])
    assert "POC" in md or "poc" in md
    assert "## Focus this week" in md
    assert "accessibility" in md.lower()
    assert "## Open questions" not in md  # no questions in fixture
    assert "<details>" in md


@pytest.mark.asyncio
async def test_compose_morning_briefing_includes_open_questions_when_present():
    from core.engine.voice.briefing import compose_morning_briefing

    p = _payload_fixture()
    p["open_uncertainty_queries"] = [{"id": "uq:1", "scope": "ambition", "question": "Is X still in scope?"}]
    md = await compose_morning_briefing(p, engine_runs=[])
    assert "## Open questions" in md


@pytest.mark.asyncio
async def test_compose_morning_briefing_passes_voice_audit():
    from core.engine.voice.audit import audit_partner_voice
    from core.engine.voice.briefing import compose_morning_briefing

    md = await compose_morning_briefing(_payload_fixture(n_blocked=11), engine_runs=[])
    result = audit_partner_voice(md)
    assert result.passed, f"audit violations: {result.violations}"


@pytest.mark.asyncio
async def test_compose_morning_briefing_thread_aware_framing(db_pool):
    """When voice continuity is enabled and a thread exists with mention_count >= 3,
    render_recommendation uses stale / re-referenced framing instead of first-time framing."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock, patch

    from core.engine.voice.briefing import compose_morning_briefing
    from core.engine.voice.thread import VoiceThread

    now = datetime.now(timezone.utc)
    stub_thread = VoiceThread(
        id="voice_thread:stub1",
        topic="rec:experience.accessibility",
        product_id="product:platform",
        status="open",
        raised_at=now - timedelta(days=14),
        last_referenced_at=now - timedelta(days=2),
        last_state_changed_at=now - timedelta(days=14),
        mention_count=4,
        current_payload_hash="old_hash",
        primary_event_type="canvas.recommendation.shifted",
    )

    # Patch: flag enabled, thread found
    with (
        patch("core.engine.voice.briefing.is_voice_continuity_enabled", new=AsyncMock(return_value=True)),
        patch("core.engine.voice.briefing.read_voice_thread", new=AsyncMock(return_value=stub_thread)),
    ):
        md = await compose_morning_briefing(_payload_fixture(n_blocked=11), engine_runs=[])

    # mention_count >= 3 + payload_unchanged => "still where we left it" framing
    assert "## Focus this week" in md
    assert "still" in md.lower() or "sat on" in md.lower() or "moved" in md.lower()
