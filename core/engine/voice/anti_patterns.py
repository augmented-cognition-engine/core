from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.engine.proactive.models import ProactiveLine

_PHRASE_PREFIX = 80
_PHRASE_WINDOW_DAYS = 7


def detect_exact_phrase_repetition(candidate: str, recent: list[ProactiveLine]) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_PHRASE_WINDOW_DAYS)
    cand_prefix = candidate[:_PHRASE_PREFIX]
    return any(
        (
            # Both share the same first N chars where N = min(len(history_line), _PHRASE_PREFIX)
            h.line[:_PHRASE_PREFIX] == cand_prefix[: len(h.line[:_PHRASE_PREFIX])]
            or h.line[:_PHRASE_PREFIX] == cand_prefix
        )
        and h.generated_at >= cutoff
        for h in recent
    )


async def detect_over_reference(thread) -> bool:
    """Same thread referenced > 6 times in last 14 days without state change."""
    from core.engine.core.db import parse_rows, pool

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT count() AS c FROM voice_thread_event
               WHERE thread = <record>$tid
                 AND kind = 're_referenced'
                 AND occurred_at > time::now() - 14d
               GROUP ALL""",
                {"tid": thread.id},
            )
        )
    count = int(rows[0].get("c", 0)) if rows else 0
    return count > 6


def detect_silent_drop(thread) -> bool:
    """Open thread with mention_count >= 1, both timestamps older than 14d.

    Translation: thread is open, we mentioned it at some point, but neither we
    nor the world have moved in 14 days. ACE is going quiet on something.
    """
    if thread.status != "open" or thread.mention_count < 1:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    return thread.last_referenced_at < cutoff and thread.last_state_changed_at < cutoff
