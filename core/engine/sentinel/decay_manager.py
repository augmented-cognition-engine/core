# engine/sentinel/decay_manager.py
"""Decay manager engine — category-dependent confidence decay and TTL expiry.

Daily scheduled engine: applies confidence decay to insights past their
category-dependent staleness threshold. Flags TTL-expired insights. Never deletes.

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md §4
Source: docs/ace-06-continuous-learning.md lines 338-346
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

# Category-dependent decay rates from docs/ace-06-continuous-learning.md
# Priority order: first match wins when insight has multiple tags
DECAY_CATEGORIES: list[dict[str, Any]] = [
    {"tag": "version", "threshold_days": 14, "decay_rate": 0.05},
    {"tag": "personnel", "threshold_days": 30, "decay_rate": 0.03},
    {"tag": "pricing", "threshold_days": 30, "decay_rate": 0.03},
    {"tag": "regulation", "threshold_days": 90, "decay_rate": 0.01},
    {"tag": "fact", "threshold_days": 90, "decay_rate": 0.01},
    {"tag": "process", "threshold_days": 180, "decay_rate": 0.005},
    {"tag": "decision", "threshold_days": 365, "decay_rate": 0.003},
]

DEFAULT_DECAY_CONFIG = {"threshold_days": 90, "decay_rate": 0.01}

# Utilization-based archival thresholds
_ARCHIVE_LOADED_MIN = 50
_ARCHIVE_ATTRIBUTED_MAX = 5


async def _get_db():
    """Get a DB connection from the pool. Overridden in tests via patch."""
    from core.engine.core.db import pool

    return pool


def get_decay_config(tags: list[str]) -> dict[str, Any]:
    """Determine decay threshold and rate from insight tags.

    Checks tags against DECAY_CATEGORIES in priority order.
    Returns first match, or DEFAULT_DECAY_CONFIG if no category recognized.
    """
    tag_set = set(tags) if tags else set()
    for category in DECAY_CATEGORIES:
        if category["tag"] in tag_set:
            return {
                "threshold_days": category["threshold_days"],
                "decay_rate": category["decay_rate"],
            }
    return DEFAULT_DECAY_CONFIG.copy()


def apply_decay(confidence: float, decay_rate: float) -> float:
    """Apply one day of decay: confidence - decay_rate, floored at 0.0."""
    return max(0.0, round(confidence - decay_rate, 6))


def should_decay(
    last_confirmed: datetime,
    threshold_days: int,
    now: datetime | None = None,
) -> bool:
    """Check if an insight should have decay applied.

    Decay only applies when last_confirmed is older than threshold_days.
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(last_confirmed, str):
        last_confirmed = datetime.fromisoformat(last_confirmed)
    if last_confirmed.tzinfo is None:
        last_confirmed = last_confirmed.replace(tzinfo=timezone.utc)
    return (now - last_confirmed) > timedelta(days=threshold_days)


def is_ttl_expired(
    created_at: datetime,
    ttl_seconds: int | None,
    now: datetime | None = None,
) -> bool:
    """Check if an insight has exceeded its TTL.

    Returns False if ttl_seconds is None (no TTL set).
    """
    if ttl_seconds is None:
        return False
    now = now or datetime.now(timezone.utc)
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at) > timedelta(seconds=ttl_seconds)


@register_engine(
    name="decay_manager",
    cron="0 2 * * *",
    description="Daily confidence decay and TTL expiry",
)
async def run(product_id: str) -> dict:
    """Execute decay manager: apply confidence decay and TTL expiry to all active insights.

    Returns summary: { insights_checked, insights_decayed, insights_expired, cost }
    """
    _pool = await _get_db()

    async with _pool.connection() as db:
        return await _run_decay(db, product_id)


