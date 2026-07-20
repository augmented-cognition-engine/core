from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from core.engine.core.db import parse_one, parse_rows, pool


@dataclass
class VoiceThread:
    id: str
    topic: str
    product_id: str
    status: str  # open|resolved|stale
    raised_at: datetime
    last_referenced_at: datetime
    last_state_changed_at: datetime
    mention_count: int
    current_payload_hash: str
    primary_event_type: str
    snooze_until: Optional[datetime] = None
    originating_event: Optional[str] = None  # journey_event:<id> deterministic pivot to /journey


def _row_to_thread(row: dict) -> VoiceThread:
    def _dt(x):
        if isinstance(x, datetime):
            return x
        if isinstance(x, str):
            return datetime.fromisoformat(x.replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    return VoiceThread(
        id=str(row.get("id", "")),
        topic=row.get("topic", ""),
        product_id=str(row.get("product", "")),
        status=row.get("status", "open"),
        raised_at=_dt(row.get("raised_at")),
        last_referenced_at=_dt(row.get("last_referenced_at")),
        last_state_changed_at=_dt(row.get("last_state_changed_at")),
        mention_count=int(row.get("mention_count", 0)),
        current_payload_hash=row.get("current_payload_hash", ""),
        primary_event_type=row.get("primary_event_type", ""),
        snooze_until=_dt(row.get("snooze_until")) if row.get("snooze_until") else None,
        originating_event=str(row["originating_event"]) if row.get("originating_event") else None,
    )


async def read_voice_thread(product_id: str, topic: str) -> Optional[VoiceThread]:
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM voice_thread
                   WHERE product = <record>$pid AND topic = <string>$t LIMIT 1""",
                {"pid": product_id, "t": topic},
            )
        )
    if not rows:
        return None
    return _row_to_thread(rows[0])


async def _ensure_thread(product_id: str, topic: str, event_type: str) -> VoiceThread:
    """Get-or-create the thread for this (product, topic). Idempotent."""
    existing = await read_voice_thread(product_id, topic)
    if existing:
        return existing

    async with pool.connection() as db:
        result = await db.query(
            """CREATE voice_thread CONTENT {
                topic: <string>$t,
                product: <record>$pid,
                status: 'open',
                raised_at: time::now(),
                last_referenced_at: time::now(),
                last_state_changed_at: time::now(),
                mention_count: 0,
                current_payload_hash: '',
                primary_event_type: <string>$evt
            } RETURN *""",
            {"t": topic, "pid": product_id, "evt": event_type},
        )
    row = parse_one(result)
    if not row:
        raise RuntimeError(f"Failed to create voice_thread for ({product_id}, {topic})")
    return _row_to_thread(row)


async def list_active_threads(product_id: str, limit: int = 20) -> list[VoiceThread]:
    """List threads for a product. Filters snoozed (snooze_until > now). Sorted: open first by raised_at asc, then resolved by last_state_changed_at desc."""
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM voice_thread
                   WHERE product = <record>$pid
                     AND (snooze_until IS NONE OR snooze_until < $now)
                   ORDER BY status ASC, raised_at ASC
                   LIMIT $lim""",
                {"pid": product_id, "now": datetime.now(timezone.utc), "lim": limit},
            )
        )
    return [_row_to_thread(r) for r in rows]


async def apply_snooze(thread_id: str, snooze_until: datetime) -> VoiceThread:
    async with pool.connection() as db:
        result = await db.query(
            """UPDATE <record>$tid SET
                 snooze_until = $until
               RETURN AFTER""",
            {"tid": thread_id, "until": snooze_until},
        )
    row = parse_one(result)
    if not row:
        raise RuntimeError(f"Failed to snooze thread {thread_id}")
    return _row_to_thread(row)


async def apply_resolve(thread_id: str, expected_status: str | None = None) -> VoiceThread:
    """Flip status to resolved. If expected_status provided and current != expected, raise ValueError('thread_state_changed')."""
    if expected_status is not None:
        current = await _read_thread_by_id(thread_id)
        if current is None or current.status != expected_status:
            raise ValueError(f"thread_state_changed:current={current.status if current else 'missing'}")

    async with pool.connection() as db:
        result = await db.query(
            """UPDATE <record>$tid SET
                 status = 'resolved',
                 last_state_changed_at = time::now()
               RETURN AFTER""",
            {"tid": thread_id},
        )
    row = parse_one(result)
    if not row:
        raise RuntimeError(f"Failed to resolve thread {thread_id}")
    return _row_to_thread(row)


async def _read_thread_by_id(thread_id: str) -> Optional[VoiceThread]:
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM <record>$tid",
                {"tid": thread_id},
            )
        )
    return _row_to_thread(rows[0]) if rows else None
