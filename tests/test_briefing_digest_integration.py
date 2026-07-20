"""Test that briefing engine incorporates session digests."""

import pytest


@pytest.mark.asyncio
async def test_briefing_prompt_includes_session_digests():
    """build_briefing_prompt() should include digest summaries when available."""
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
        "specialty_improvements": 0,
        "engine_runs_summarized": 0,
    }
    digests = [
        {
            "session_id": "sess-001",
            "summary": "Worked on auth module, decided on JWT approach",
            "decisions": [{"title": "Use JWT", "discipline": "security"}],
            "tasks_executed": 3,
            "disciplines_touched": ["security"],
        }
    ]

    prompt = build_briefing_prompt(metrics, {}, "test-org", session_digests=digests)
    assert "sess-001" in prompt or "JWT" in prompt or "auth" in prompt


@pytest.mark.asyncio
async def test_briefing_prompt_no_digests_unchanged():
    """build_briefing_prompt() with no digests should not include session activity section."""
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
        "specialty_improvements": 0,
        "engine_runs_summarized": 0,
    }

    prompt = build_briefing_prompt(metrics, {}, "test-org")
    assert "Session Activity" not in prompt


@pytest.mark.asyncio
async def test_briefing_prompt_digests_with_blockers():
    """build_briefing_prompt() should include blocker info from digests."""
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
        "specialty_improvements": 0,
        "engine_runs_summarized": 0,
    }
    digests = [
        {
            "session_id": "sess-002",
            "summary": "Encountered DB migration issue",
            "decisions": [],
            "blockers": [{"description": "Migration failed on prod", "status": "open"}],
            "tasks_executed": 1,
        }
    ]

    prompt = build_briefing_prompt(metrics, {}, "test-org", session_digests=digests)
    assert "Session Activity" in prompt
    assert "sess-002" in prompt
    assert "Migration failed on prod" in prompt or "Blocker" in prompt


@pytest.mark.asyncio
async def test_briefing_prompt_empty_digests_list():
    """build_briefing_prompt() with empty list should not include session activity section."""
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
        "specialty_improvements": 0,
        "engine_runs_summarized": 0,
    }

    prompt = build_briefing_prompt(metrics, {}, "test-org", session_digests=[])
    assert "Session Activity" not in prompt