async def _run_decay(db, product_id: str) -> dict:
    """Inner decay logic with a live DB connection."""
    # Query all active insights for this org
    rows = await db.query(
        """
        SELECT id, tags, confidence, decay_rate, last_confirmed, created_at, ttl, status
        FROM insight
        WHERE product = <record>$product AND status = 'active'
        """,
        {"product": product_id},
    )

    from core.engine.core.db import parse_rows

    insights = parse_rows(rows)

    now = datetime.now(timezone.utc)

    decayed_count = 0
    expired_count = 0

    for insight in insights:
        insight_id = insight["id"]
        tags = insight.get("tags") or []
        confidence = float(insight.get("confidence", 1.0))
        last_confirmed = insight.get("last_confirmed")
        created_at = insight.get("created_at")
        ttl = insight.get("ttl")

        # Check TTL expiry (separate from confidence decay)
        ttl_seconds = None
        if ttl is not None:
            # SurrealDB duration — parse as seconds if numeric, or handle string
            if isinstance(ttl, (int, float)):
                ttl_seconds = int(ttl)
            elif isinstance(ttl, str) and ttl.endswith("s"):
                ttl_seconds = int(ttl[:-1])

        if created_at and is_ttl_expired(created_at, ttl_seconds, now=now):
            await db.query(
                "UPDATE <record>$id SET status = 'expired'",
                {"id": insight_id},
            )
            expired_count += 1
            continue  # Expired insights don't also need decay

        # Check confidence decay
        config = get_decay_config(tags)
        # Use insight's own decay_rate if set, otherwise use category rate
        effective_rate = insight.get("decay_rate") or config["decay_rate"]

        if last_confirmed and should_decay(last_confirmed, config["threshold_days"], now=now):
            new_confidence = apply_decay(confidence, effective_rate)
            if new_confidence != confidence:
                await db.query(
                    "UPDATE <record>$id SET confidence = $conf",
                    {"id": insight_id, "conf": new_confidence},
                )
                decayed_count += 1

                # Flag as stale if confidence drops below 0.1
                if new_confidence < 0.1:
                    logger.info(f"Insight {insight_id} confidence below 0.1 — flagging stale")

    archived_count = await _archive_unused_insights(db, product_id)

    logger.info(
        "Decay manager: checked=%d, decayed=%d, expired=%d, archived=%d",
        len(insights),
        decayed_count,
        expired_count,
        archived_count,
    )
    return {
        "insights_checked": len(insights),
        "insights_decayed": decayed_count,
        "insights_expired": expired_count,
        "insights_archived": archived_count,
        "cost": 0.0,
    }


async def _archive_unused_insights(db, product_id: str) -> int:
    """Mark loaded-but-rarely-attributed insights as 'archived'.

    Rule: loaded_count >= _ARCHIVE_LOADED_MIN AND attributed_count < _ARCHIVE_ATTRIBUTED_MAX
    Archived insights are excluded from future loads (loader SELECTs status='active').

    Returns count of insights archived. Non-fatal on any failure.
    """
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(
            await db.query(
                """SELECT insight AS insight_id, loaded_count, attributed_count
                   FROM insight_utilization
                   WHERE product = <record>$product
                     AND loaded_count >= $loaded_min
                     AND attributed_count < $attributed_max""",
                {
                    "product": product_id,
                    "loaded_min": _ARCHIVE_LOADED_MIN,
                    "attributed_max": _ARCHIVE_ATTRIBUTED_MAX,
                },
            )
        )

        archived = 0
        for row in rows:
            insight_id = str(row.get("insight_id") or "")
            if not insight_id:
                continue
            try:
                await db.query(
                    "UPDATE <record>$id SET status = 'archived', archived_at = time::now()",
                    {"id": insight_id},
                )
                archived += 1
            except Exception as exc:
                logger.warning("archive UPDATE failed for %s: %s", insight_id, exc)

        return archived
    except Exception as exc:
        logger.warning("_archive_unused_insights failed (non-fatal): %s", exc)
        return 0
