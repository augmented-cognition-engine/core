import pytest


@pytest.mark.asyncio
async def test_ensure_thread_creates_when_missing(db_pool):
    from core.engine.voice.thread import _ensure_thread

    pid = "product:platform"
    topic = "rec:experience.test_topic_1"

    # Cleanup from any prior runs
    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    assert thread.topic == topic
    assert thread.status == "open"
    assert thread.mention_count == 0


@pytest.mark.asyncio
async def test_ensure_thread_idempotent(db_pool):
    from core.engine.voice.thread import _ensure_thread

    pid = "product:platform"
    topic = "rec:experience.test_topic_2"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    t1 = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    t2 = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    assert t1.topic == t2.topic
    assert t1.raised_at == t2.raised_at  # didn't recreate
