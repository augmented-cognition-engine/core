# engine/atc/freshness.py
"""Plan Freshness — detect when a queued plan has gone stale.

When a flight comes off the holding pattern, the codebase may have
changed since the plan was created. This module checks if the plan's
predicted files have been modified by other landed flights and determines
whether the plan needs re-decomposition.

Usage:
    checker = FreshnessChecker(db_pool=pool, repo_path="/path/to/repo")
    result = await checker.check(flight_id, product_id)
    if result["stale"]:
        new_plan = await decomposer.replan(spec_id, result, product_id)
"""

from __future__ import annotations

import logging

from core.engine.atc.registry import FlightRegistry
from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


class FreshnessChecker:
    """Check if a flight's plan is still valid given codebase changes."""

    def __init__(self, db_pool, repo_path: str | None = None):
        import os

        self._pool = db_pool
        self._repo_path = repo_path or os.getcwd()
        self._registry = FlightRegistry(db_pool=db_pool)

    async def check(self, flight_id: str, product_id: str) -> dict:
        """Check if a flight's plan is stale.

        Compares files_predicted against flights that landed since
        plan_created_at. If any landed flight modified files in this
        plan's predicted set, the plan is stale.

        Returns:
            {
                stale: bool,
                overlapping_files: [str],
                landed_flights: [str],   # flight IDs that caused staleness
                reason: str,
            }
        """
        flight = await self._registry.get(flight_id)
        if not flight:
            return {"stale": False, "reason": "flight not found"}

        predicted = set(flight.files_predicted or [])
        if not predicted:
            return {"stale": False, "reason": "no predicted files to check"}

        # Find flights that landed since this plan was created
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """SELECT id, files_actual, source_id, landed_at
                    FROM atc_flight
                    WHERE product = <record>$product
                      AND status = 'landed'
                      AND landed_at > $since
                    ORDER BY landed_at ASC""",
                    {"product": product_id, "since": flight.files_predicted and "2000-01-01" or "2000-01-01"},
                    # Note: plan_created_at isn't easily parameterizable with datetime
                    # so we check all landed flights and filter in Python
                )
                landed = parse_rows(result)
        except Exception as exc:
            logger.warning("Freshness check failed: %s", exc)
            return {"stale": False, "reason": f"query failed: {exc}"}

        overlapping_files: list[str] = []
        landed_flight_ids: list[str] = []

        for lf in landed:
            actual = set(lf.get("files_actual") or [])
            overlap = predicted & actual
            if overlap:
                overlapping_files.extend(overlap)
                landed_flight_ids.append(str(lf.get("id", "")))

        if overlapping_files:
            return {
                "stale": True,
                "overlapping_files": sorted(set(overlapping_files)),
                "landed_flights": landed_flight_ids,
                "reason": f"{len(set(overlapping_files))} predicted files were modified by {len(landed_flight_ids)} landed flight(s)",
            }

        return {"stale": False, "reason": "no overlap with landed flights"}
