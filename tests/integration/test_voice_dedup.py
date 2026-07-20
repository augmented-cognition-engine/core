"""ProactiveLine dedup integration — same topic same day fires once."""

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_dedup_same_topic_same_day():
    from core.engine.voice.stream import emit_proactive_line

    payload = {"product_id": "product:platform", "n_total": 15, "n_blocked": 11, "blocking_pillars": ["experience"]}
    line1 = await emit_proactive_line("canvas.drift.crossed", payload, recent_history=[])
    assert line1 is not None
    line2 = await emit_proactive_line("canvas.drift.crossed", payload, recent_history=[line1])
    assert line2 is None  # same topic, same day → silent


@pytest.mark.asyncio
async def test_different_topic_same_day_both_emit():
    from core.engine.voice.stream import emit_proactive_line

    drift_payload = {"product_id": "product:platform", "n_total": 15, "n_blocked": 11, "blocking_pillars": []}
    rec_payload = {
        "product_id": "product:platform",
        "top_pillar": "experience",
        "top_discipline": "accessibility",
        "swap": True,
        "rec": {"pillar": "experience", "discipline": "accessibility", "gap": 0.5, "blocking_patterns": []},
    }
    line1 = await emit_proactive_line("canvas.drift.crossed", drift_payload, [])
    assert line1 is not None
    line2 = await emit_proactive_line("canvas.recommendation.shifted", rec_payload, [line1])
    assert line2 is not None
    assert line1.topic != line2.topic


@pytest.mark.asyncio
async def test_low_priority_below_threshold_silent():
    from core.engine.proactive.models import ProactiveLine, ProactiveSource
    from core.engine.voice.stream import should_emit

    candidate = ProactiveLine(
        product_id="product:platform",
        line="we did a thing",
        source=ProactiveSource.SENTINEL,
        source_artifact_id="x",
        drill_down_url="/x",
        severity=0.3,
        generated_at=datetime.now(timezone.utc),
        priority="LOW",
        topic="capability:auth",
    )
    assert should_emit(candidate, [], threshold="HIGH") is False
