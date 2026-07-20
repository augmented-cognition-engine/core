"""Portal voice-thread endpoints — list threads + dispatch actions.

Read endpoint (this module): GET /portal/voice-threads/{product_id}
Action endpoint (Task 6):    POST /portal/voice-threads/{thread_id}/action

Both gated on partner_panel_enabled per-product feature flag (404 when off).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.engine.api._portal_security import verify_product_access
from core.engine.core.auth import get_current_user  # match the pattern in engine/api/briefings.py:15
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.events.canvas import emit_thread_committed, emit_thread_resolved
from core.engine.voice.feature_flag import is_partner_panel_enabled
from core.engine.voice.thread import (
    _read_thread_by_id,
    apply_resolve,
    apply_snooze,
    list_active_threads,
)

router = APIRouter(prefix="/portal/voice-threads", tags=["voice-threads"])


@router.get("/{product_id}")
async def list_threads(product_id: str, user=Depends(verify_product_access)) -> dict[str, Any]:
    """Return active voice threads + the briefing they came from.

    Each thread carries `originating_event` (journey_event record id, or null) so the
    portal can render a "Why this →" pivot into /journey.

    The response also carries `briefing_event_id` — the journey_event whose payload
    references the latest briefing. The portal uses it for the BriefingDrawer
    "How this came together →" link. May be null when the briefing engine has not
    yet emitted `canvas.briefing.updated`; the link gracefully hides in that case.
    """
    if not await is_partner_panel_enabled(pool, product_id):
        raise HTTPException(status_code=404, detail="partner_panel_disabled")

    threads = await list_active_threads(product_id, limit=20)
    briefing_meta = await _latest_briefing_with_event(product_id)
    return {
        "threads": [
            {
                "id": t.id,
                "topic": t.topic,
                "status": t.status,
                "mention_count": t.mention_count,
                "raised_at": t.raised_at.isoformat(),
                "last_referenced_at": t.last_referenced_at.isoformat(),
                "primary_event_type": t.primary_event_type,
                "snooze_until": t.snooze_until.isoformat() if t.snooze_until else None,
                "originating_event": t.originating_event,
            }
            for t in threads
        ],
        "briefing_id": briefing_meta["briefing_id"] if briefing_meta else None,
        "briefing_event_id": briefing_meta["event_id"] if briefing_meta else None,
    }


# ---------------------------------------------------------------------------
# Action endpoint — snooze / resolve / commit
# ---------------------------------------------------------------------------


class ThreadAction(BaseModel):
    kind: Literal["snooze", "resolve", "commit"]
    snooze_days: int = Field(default=7, ge=1, le=30)
    note: Optional[str] = None
    expected_status: Optional[str] = None


@router.post("/{thread_id}/action")
async def dispatch_action(
    thread_id: str,
    action: ThreadAction,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """Dispatch a user action (snooze / resolve / commit) on a voice thread."""
    thread = await _read_thread_by_id(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread_not_found")
    if not await is_partner_panel_enabled(pool, thread.product_id):
        raise HTTPException(status_code=404, detail="partner_panel_disabled")

    # Extract email regardless of whether user is a dict (test) or an object (prod).
    user_email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None) or "unknown"

    audit_id = await _write_audit(
        thread_id=thread.id,
        product_id=thread.product_id,
        kind=action.kind,
        snooze_until=(
            datetime.now(timezone.utc) + timedelta(days=action.snooze_days) if action.kind == "snooze" else None
        ),
        note=action.note,
        created_by=user_email,
    )

    if action.kind == "snooze":
        until = datetime.now(timezone.utc) + timedelta(days=action.snooze_days)
        updated = await apply_snooze(thread.id, until)
        return {"ok": True, "new_status": updated.status, "audit_id": audit_id}

    if action.kind == "resolve":
        try:
            updated = await apply_resolve(thread.id, expected_status=action.expected_status)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        await emit_thread_resolved(
            product_id=thread.product_id,
            thread_id=thread.id,
            topic=thread.topic,
            action_id=audit_id,
        )
        return {"ok": True, "new_status": updated.status, "audit_id": audit_id}

    # commit
    await emit_thread_committed(
        product_id=thread.product_id,
        thread_id=thread.id,
        topic=thread.topic,
        action_id=audit_id,
    )
    return {"ok": True, "new_status": thread.status, "audit_id": audit_id}


async def _write_audit(
    thread_id: str,
    product_id: str,
    kind: str,
    snooze_until: Optional[datetime],
    note: Optional[str],
    created_by: str,
) -> str:
    """Append an audit record and return its record ID string."""
    async with pool.connection() as db:
        result = await db.query(
            """CREATE voice_thread_action CONTENT {
                thread_id: <record>$tid,
                product: <record>$pid,
                kind: <string>$k,
                snooze_until: $until,
                note: $note,
                created_by: <string>$cb
            } RETURN *""",
            {
                "tid": thread_id,
                "pid": product_id,
                "k": kind,
                "until": snooze_until,
                "note": note,
                "cb": created_by,
            },
        )
    row = parse_one(result)
    return str(row.get("id", "")) if row else ""


async def _latest_briefing_id(product_id: str) -> Optional[str]:
    """Return the record-ID string of the most recently created briefing for a product."""
    meta = await _latest_briefing_with_event(product_id)
    return meta["briefing_id"] if meta else None


async def _latest_briefing_with_event(product_id: str) -> Optional[dict]:
    """Return {briefing_id, event_id} for the latest briefing.

    event_id is the journey_event row whose payload.briefing_id matches the
    latest briefing. Returns None when no briefing exists; event_id is None
    when no matching journey_event has been emitted yet (briefing engine
    hasn't wired up canvas.briefing.updated emission).
    """
    async with pool.connection() as db:
        brief_rows = parse_rows(
            await db.query(
                """SELECT id, created_at FROM briefing
                   WHERE product = <record>$pid
                   ORDER BY created_at DESC LIMIT 1""",
                {"pid": product_id},
            )
        )
        if not brief_rows:
            return None
        briefing_id = str(brief_rows[0]["id"])
        je_rows = parse_rows(
            await db.query(
                """SELECT id, occurred_at FROM journey_event
                   WHERE topic = 'canvas.briefing.updated'
                     AND payload.briefing_id = $bid
                   ORDER BY occurred_at DESC LIMIT 1""",
                {"bid": briefing_id},
            )
        )
    return {
        "briefing_id": briefing_id,
        "event_id": str(je_rows[0]["id"]) if je_rows else None,
    }
