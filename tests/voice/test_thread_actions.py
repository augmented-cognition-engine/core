"""Tests for voice_thread action helpers — snooze, resolve, commit (state mutations only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.voice.thread import (
    _ensure_thread,
    apply_resolve,
    apply_snooze,
    list_active_threads,
)


async def _delete_thread(db_pool, pid: str, topic: str) -> None:
    """Delete any existing voice_thread row for pid+topic to guarantee a clean slate."""
    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )


@pytest.mark.asyncio
async def test_snooze_sets_snooze_until(db_pool):
    pid = "product:test_snooze_basic"
    await _delete_thread(db_pool, pid, "ux")
    thread = await _ensure_thread(pid, "ux", "canvas.score.changed")
    until = datetime.now(timezone.utc) + timedelta(days=7)
    updated = await apply_snooze(thread.id, until)
    assert updated.snooze_until is not None
    assert updated.snooze_until.date() == until.date()


@pytest.mark.asyncio
async def test_resolve_flips_status(db_pool):
    pid = "product:test_resolve"
    await _delete_thread(db_pool, pid, "ai")
    thread = await _ensure_thread(pid, "ai", "canvas.score.changed")
    assert thread.status == "open"
    updated = await apply_resolve(thread.id)
    assert updated.status == "resolved"


@pytest.mark.asyncio
async def test_list_active_threads_excludes_snoozed(db_pool):
    pid = "product:test_list_excludes_snoozed"
    await _delete_thread(db_pool, pid, "qa")
    await _delete_thread(db_pool, pid, "ops")
    open_thread = await _ensure_thread(pid, "qa", "canvas.score.changed")
    snoozed_thread = await _ensure_thread(pid, "ops", "canvas.score.changed")
    await apply_snooze(snoozed_thread.id, datetime.now(timezone.utc) + timedelta(days=7))

    threads = await list_active_threads(pid)
    topics = [t.topic for t in threads]
    assert "qa" in topics
    assert "ops" not in topics  # snoozed → filtered


@pytest.mark.asyncio
async def test_resolve_returns_409_payload_when_already_resolved(db_pool):
    pid = "product:test_409"
    await _delete_thread(db_pool, pid, "api")
    thread = await _ensure_thread(pid, "api", "canvas.score.changed")
    await apply_resolve(thread.id)
    with pytest.raises(ValueError, match="thread_state_changed"):
        await apply_resolve(thread.id, expected_status="open")
