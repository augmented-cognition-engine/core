"""Tests for bus-subscriber state transitions (resolved/reopened/answered)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_resolved_event_transitions_open_to_resolved(db_pool):
    """canvas.recommendation.resolved → voice_thread.status open → resolved."""
    from core.engine.voice.thread import _ensure_thread, read_voice_thread
    from core.engine.voice.transitions import on_recommendation_resolved

    pid = "product:platform"
    topic = "rec:experience.trans_resolved"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")
    assert thread.status == "open"

    await on_recommendation_resolved(
        "canvas.recommendation.resolved",
        {"product_id": pid, "top_pillar": "experience", "top_discipline": "trans_resolved"},
    )

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "resolved"


@pytest.mark.asyncio
async def test_reopened_event_transitions_resolved_to_open(db_pool):
    """canvas.recommendation.reopened → voice_thread.status resolved → open."""
    from core.engine.core.db import pool
    from core.engine.voice.thread import _ensure_thread, read_voice_thread
    from core.engine.voice.transitions import on_recommendation_reopened

    pid = "product:platform"
    topic = "rec:experience.trans_reopened"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    thread = await _ensure_thread(pid, topic, "canvas.recommendation.shifted")

    # Force to resolved state first
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$tid SET status = 'resolved', last_state_changed_at = time::now()",
            {"tid": thread.id},
        )

    await on_recommendation_reopened(
        "canvas.recommendation.reopened",
        {"product_id": pid, "top_pillar": "experience", "top_discipline": "trans_reopened"},
    )

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "open"


@pytest.mark.asyncio
async def test_uncertainty_answered_transitions_to_resolved(db_pool):
    """canvas.uncertainty.answered → voice_thread for uncertainty topic transitions open → resolved."""
    from core.engine.voice.thread import _ensure_thread, read_voice_thread
    from core.engine.voice.transitions import on_uncertainty_answered

    pid = "product:platform"
    query_id = "q:trans_answered"
    topic = f"uncertainty:{query_id}"

    async with db_pool.connection() as db:
        await db.query(
            "DELETE voice_thread WHERE product = <record>$pid AND topic = <string>$t",
            {"pid": pid, "t": topic},
        )

    await _ensure_thread(pid, topic, "canvas.uncertainty.opened")

    await on_uncertainty_answered(
        "canvas.uncertainty.answered",
        {"product_id": pid, "query_id": query_id},
    )

    updated = await read_voice_thread(pid, topic)
    assert updated is not None
    assert updated.status == "resolved"
