"""Tests for the onboarding conversation state module."""

from __future__ import annotations

import pytest


def test_copy_loads_with_4_questions():
    from core.engine.onboarding.conversation import COPY

    assert "opening" in COPY
    assert len(COPY["questions"]) == 4
    assert COPY["closing_template"]
    for i, q in enumerate(COPY["questions"], 1):
        assert q["index"] == i
        assert q["prompt"]
        assert q["ack_template"]


def test_shorten_word_boundary_under_limit():
    from core.engine.onboarding.conversation import shorten

    assert shorten("hello world", 60) == "hello world"


def test_shorten_word_boundary_over_limit():
    from core.engine.onboarding.conversation import shorten

    text = "this is a very long answer that definitely exceeds the sixty character limit for sure"
    result = shorten(text, 60)
    assert len(result) <= 60
    # No mid-word cut — must end at a word boundary or be empty
    assert not result.endswith(" ")
    if result and " " in text[:60]:
        # Should end with the last whole word that fit
        assert text.startswith(result)


def test_format_closing():
    from core.engine.onboarding.conversation import format_closing

    out = format_closing(
        q1="A habit tracker app",
        q2="ADHD adults",
        q3="MVP launch",
        q4="onboarding friction",
    )
    assert "habit tracker app" in out
    assert "ADHD adults" in out
    assert "MVP launch" in out
    assert "onboarding friction" in out
    assert out.startswith("Got it. We're building")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_start_creates_conversation_row():
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.onboarding.conversation import start

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_user@example.com'")

    try:
        cid = await start(pool, user_email="test_user@example.com", initial_prompt="A habit tracker")
        assert cid.startswith("onboarding_conversation:")

        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT created_by, answers, product_id, completed_at FROM $cid",
                    {"cid": parse_record_id(cid)},
                )
            )
        assert len(rows) == 1
        assert rows[0]["created_by"] == "test_user@example.com"
        # initial_prompt was substantive (>=3 chars), so Q1 was auto-recorded
        assert len(rows[0]["answers"]) == 1
        assert rows[0]["answers"][0]["q_index"] == 1
        assert rows[0]["answers"][0]["text"] == "A habit tracker"
        assert rows[0].get("product_id") is None
        assert rows[0].get("completed_at") is None
    finally:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_user@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_record_answer_appends_to_array():
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.onboarding.conversation import record_answer, start

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_record@example.com'")

    try:
        cid = await start(pool, user_email="test_record@example.com", initial_prompt=None)

        result1 = await record_answer(pool, cid, question_index=1, answer="A habit tracker app")
        assert "ack" in result1
        assert "habit tracker" in result1["ack"]
        assert result1["next_question"]["index"] == 2

        result2 = await record_answer(pool, cid, question_index=2, answer="ADHD adults")
        assert "next_question" in result2 and result2["next_question"]["index"] == 3

        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT answers FROM $cid", {"cid": parse_record_id(cid)}))
        answers = rows[0]["answers"]
        assert len(answers) == 2
        assert answers[0]["q_index"] == 1 and answers[0]["text"] == "A habit tracker app"
        assert answers[1]["q_index"] == 2 and answers[1]["text"] == "ADHD adults"
    finally:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_record@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_record_answer_rejects_out_of_order():
    from core.engine.core.db import pool
    from core.engine.onboarding.conversation import record_answer, start

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_order@example.com'")

    try:
        cid = await start(pool, user_email="test_order@example.com", initial_prompt=None)
        with pytest.raises(ValueError, match="expected question 1, got 2"):
            await record_answer(pool, cid, question_index=2, answer="skipping ahead")
    finally:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_order@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_seeds_3_rows_atomically():
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.onboarding.conversation import complete, record_answer, start

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_complete@example.com'")

    result = {}  # hoisted so finally cleanup can reference it even if complete() raises
    try:
        cid = await start(pool, user_email="test_complete@example.com", initial_prompt="A habit tracker app")
        await record_answer(pool, cid, 2, "ADHD adults who lose focus")
        await record_answer(pool, cid, 3, "MVP launched and 5 paying users")
        await record_answer(pool, cid, 4, "Onboarding friction will kill activation")

        result = await complete(pool, cid)
        assert "product_id" in result
        assert "voice_thread_id" in result

        async with pool.connection() as db:
            prod_rows = parse_rows(
                await db.query(
                    "SELECT id, name, description FROM $pid",
                    {"pid": parse_record_id(result["product_id"])},
                )
            )
            assert len(prod_rows) == 1
            assert prod_rows[0]["name"] == "A habit tracker app"

            vision_rows = parse_rows(
                await db.query(
                    "SELECT id, description FROM product_vision WHERE product = $pid",
                    {"pid": parse_record_id(result["product_id"])},
                )
            )
            assert len(vision_rows) == 1
            assert vision_rows[0]["description"] == "MVP launched and 5 paying users"

            thread_rows = parse_rows(
                await db.query(
                    "SELECT id, topic, status, mention_count, primary_event_type, last_referenced_at, "
                    "last_state_changed_at, current_payload_hash FROM $tid",
                    {"tid": parse_record_id(result["voice_thread_id"])},
                )
            )
            assert len(thread_rows) == 1
            t = thread_rows[0]
            assert "Onboarding friction" in t["topic"]
            assert t["status"] == "open"
            assert t["mention_count"] == 1
            assert t["primary_event_type"] == "canvas.gap.detected"
            assert t["last_referenced_at"] is not None
            assert t["last_state_changed_at"] is not None
            assert len(t["current_payload_hash"]) == 16

            conv_rows = parse_rows(
                await db.query(
                    "SELECT completed_at, product_id, answers FROM $cid",
                    {"cid": parse_record_id(cid)},
                )
            )
            assert conv_rows[0]["completed_at"] is not None
            assert len(conv_rows[0]["answers"]) == 4
    finally:
        async with pool.connection() as db:
            if result.get("product_id"):
                pid = parse_record_id(result["product_id"])
                await db.query("DELETE voice_thread WHERE product = $pid", {"pid": pid})
                await db.query("DELETE product_vision WHERE product = $pid", {"pid": pid})
                await db.query("DELETE $pid", {"pid": pid})
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_complete@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_rejects_incomplete_conversation():
    from core.engine.core.db import pool
    from core.engine.onboarding.conversation import complete, record_answer, start

    await pool.init()
    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_incomplete@example.com'")

    try:
        cid = await start(pool, user_email="test_incomplete@example.com", initial_prompt=None)
        await record_answer(pool, cid, 1, "only answered Q1")

        with pytest.raises(ValueError, match="all 4 answers required"):
            await complete(pool, cid)
    finally:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_incomplete@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_sets_originating_event_on_thread():
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.events.audit_logger import audit_logger
    from core.engine.onboarding.conversation import complete, record_answer, start

    await pool.init()
    await audit_logger.start(pool)

    async with pool.connection() as db:
        await db.query("DELETE onboarding_conversation WHERE created_by = 'test_orig@example.com'")

    result = {}
    try:
        cid = await start(pool, user_email="test_orig@example.com", initial_prompt="Test product")
        await record_answer(pool, cid, 2, "Test customer")
        await record_answer(pool, cid, 3, "Test goal")
        await record_answer(pool, cid, 4, "Test risk for originating_event")
        result = await complete(pool, cid)

        async with pool.connection() as db:
            t_rows = parse_rows(
                await db.query(
                    "SELECT originating_event FROM $tid",
                    {"tid": parse_record_id(result["voice_thread_id"])},
                )
            )
        assert t_rows[0].get("originating_event") is not None, (
            "originating_event was not set — UUID stamp + lookup must wire it"
        )
    finally:
        async with pool.connection() as db:
            if result.get("product_id"):
                pid = parse_record_id(result["product_id"])
                await db.query("DELETE voice_thread WHERE product = <record>$pid", {"pid": result["product_id"]})
                await db.query("DELETE product_vision WHERE product = <record>$pid", {"pid": result["product_id"]})
                await db.query(
                    "DELETE journey_event WHERE topic = 'canvas.thread.committed' AND payload.product_id = $pid",
                    {"pid": result["product_id"]},
                )
                await db.query("DELETE $pid", {"pid": pid})
            await db.query("DELETE onboarding_conversation WHERE created_by = 'test_orig@example.com'")
        await audit_logger.stop()
