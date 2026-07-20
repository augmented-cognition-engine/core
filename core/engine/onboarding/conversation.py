"""Onboarding conversation state module — loader + formatting helpers.

The canonical conversation copy lives in conversation_copy.json. This module
loads it once at import time and exposes formatting helpers used by both the
API layer and tests.

Seeding logic (start/record_answer/complete) lives in this module too — added
in a later task. This file is structured so the loader/helpers are isolated
and testable without DB.
"""

from __future__ import annotations

import hashlib
import json
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COPY_PATH = Path(__file__).parent / "conversation_copy.json"
COPY = json.loads(_COPY_PATH.read_text(encoding="utf-8"))


def shorten(text: str, width: int = 60) -> str:
    """Word-boundary truncation, no ellipsis. Never mid-word."""
    return textwrap.shorten(text or "", width=width, placeholder="")


def format_closing(q1: str, q2: str, q3: str, q4: str) -> str:
    """Render the closing summary using user's 4 answers, word-boundary truncated."""
    return COPY["closing_template"].format(
        q1_short=shorten(q1),
        q2_short=shorten(q2),
        q3_short=shorten(q3),
        q4_short=shorten(q4),
    )


def format_ack(question_index: int, answer: str) -> str:
    """Render an acknowledgement for a given question index (1-4)."""
    q = COPY["questions"][question_index - 1]
    return q["ack_template"].format(shortened=shorten(answer))


async def start(pool: Any, user_email: str | None, initial_prompt: str | None) -> str:
    """Create a new onboarding conversation row. Returns the conversation_id (record string)."""
    from core.engine.core.db import parse_one

    async with pool.connection() as db:
        result = parse_one(
            await db.query(
                "CREATE onboarding_conversation CONTENT { "
                "created_by: $user, answers: [], "
                "started_at: time::now() } RETURN AFTER",
                {"user": user_email},
            )
        )
    cid = str(result["id"])

    # Auto-record initial_prompt as Q1 ONLY when it's substantive (>=3 chars after strip).
    # Sub-3-char prompts are dropped silently — UI will ask Q1 fresh, no orphan conversation
    # row with a failed record_answer raise.
    if initial_prompt and len(initial_prompt.strip()) >= 3:
        await record_answer(pool, cid, question_index=1, answer=initial_prompt)

    return cid


async def record_answer(pool: Any, conversation_id: str, question_index: int, answer: str) -> dict:
    """Append an answer and return ack + next question (or None if complete)."""
    from core.engine.core.db import parse_record_id, parse_rows

    if question_index < 1 or question_index > 4:
        raise ValueError(f"question_index must be 1-4, got {question_index}")
    if not answer or len(answer.strip()) < 3:
        raise ValueError("answer must be at least 3 characters")

    rid = parse_record_id(conversation_id)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT answers FROM $cid",
                {"cid": rid},
            )
        )
        if not rows:
            raise ValueError(f"conversation {conversation_id} not found")
        current = rows[0]["answers"] or []
        next_expected = len(current) + 1
        if question_index != next_expected:
            raise ValueError(f"expected question {next_expected}, got {question_index}")

        new_answers = current + [{"q_index": question_index, "text": answer}]
        await db.query(
            "UPDATE $cid SET answers = $a",
            {"cid": rid, "a": new_answers},
        )

    ack = format_ack(question_index, answer)
    next_q = COPY["questions"][question_index] if question_index < 4 else None
    return {"ack": ack, "next_question": next_q}


async def _safe_cleanup(db, ids_to_delete: list[str], original_error: Exception) -> None:
    """Best-effort delete of partial rows on compensating cleanup. Never masks original error."""
    from core.engine.core.db import parse_record_id

    for rec_id in ids_to_delete:
        try:
            await db.query("DELETE $rid", {"rid": parse_record_id(rec_id)})
            logger.warning(
                "Onboarding compensating-delete: removed %s after failure: %s",
                rec_id,
                original_error,
            )
        except Exception as cleanup_err:
            logger.error(
                "Onboarding cleanup FAILED for %s: %s (original error: %s)",
                rec_id,
                cleanup_err,
                original_error,
            )
            # Continue — don't mask the original exception by raising here


