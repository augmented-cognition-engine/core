# engine/foresight/signal_engine.py
"""Internal signal engine — computes foresight signals from ACE's existing state.

No external APIs. No LLM calls. Pure analytics over existing DB tables.
Domain-agnostic: capabilities can represent anything (features, research outputs,
legal matters, operational functions — whatever ACE is tracking for this context).

Three signal kinds:
  capability_decline      — capability quality score dropped >= 0.1 over 7 days
  gap_persistence         — capability score < 0.4 open >= 14 days with no decision
  decision_velocity_drop  — decision cadence down > 50% week-over-week

Registered as sentinel engine "signal_engine" (daily at 07:00).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from core.engine.core.db import parse_rows, pool
from core.engine.foresight.models import Signal
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_DECLINE_THRESHOLD = 0.10
_GAP_SCORE_CUTOFF = 0.40
_GAP_AGE_DAYS = 14
_VELOCITY_DROP_RATIO = 0.50


async def compute_capability_decline_signals(product_id: str) -> list[Signal]:
    """Detect capabilities whose mean score dropped >= 0.1 over the last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT capability, score, assessed_at
                   FROM capability_quality
                   WHERE product = <record>$product AND assessed_at > $since
                   ORDER BY capability ASC, assessed_at ASC""",
                {"product": product_id, "since": since},
            )
        rows = parse_rows(result)
    except Exception:
        return []

    buckets: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        cap = str(row.get("capability", ""))
        score = float(row.get("score", 0.5))
        ts = str(row.get("assessed_at", ""))
        if cap:
            buckets[cap].append((ts, score))

    signals: list[Signal] = []
    for cap, entries in buckets.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: x[0])
        oldest_score = entries[0][1]
        newest_score = entries[-1][1]
        delta = oldest_score - newest_score  # positive = decline
        if delta < _DECLINE_THRESHOLD:
            continue

        confidence = min(1.0, delta / 0.5 * 0.7 + min(len(entries) / 5, 0.3))
        slug = cap.split(":")[-1] if ":" in cap else cap
        signals.append(
            Signal(
                id=str(uuid.uuid4()),
                kind="capability_decline",
                product_id=product_id,
                subject=cap,
                description=f"{slug} score declined {delta:.2f} over 7 days (now {newest_score:.2f})",
                confidence=round(confidence, 2),
                trend_data={
                    "scores": [e[1] for e in entries],
                    "days": 7,
                    "delta": round(delta, 3),
                },
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    return signals


async def compute_gap_persistence_signals(product_id: str) -> list[Signal]:
    """Detect gaps open >= 14 days with no decision addressing them."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_GAP_AGE_DAYS)
    try:
        async with pool.connection() as db:
            result = await db.query(
                f"""SELECT capability, score, assessed_at
                   FROM capability_quality
                   WHERE product = <record>$product
                   AND score < {_GAP_SCORE_CUTOFF}
                   AND assessed_at < $cutoff_date
                   ORDER BY score ASC LIMIT 10""",
                {"product": product_id, "cutoff_date": cutoff},
            )
        gap_rows = parse_rows(result)
    except Exception:
        return []

    signals: list[Signal] = []
    for row in gap_rows:
        cap = str(row.get("capability", ""))
        score = float(row.get("score", 0.3))
        slug = cap.split(":")[-1] if ":" in cap else cap

        try:
            async with pool.connection() as db:
                dec_result = await db.query(
                    """SELECT id FROM decision
                       WHERE product = <record>$product
                       AND created_at > $since
                       AND (content CONTAINS $slug OR title CONTAINS $slug)
                       LIMIT 1""",
                    {"product": product_id, "since": cutoff, "slug": slug},
                )
            has_decision = bool(parse_rows(dec_result))
        except Exception:
            has_decision = False

        if has_decision:
            continue

        confidence = min(1.0, (0.4 - score) / 0.4 * 0.8 + 0.2)
        signals.append(
            Signal(
                id=str(uuid.uuid4()),
                kind="gap_persistence",
                product_id=product_id,
                subject=cap,
                description=f"{slug} has been gapped (score {score:.2f}) for >{_GAP_AGE_DAYS} days with no decision",
                confidence=round(confidence, 2),
                trend_data={"score": score, "age_days": _GAP_AGE_DAYS},
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    return signals


async def compute_decision_velocity_signals(product_id: str) -> list[Signal]:
    """Detect when decision cadence drops > 50% week-over-week."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    try:
        async with pool.connection() as db:
            this_week_result = await db.query(
                "SELECT count() AS n FROM decision WHERE product = <record>$product AND created_at > $since GROUP ALL",
                {"product": product_id, "since": week_ago},
            )
            last_week_result = await db.query(
                """SELECT count() AS n FROM decision
                   WHERE product = <record>$product
                   AND created_at > $start AND created_at <= $end
                   GROUP ALL""",
                {"product": product_id, "start": two_weeks_ago, "end": week_ago},
            )
        this_week_rows = parse_rows(this_week_result)
        last_week_rows = parse_rows(last_week_result)
    except Exception:
        return []

    this_week = int((this_week_rows[0].get("n", 0)) if this_week_rows else 0)
    last_week = int((last_week_rows[0].get("n", 0)) if last_week_rows else 0)

    if last_week == 0 or this_week >= last_week:
        return []

    drop_ratio = 1.0 - (this_week / last_week)
    if drop_ratio <= _VELOCITY_DROP_RATIO:
        return []

    confidence = min(1.0, drop_ratio)
    return [
        Signal(
            id=str(uuid.uuid4()),
            kind="decision_velocity_drop",
            product_id=product_id,
            subject="decisions",
            description=f"Decision cadence dropped {drop_ratio:.0%}: {this_week} this week vs {last_week} last week",
            confidence=round(confidence, 2),
            trend_data={"this_week": this_week, "last_week": last_week, "drop_ratio": round(drop_ratio, 2)},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    ]


async def _write_signal(sig: Signal) -> None:
    async with pool.connection() as db:
        await db.query(
            """CREATE type::record('signal', $id) SET
                product         = <record>$product,
                kind            = $kind,
                subject         = $subject,
                description     = $description,
                confidence      = $confidence,
                trend_data      = $trend_data,
                scenario_built  = false,
                created_at      = time::now()
            """,
            {
                "id": sig.id,
                "product": sig.product_id,
                "kind": sig.kind,
                "subject": sig.subject,
                "description": sig.description,
                "confidence": sig.confidence,
                "trend_data": sig.trend_data,
            },
        )


@register_engine(
    name="signal_engine",
    cron="0 7 * * *",  # daily at 07:00
    description="Compute internal foresight signals: capability decline, gap persistence, decision velocity.",
)
async def run_signal_engine(product_id: str) -> dict:
    """Compute all internal signal types and write new ones to the signal table."""
    all_signals: list[Signal] = []
    all_signals.extend(await compute_capability_decline_signals(product_id))
    all_signals.extend(await compute_gap_persistence_signals(product_id))
    all_signals.extend(await compute_decision_velocity_signals(product_id))

    written = 0
    for sig in all_signals:
        try:
            await _write_signal(sig)
            written += 1
        except Exception as exc:
            logger.warning("signal_engine: failed to write signal %s: %s", sig.id, exc)

    logger.info("signal_engine: %d signals written for %s", written, product_id)
    return {"signals_written": written}
