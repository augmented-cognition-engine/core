import pytest


@pytest.mark.asyncio
async def test_write_thread_event(db_pool):
    from core.engine.voice.thread import _ensure_thread
    from core.engine.voice.thread_event import write_thread_event

    pid = "product:platform"
    topic = "rec:experience.test_event_1"

    async with db_pool.connection() as db:
        await db.query(
            """DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t;
               DELETE voice_thread_event WHERE product = <record>$pid""",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    await write_thread_event(thread, kind="raised", details={})
    await write_thread_event(thread, kind="re_referenced", details={"emitted": True})

    from core.engine.core.db import parse_rows

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT kind, details, occurred_at FROM voice_thread_event WHERE thread = <record>$tid ORDER BY occurred_at",
                {"tid": thread.id},
            )
        )
    kinds = [r["kind"] for r in rows]
    assert "raised" in kinds
    assert "re_referenced" in kinds
