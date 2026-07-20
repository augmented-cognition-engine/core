"""Sentinel engine: Voice Thread Sweeper.

Runs twice daily at 06:00 and 18:00. Transitions open voice_threads to 'stale'
when they meet time-based criteria:

  Rule 1: mention_count == 1 AND last_referenced_at > 14d ago
          → single-mention thread went quiet; mark stale.

  Rule 2: mention_count >= 5 AND last_state_changed_at > 21d ago
          → heavily-referenced thread with no state change in 21d; mark stale.

Writes a 'stale_sweep' event to voice_thread_event for each transitioned thread.
"""

from __future__ import annotations

import logging

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


async def sweep_stale_threads(product_id: str) -> dict:
    """Sweep open voice threads for the product and mark stale ones.

    Returns a summary dict for the engine result record.
    """
    from core.engine.core.db import parse_rows, pool
    from core.engine.voice.thread import _row_to_thread
    from core.engine.voice.thread_event import write_thread_event

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM voice_thread
                   WHERE product = <record>$pid
                     AND status = 'open'
                     AND (
                       (mention_count = 1 AND last_referenced_at < time::now() - 14d)
                       OR
                       (mention_count >= 5 AND last_state_changed_at < time::now() - 21d)
                     )
                """,
                {"pid": product_id},
            )
        )

    transitioned = 0
    for row in rows:
        try:
            thread = _row_to_thread(row)
            await write_thread_event(
                thread,
                kind="stale_sweep",
                details={
                    "mention_count": thread.mention_count,
                    "rule": ("single_mention_14d" if thread.mention_count == 1 else "high_mention_21d"),
                },
            )
            async with pool.connection() as db:
                await db.query(
                    """UPDATE <record>$tid SET
                        status = 'stale',
                        last_state_changed_at = time::now()
                    """,
                    {"tid": thread.id},
                )
            transitioned += 1
        except Exception as exc:
            logger.warning(
                "voice_thread_sweeper: failed to transition thread %s: %s",
                row.get("id"),
                exc,
            )

    logger.info(
        "voice_thread_sweeper: %d thread(s) transitioned to stale for %s",
        transitioned,
        product_id,
    )
    return {"transitioned_to_stale": transitioned, "product_id": product_id}


@register_engine(
    "voice_thread_sweeper",
    "0 6,18 * * *",
    "Sweep stale open voice_threads twice daily (14d single-mention, 21d high-mention)",
)
async def run_voice_thread_sweeper(product_id: str) -> dict:
    """Sentinel entry point — delegates to sweep_stale_threads."""
    return await sweep_stale_threads(product_id)
