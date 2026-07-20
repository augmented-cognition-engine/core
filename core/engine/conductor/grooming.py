# engine/conductor/grooming.py
"""Backlog grooming — stale ideas, stuck tracks, duplicate detection.

Triggered by conductor heartbeat (every 6 heartbeats = ~60 min).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


class BacklogGroomer:
    """Groom the backlog on a heartbeat cadence."""

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._heartbeat_count = 0

    async def maybe_groom(self, product_id: str) -> bool:
        """Called every heartbeat. Runs grooming every 6th beat (~60 min)."""
        self._heartbeat_count += 1
        if self._heartbeat_count % 6 != 0:
            return False
        await self._run_grooming(product_id)
        return True

    async def _run_grooming(self, product_id: str) -> None:
        stale = await self.detect_stale_ideas(product_id)
        if stale:
            logger.info("Found %d stale ideas", len(stale))

    async def detect_stale_ideas(self, product_id: str) -> list[dict]:
        """Ideas in captured or qualifying for >30 days with no activity."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT * FROM idea
                   WHERE product = <record>$product
                   AND status IN ['captured', 'qualifying']
                   AND updated_at < time::now() - 30d
                   ORDER BY updated_at ASC LIMIT 20""",
                {"product": product_id},
            )
        return parse_rows(result)
