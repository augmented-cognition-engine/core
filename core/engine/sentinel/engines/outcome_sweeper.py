"""Sentinel engine: Outcome Sweeper.

Runs every 4 hours. Transitions outcome_observation rows with outcome_label='open'
AND window_expires_at < now to outcome_label='ignored'.

Fast: single UPDATE query with WHERE filter on (outcome_label='open' AND window_expires_at < now).
Idempotent: re-running on already-ignored rows is a no-op.
"""

from __future__ import annotations

import logging
import sys

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


async def sweep_expired_observations(product_id: str) -> dict:
    """Sweep open outcome_observations for the product and mark expired ones as ignored.

    Returns a summary dict for the engine result record.
    """
    from core.engine.core.db import parse_rows, pool

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, product, emission_kind, pillar FROM outcome_observation
                   WHERE product = <record>$pid
                     AND outcome_label = 'open'
                     AND window_expires_at < time::now()""",
                {"pid": product_id},
            )
        )

    swept = 0
    for row in rows:
        obs_id = str(row["id"])
        try:
            from core.engine.core.db import pool

            async with pool.connection() as db:
                await db.query(
                    """UPDATE <record>$obs_id SET
                        outcome_label = 'ignored',
                        outcome_at = time::now()""",
                    {"obs_id": obs_id},
                )
            swept += 1
            # Emit a journey topic so the contributions dashboard's "we let go"
            # card can fire from sweeper-driven transitions too (mirrors the
            # detector emit at engine/learning/detector.py:172).
            from core.engine.events.bus import bus

            try:
                await bus.emit(
                    "outcome.ignored",
                    {
                        "product_id": str(row.get("product") or product_id),
                        "emission_kind": row.get("emission_kind") or "unknown",
                        "pillar": row.get("pillar") or "unknown",
                    },
                )
            except Exception as exc:
                print(f"warn: outcome.ignored emit from sweeper failed: {exc!r}", file=sys.stderr)
        except Exception as exc:
            logger.warning("outcome_sweeper: failed to transition %s: %s", obs_id, exc)

    logger.info(
        "outcome_sweeper: %d observation(s) transitioned to ignored for %s",
        swept,
        product_id,
    )
    return {"observations_swept": swept, "product_id": product_id}


@register_engine(
    "outcome_sweeper",
    "0 */4 * * *",
    "Close expired outcome windows (open → ignored) every 4 hours",
)
async def run_outcome_sweeper(product_id: str = "product:platform") -> dict:
    """Sentinel entry point — delegates to sweep_expired_observations."""
    return await sweep_expired_observations(product_id)
