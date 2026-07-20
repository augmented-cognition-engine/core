from datetime import datetime, timedelta, timezone

from core.engine.proactive.models import ProactiveLine, ProactiveSource


def _make_line(*, priority="HIGH", topic="rec:experience.accessibility", offset_minutes=0, day_offset=0):
    return ProactiveLine(
        product_id="product:platform",
        line="we should look at this",
        source=ProactiveSource.SENTINEL,
        source_artifact_id="x",
        drill_down_url="/x",
        severity=0.5,
        generated_at=datetime.now(timezone.utc) + timedelta(days=day_offset, minutes=offset_minutes),
        priority=priority,
        topic=topic,
    )


def test_should_emit_passes_when_no_history():
    from core.engine.voice.stream import should_emit

    assert should_emit(_make_line(), [], threshold="LOW") is True


def test_should_emit_blocks_below_threshold():
    from core.engine.voice.stream import should_emit

    candidate = _make_line(priority="LOW")
    assert should_emit(candidate, [], threshold="HIGH") is False


def test_should_emit_blocks_same_topic_today():
    from core.engine.voice.stream import should_emit

    history = [_make_line(topic="rec:exp.acc")]
    candidate = _make_line(topic="rec:exp.acc", offset_minutes=10)
    assert should_emit(candidate, history) is False


def test_should_emit_passes_different_topic_today():
    from core.engine.voice.stream import should_emit

    history = [_make_line(topic="rec:exp.acc")]
    candidate = _make_line(topic="rec:exp.ux", offset_minutes=10)
    assert should_emit(candidate, history) is True


def test_should_emit_passes_same_topic_yesterday():
    from core.engine.voice.stream import should_emit

    history = [_make_line(topic="rec:exp.acc", day_offset=-1)]
    candidate = _make_line(topic="rec:exp.acc")
    assert should_emit(candidate, history) is True


def test_should_emit_legacy_priority_none_bypasses_gate():
    from core.engine.voice.stream import should_emit

    candidate = _make_line(priority=None)
    history = [_make_line(topic=candidate.topic)]
    # priority is None → returns True regardless of dedup
    assert should_emit(candidate, history) is True
