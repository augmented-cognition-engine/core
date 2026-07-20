"""Tests for voice_thread_sweeper @register_engine sentinel."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_sweeper_transitions_single_mention_old_thread_to_stale(db_pool):
    """Open thread with mention_count == 1 and last_referenced_at > 14d ago → stale."""
    from datetime import datetime, timedelta, timezone

    from core.engine.core.db import pool
    from core.engine.voice.thread import _ensure_thread, read_voice_thread

    pid = "product:platform"
    topic = "rec:experience.sweep_single_old"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")

    # Backdate: mention_count=1, last_referenced_at > 14d ago
    stale_date = (datetime.now(timezone.utc) - timedelta(days=16)).isoformat()
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$tid SET
                mention_count = 1,
                last_referenced_at = <datetime>$d,
                last_state_changed_at = <datetime>$d
            """,
            {"tid": thread.id, "d": stale_date},
        )

    from core.engine.sentinel.engines.voice_thread_sweeper import sweep_stale_threads

    await sweep_stale_threads(pid)

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "stale", f"expected stale, got {updated.status}"


@pytest.mark.asyncio
async def test_sweeper_transitions_high_mention_long_stale_to_stale(db_pool):
    """Open thread with mention_count >= 5 and last_state_changed_at > 21d ago → stale."""
    from datetime import datetime, timedelta, timezone

    from core.engine.core.db import pool
    from core.engine.voice.thread import _ensure_thread, read_voice_thread

    pid = "product:platform"
    topic = "rec:experience.sweep_high_mention"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")

    stale_date = (datetime.now(timezone.utc) - timedelta(days=23)).isoformat()
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$tid SET
                mention_count = 5,
                last_referenced_at = <datetime>$d,
                last_state_changed_at = <datetime>$d
            """,
            {"tid": thread.id, "d": stale_date},
        )

    from core.engine.sentinel.engines.voice_thread_sweeper import sweep_stale_threads

    await sweep_stale_threads(pid)

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "stale", f"expected stale, got {updated.status}"


@pytest.mark.asyncio
async def test_sweeper_idempotent(db_pool):
    """Running sweeper twice on same stale thread doesn't error."""
    from datetime import datetime, timedelta, timezone

    from core.engine.core.db import pool
    from core.engine.voice.thread import _ensure_thread, read_voice_thread

    pid = "product:platform"
    topic = "rec:experience.sweep_idempotent"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")

    stale_date = (datetime.now(timezone.utc) - timedelta(days=16)).isoformat()
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$tid SET
                mention_count = 1,
                last_referenced_at = <datetime>$d,
                last_state_changed_at = <datetime>$d
            """,
            {"tid": thread.id, "d": stale_date},
        )

    from core.engine.sentinel.engines.voice_thread_sweeper import sweep_stale_threads

    await sweep_stale_threads(pid)
    await sweep_stale_threads(pid)  # second call — must not raise

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "stale"


def test_sweeper_is_registered():
    """voice_thread_sweeper is importable and @register_engine cron is correct."""
    import core.engine.sentinel.engines.voice_thread_sweeper  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "voice_thread_sweeper" in engine_registry
    entry = engine_registry["voice_thread_sweeper"]
    assert entry["cron"] == "0 6,18 * * *"
