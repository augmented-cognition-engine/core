from __future__ import annotations

from core.engine.core.db import pool
from core.engine.voice.thread import VoiceThread


async def write_thread_event(
    thread: VoiceThread,
    kind: str,
    details: dict | None = None,
) -> None:
    """Append-only event log for a voice_thread. Caller must update voice_thread state separately."""
    async with pool.connection() as db:
        await db.query(
            """CREATE voice_thread_event CONTENT {
                thread: <record>$tid,
                product: <record>$pid,
                occurred_at: time::now(),
                kind: <string>$kind,
                details: $details
            }""",
            {"tid": thread.id, "pid": thread.product_id, "kind": kind, "details": details or {}},
        )