async def complete(pool: Any, conversation_id: str) -> dict:
    """Atomically (via compensating delete) seed product + product_vision + voice_thread."""
    from core.engine.core.db import parse_one, parse_record_id, parse_rows

    async with pool.connection() as db:
        # Validate all 4 answers present
        rows = parse_rows(
            await db.query(
                "SELECT answers, completed_at, created_by FROM $cid",
                {"cid": parse_record_id(conversation_id)},
            )
        )
        if not rows:
            raise ValueError(f"conversation {conversation_id} not found")
        if rows[0].get("completed_at"):
            raise ValueError(f"conversation {conversation_id} already completed")
        answers = rows[0]["answers"] or []
        if len(answers) != 4:
            raise ValueError(f"all 4 answers required, got {len(answers)}")

        q1, q2, q3, q4 = (a["text"] for a in answers)

        # Resolve tenant: prefer caller's existing tenant, else bootstrap tenant:default.
        # `product.tenant` is required (TYPE record<tenant>, not option<>) per v054.
        #
        # The `membership` table joins user (record<user>) ↔ product (record<product>);
        # there is no `user_email` field on membership. To resolve via membership we
        # join through the user table by email. We also accept the user's direct
        # tenant on the user record as a faster-path fallback before bootstrap.
        created_by = rows[0].get("created_by")
        tenant_id = None
        if created_by:
            # Path 1: tenant from a product the user is a member of.
            t_rows = parse_rows(
                await db.query(
                    "SELECT tenant FROM product WHERE id IN "
                    "(SELECT VALUE product FROM membership "
                    "WHERE user IN (SELECT VALUE id FROM user WHERE email = $email)) "
                    "LIMIT 1",
                    {"email": created_by},
                )
            )
            if t_rows and t_rows[0].get("tenant"):
                tenant_id = str(t_rows[0]["tenant"])
            else:
                # Path 2: tenant directly on the user record (first product, no memberships yet).
                u_rows = parse_rows(
                    await db.query(
                        "SELECT tenant FROM user WHERE email = $email LIMIT 1",
                        {"email": created_by},
                    )
                )
                if u_rows and u_rows[0].get("tenant"):
                    tenant_id = str(u_rows[0]["tenant"])
        if not tenant_id:
            # Use whatever tenant exists, or bootstrap tenant:default.
            t_any = parse_rows(await db.query("SELECT id FROM tenant LIMIT 1"))
            if t_any:
                tenant_id = str(t_any[0]["id"])
            else:
                await db.query("UPSERT tenant:default SET name = 'Default Tenant'")
                tenant_id = "tenant:default"

        # 1. CREATE product
        prod = parse_one(
            await db.query(
                "CREATE product CONTENT { name: $name, description: $description, "
                "tenant: <record>$tenant, created_at: time::now() } RETURN AFTER",
                {"name": shorten(q1, 60), "description": q1, "tenant": tenant_id},
            )
        )
        product_id = str(prod["id"])
        product_name = prod["name"]

        # 2. CREATE product_vision
        try:
            vision = parse_one(
                await db.query(
                    "CREATE product_vision CONTENT { product: <record>$pid, name: $name, "
                    "description: $description, active: true, created_at: time::now() } "
                    "RETURN AFTER",
                    {"pid": product_id, "name": shorten(q1, 60), "description": q3},
                )
            )
            vision_id = str(vision["id"])
        except Exception as exc:
            await _safe_cleanup(db, [product_id], original_error=exc)
            raise

        # 3. CREATE voice_thread (full 9 fields per v093)
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            topic = q4[:200] + f" — raised {now_iso}"  # em-dash suffix is engine-internal
            payload_hash = hashlib.sha256(topic.encode()).hexdigest()[:16]
            thread = parse_one(
                await db.query(
                    "CREATE voice_thread CONTENT { topic: $topic, product: <record>$pid, "
                    "status: 'open', raised_at: time::now(), last_referenced_at: time::now(), "
                    "last_state_changed_at: time::now(), mention_count: 1, "
                    "current_payload_hash: $hash, primary_event_type: 'canvas.gap.detected' } "
                    "RETURN AFTER",
                    {"topic": topic, "pid": product_id, "hash": payload_hash},
                )
            )
            thread_id = str(thread["id"])
        except Exception as exc:
            await _safe_cleanup(db, [vision_id, product_id], original_error=exc)
            raise

        # 4. Mark conversation complete
        await db.query(
            "UPDATE $cid SET completed_at = time::now(), product_id = <record>$pid",
            {"cid": parse_record_id(conversation_id), "pid": product_id},
        )

    # Emit canvas.thread.committed with a lookup UUID, then resolve the
    # journey_event row by UUID to set voice_thread.originating_event.
    # Race-free via the unique UUID; small sleep gives the AuditLogger
    # subscriber time to fork-write.
    import asyncio
    import uuid as _uuid

    from core.engine.events.canvas import LivingCanvasEventType, Provenance, emit_canvas_event

    lookup_uuid = _uuid.uuid4().hex
    try:
        await emit_canvas_event(
            LivingCanvasEventType.THREAD_COMMITTED,
            product_id=product_id,
            payload={
                "thread_id": thread_id,
                "topic": q4,
                "product_id": product_id,
                "_lookup_uuid": lookup_uuid,
            },
            provenance=Provenance(
                source="user",
                actor_id=conversation_id,
                rationale="Thread committed via onboarding completion",
            ),
        )
        # Wait for AuditLogger to fork-write (subscriber is async)
        await asyncio.sleep(0.1)

        async with pool.connection() as db:
            je_rows = parse_rows(
                await db.query(
                    "SELECT id FROM journey_event WHERE topic = 'canvas.thread.committed' "
                    "AND payload._lookup_uuid = $u LIMIT 1",
                    {"u": lookup_uuid},
                )
            )
            if not je_rows:
                # 1 retry with longer sleep
                await asyncio.sleep(0.2)
                je_rows = parse_rows(
                    await db.query(
                        "SELECT id FROM journey_event WHERE topic = 'canvas.thread.committed' "
                        "AND payload._lookup_uuid = $u LIMIT 1",
                        {"u": lookup_uuid},
                    )
                )
            if je_rows:
                await db.query(
                    "UPDATE $tid SET originating_event = <record>$jid",
                    {"tid": parse_record_id(thread_id), "jid": str(je_rows[0]["id"])},
                )
            else:
                logger.warning(
                    "Onboarding: failed to resolve journey_event for thread %s (uuid=%s) — "
                    "originating_event left NULL; 'Why this' pivot will hide",
                    thread_id,
                    lookup_uuid,
                )
    except Exception as exc:
        # Best-effort — failure here doesn't break the onboarding completion
        logger.warning("Onboarding: originating_event wiring failed: %s", exc)

    return {"product_id": product_id, "voice_thread_id": thread_id, "name": product_name}
