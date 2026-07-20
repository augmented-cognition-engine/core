"""Recommendation decay — defeats the stuck-loop pattern.

A recommendation that has been #1 for >= DECAY_THRESHOLD consecutive briefings
without acknowledgment gets exponentially downweighted by DECAY_BASE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.engine.core.db import parse_rows

DECAY_THRESHOLD = 5
DECAY_BASE = 0.85


@dataclass
class DecayState:
    rec_id: str
    product_id: str
    consecutive_briefings_at_top: int = 0
    last_acknowledged_at: Optional[datetime] = None


async def get_decay_state(pool, rec_id: str, product_id: str) -> DecayState:
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM recommendation_decay_state WHERE rec_id = <string>$rec LIMIT 1",
            {"rec": rec_id},
        )
    rows = parse_rows(result)
    if not rows:
        return DecayState(rec_id=rec_id, product_id=product_id)
    r = rows[0]
    return DecayState(
        rec_id=rec_id,
        product_id=product_id,
        consecutive_briefings_at_top=int(r.get("consecutive_briefings_at_top", 0)),
        last_acknowledged_at=r.get("last_acknowledged_at"),
    )


async def increment_briefing_count(pool, rec_id: str, product_id: str) -> None:
    async with pool.connection() as db:
        existing = await db.query(
            "SELECT id FROM recommendation_decay_state WHERE rec_id = <string>$rec LIMIT 1",
            {"rec": rec_id},
        )
        if parse_rows(existing):
            await db.query(
                """UPDATE recommendation_decay_state SET
                    consecutive_briefings_at_top += 1,
                    last_status_change_at = time::now()
                   WHERE rec_id = <string>$rec""",
                {"rec": rec_id},
            )
        else:
            await db.query(
                """CREATE recommendation_decay_state CONTENT {
                    rec_id: <string>$rec,
                    product: <record>$pid,
                    consecutive_briefings_at_top: 1,
                    last_acknowledged_at: NONE,
                    last_status_change_at: time::now()
                }""",
                {"rec": rec_id, "pid": product_id},
            )


async def acknowledge(pool, rec_id: str) -> None:
    async with pool.connection() as db:
        await db.query(
            """UPDATE recommendation_decay_state SET
                consecutive_briefings_at_top = 0,
                last_acknowledged_at = time::now(),
                last_status_change_at = time::now()
               WHERE rec_id = <string>$rec""",
            {"rec": rec_id},
        )


def apply_decay(rank: float, consecutive_briefings_at_top: int) -> float:
    """Apply exponential decay once consecutive briefings exceeds threshold."""
    if consecutive_briefings_at_top <= DECAY_THRESHOLD:
        return rank
    excess = consecutive_briefings_at_top - DECAY_THRESHOLD
    return rank * (DECAY_BASE**excess)
