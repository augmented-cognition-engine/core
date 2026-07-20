"""Reusable trigger primitives for cron-fired sentinel engines.

A trigger is `async def (product_id: str) -> bool`. The scheduler calls
it before invoking the expensive engine — False skips the engine, True
proceeds. All triggers are pure DB reads (no LLM calls) and fail-open on
errors (return True) so a trigger bug never silently disables an engine.

Source pattern: StreamBridge / Em-Garde "cheap always-on trigger + big
occasional reasoner" (https://arxiv.org/abs/2505.05467,
https://arxiv.org/abs/2603.19054).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, pool

logger = logging.getLogger(__name__)

DEFAULT_MUTATION_THRESHOLD = 5


async def _last_successful_run_time(engine_name: str, product_id: str) -> str | None:
    """Return ISO timestamp of last successful run, or None if never run."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT completed_at FROM engine_run "
            "WHERE engine = $engine AND product = <record>$product AND status = 'completed' "
            "ORDER BY completed_at DESC LIMIT 1",
            {"engine": engine_name, "product": product_id},
        )
    row = parse_one(result)
    return row.get("completed_at") if row else None


async def _count_mutations_since(product_id: str, since_ts: str | None) -> int:
    """Count product_graph mutations since the given timestamp."""
    async with pool.connection() as db:
        if since_ts is None:
            return 0  # caller checks for None
        result = await db.query(
            "SELECT count() AS n FROM journey_event "
            "WHERE product = <record>$product AND occurred_at > <datetime>$since",
            {"product": product_id, "since": since_ts},
        )
    row = parse_one(result)
    return int(row.get("n", 0)) if row else 0


async def _count_unread_signals(product_id: str) -> int:
    """Count unprocessed ace-signal rows."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT count() AS n FROM ace_signal WHERE product = <record>$product AND processed = false",
            {"product": product_id},
        )
    row = parse_one(result)
    return int(row.get("n", 0)) if row else 0


async def meaningful_change_since_last_run(
    engine_name: str,
    product_id: str,
    threshold: int = DEFAULT_MUTATION_THRESHOLD,
) -> bool:
    """Trigger: fire when product graph has mutated above `threshold` since
    this engine's last successful run.

    Returns True on:
      - No prior successful run (engine never fired before)
      - Mutation count since last run >= threshold
      - Any DB error (fail-open: never silently disable an engine)
    """
    try:
        last = await _last_successful_run_time(engine_name, product_id)
        if last is None:
            return True
        n = await _count_mutations_since(product_id, last)
        return n >= threshold
    except Exception as exc:
        logger.warning("trigger meaningful_change failed-open: %s", exc)
        return True


async def unread_signals_threshold(threshold: int, product_id: str) -> bool:
    """Trigger: fire when unread signal count >= threshold. Fail-open on error."""
    try:
        n = await _count_unread_signals(product_id)
        return n >= threshold
    except Exception as exc:
        logger.warning("trigger unread_signals failed-open: %s", exc)
        return True


async def idea_velocity_above(per_day: int, product_id: str) -> bool:
    """Trigger: fire when new-idea count over the last 24h >= `per_day`. Fail-open."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                "SELECT count() AS n FROM idea WHERE product = <record>$product AND created_at > time::now() - 1d",
                {"product": product_id},
            )
        row = parse_one(result)
        n = int(row.get("n", 0)) if row else 0
        return n >= per_day
    except Exception as exc:
        logger.warning("trigger idea_velocity failed-open: %s", exc)
        return True


async def external_signals_arrived(source: str, product_id: str) -> bool:
    """Trigger: fire when new external signals from `source` arrived since last run.

    `source` is the scanner name (e.g., 'competitive_observer', 'community_scanner').
    Fail-open on error.
    """
    try:
        async with pool.connection() as db:
            result = await db.query(
                "SELECT count() AS n FROM ace_signal "
                "WHERE product = <record>$product AND source = $source "
                "AND created_at > time::now() - 1d",
                {"product": product_id, "source": source},
            )
        row = parse_one(result)
        n = int(row.get("n", 0)) if row else 0
        return n > 0
    except Exception as exc:
        logger.warning("trigger external_signals failed-open: %s", exc)
        return True
