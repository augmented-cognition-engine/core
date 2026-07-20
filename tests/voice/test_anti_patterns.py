from datetime import datetime, timedelta, timezone

import pytest

from core.engine.proactive.models import ProactiveLine, ProactiveSource


def _make(line, days_ago=0):
    return ProactiveLine(
        product_id="product:platform",
        line=line,
        source=ProactiveSource.SENTINEL,
        source_artifact_id="x",
        drill_down_url="/x",
        severity=0.5,
        generated_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        priority="HIGH",
        topic="rec:experience.ux",
    )


def test_exact_phrase_repetition_triggers_within_7d():
    from core.engine.voice.anti_patterns import detect_exact_phrase_repetition

    history = [_make("we should look at this thing right now", days_ago=2)]
    candidate = "we should look at this thing right now and now also"
    assert detect_exact_phrase_repetition(candidate, history) is True


def test_exact_phrase_repetition_does_not_trigger_after_7d():
    from core.engine.voice.anti_patterns import detect_exact_phrase_repetition

    history = [_make("we should look at this thing right now", days_ago=8)]
    candidate = "we should look at this thing right now and now also"
    assert detect_exact_phrase_repetition(candidate, history) is False


@pytest.mark.asyncio
async def test_over_reference_detects_seven_in_fourteen_days(db_pool):
    from core.engine.voice.anti_patterns import detect_over_reference
    from core.engine.voice.thread import _ensure_thread
    from core.engine.voice.thread_event import write_thread_event

    pid = "product:platform"
    topic = "rec:experience.test_over_ref"
    async with db_pool.connection() as db:
        await db.query(
            """DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t;
               DELETE voice_thread_event WHERE product = <record>$pid""",
            {"pid": pid, "t": topic},
        )
    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    for _ in range(7):
        await write_thread_event(thread, kind="re_referenced", details={"emitted": True})

    assert await detect_over_reference(thread) is True


@pytest.mark.asyncio
async def test_over_reference_silent_below_threshold(db_pool):
    from core.engine.voice.anti_patterns import detect_over_reference
    from core.engine.voice.thread import _ensure_thread
    from core.engine.voice.thread_event import write_thread_event

    pid = "product:platform"
    topic = "rec:experience.test_under_ref"
    async with db_pool.connection() as db:
        await db.query(
            """DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t;
               DELETE voice_thread_event WHERE product = <record>$pid""",
            {"pid": pid, "t": topic},
        )
    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    for _ in range(3):
        await write_thread_event(thread, kind="re_referenced", details={"emitted": True})

    assert await detect_over_reference(thread) is False


@pytest.mark.asyncio
async def test_silent_drop_detects_old_thread(db_pool):
    from core.engine.voice.anti_patterns import detect_silent_drop

    # Stub thread: open, last_referenced > 14d ago, last_state_changed > 14d ago
    class _Stub:
        status = "open"
        mention_count = 1
        last_referenced_at = datetime.now(timezone.utc) - timedelta(days=20)
        last_state_changed_at = datetime.now(timezone.utc) - timedelta(days=20)

    assert detect_silent_drop(_Stub()) is True


@pytest.mark.asyncio
async def test_silent_drop_silent_for_recent_reference(db_pool):
    from core.engine.voice.anti_patterns import detect_silent_drop

    class _Stub:
        status = "open"
        mention_count = 1
        last_referenced_at = datetime.now(timezone.utc) - timedelta(days=3)
        last_state_changed_at = datetime.now(timezone.utc) - timedelta(days=20)

    assert detect_silent_drop(_Stub()) is False
