import pytest


@pytest.mark.asyncio
async def test_dispatch_drift_crossed_returns_high_priority():
    from core.engine.voice.stream import emit_proactive_line

    payload = {
        "product_id": "product:platform",
        "prev_blocked_frac": 0.3,
        "new_blocked_frac": 0.7,
        "blocking_pillars": ["experience"],
        "n_total": 15,
        "n_blocked": 11,
    }
    line = await emit_proactive_line("canvas.drift.crossed", payload, recent_history=[])
    assert line is not None
    assert line.priority == "HIGH"
    assert line.topic == "drift"


@pytest.mark.asyncio
async def test_dispatch_score_changed_returns_none():
    """canvas.score.changed is detector-only — not voice-rendered."""
    from core.engine.voice.stream import emit_proactive_line

    line = await emit_proactive_line("canvas.score.changed", {"product_id": "p"}, [])
    assert line is None


@pytest.mark.asyncio
async def test_dispatch_handoff_progress_returns_none():
    from core.engine.voice.stream import emit_proactive_line

    line = await emit_proactive_line("canvas.handoff.progress", {"product_id": "p"}, [])
    assert line is None


@pytest.mark.asyncio
async def test_dispatch_unknown_event_returns_none():
    from core.engine.voice.stream import emit_proactive_line

    line = await emit_proactive_line("canvas.unknown.event", {"product_id": "p"}, [])
    assert line is None


@pytest.mark.asyncio
async def test_dispatch_recommendation_shifted_swap_high():
    from core.engine.voice.stream import emit_proactive_line

    payload = {
        "product_id": "product:platform",
        "top_pillar": "experience",
        "top_discipline": "accessibility",
        "swap": True,
        "rec": {"pillar": "experience", "discipline": "accessibility", "gap": 0.5, "blocking_patterns": []},
    }
    line = await emit_proactive_line("canvas.recommendation.shifted", payload, [])
    assert line is not None
    assert line.priority == "HIGH"
    assert line.topic == "rec:experience.accessibility"


@pytest.mark.asyncio
async def test_dispatch_intelligence_classified_routes_to_state_change():
    from core.engine.voice.stream import emit_proactive_line

    payload = {
        "product_id": "product:platform",
        "discipline": "ux",
        "summary": "user worked on accessibility this morning",
        "confidence": 0.85,
    }
    line = await emit_proactive_line("canvas.intelligence.classified", payload, [])
    assert line is not None
    assert line.priority == "LOW"


@pytest.mark.asyncio
async def test_dispatch_pattern_matched_routes_to_state_change():
    from core.engine.voice.stream import emit_proactive_line

    payload = {
        "product_id": "product:platform",
        "pattern_slug": "always-add-tests",
        "discipline": "testing",
        "confidence": 0.8,
    }
    line = await emit_proactive_line("canvas.pattern.matched", payload, [])
    assert line is not None
    assert line.priority == "LOW"
