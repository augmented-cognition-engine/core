"""Effectiveness aggregator — compute per-(pillar, discipline) effectiveness scores.

Reads outcome_observation over a 30-day rolling window, groups by (pillar, discipline),
computes smoothed scores using Laplace smoothing (neutral prior), writes to
effectiveness_score table (append-only ledger).

v1.0: SHADOW MODE — scores are computed and written but NOT consumed by the ranker.
v1.1: StrategicPrioritizer will read effectiveness_score to bias ranking.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.engine.core.db import parse_rows, pool


@dataclass
class EffectivenessScore:
    product_id: str
    pillar: str
    discipline: str
    n_emissions: int
    n_acted_on: int
    n_ignored: int
    n_rejected: int
    raw_rate: float
    smoothed_rate: float
    confidence: float
    computed_at: datetime


async def compute_effectiveness_scores(product_id: str) -> list[EffectivenessScore]:
    """Read outcome_observations from last 30 days, group by (pillar, discipline),
    compute Laplace-smoothed effectiveness scores.

    Only closed observations (not 'open') are counted. 'answered' is treated the
    same as 'acted_on' (positive outcome). 'ignored' and 'rejected' are negative.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT pillar, discipline, outcome_label
                   FROM outcome_observation
                   WHERE product = <record>$pid
                     AND outcome_at > <datetime>$cutoff
                     AND outcome_label != 'open'""",
                {"pid": product_id, "cutoff": cutoff.isoformat()},
            )
        )

    by_key: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"acted_on": 0, "ignored": 0, "rejected": 0, "answered": 0}
    )
    for r in rows:
        pillar = r.get("pillar") or ""
        discipline = r.get("discipline") or ""
        if not pillar:
            continue  # skip emissions without pillar
        label = r.get("outcome_label", "ignored")
        bucket = by_key[(pillar, discipline)]
        if label in bucket:
            bucket[label] += 1

    scores = []
    now = datetime.now(timezone.utc)
    for (pillar, discipline), counts in by_key.items():
        # 'answered' counts as acted_on for uncertainty
        total = counts["acted_on"] + counts["answered"] + counts["ignored"] + counts["rejected"]
        if total == 0:
            continue
        positive = counts["acted_on"] + counts["answered"]
        raw = positive / total
        # Laplace smoothing with neutral prior (k=1, denominator +3)
        # Centers at ~0.33 for no data; rises to true rate with sample size
        smoothed = (positive + 1) / (total + 3)
        # Confidence rises linearly with sample size; saturates at 20 observations
        confidence = min(1.0, total / 20.0)
        scores.append(
            EffectivenessScore(
                product_id=product_id,
                pillar=pillar,
                discipline=discipline,
                n_emissions=total,
                n_acted_on=counts["acted_on"],
                n_ignored=counts["ignored"],
                n_rejected=counts["rejected"],
                raw_rate=raw,
                smoothed_rate=smoothed,
                confidence=confidence,
                computed_at=now,
            )
        )
    return scores


async def persist_scores(scores: list[EffectivenessScore]) -> None:
    """Append-only writes to effectiveness_score.

    Old rows stay; consumers read MAX(computed_at) per (pillar, discipline) to
    get the latest score. No rows are ever deleted by this function.
    """
    import sys

    from core.engine.events.bus import bus

    async with pool.connection() as db:
        for s in scores:
            await db.query(
                """CREATE effectiveness_score CONTENT {
                    product: <record>$pid,
                    pillar: <string>$pillar,
                    discipline: <string>$discipline,
                    n_emissions: <int>$n,
                    n_acted_on: <int>$na,
                    n_ignored: <int>$ni,
                    n_rejected: <int>$nr,
                    raw_rate: <float>$raw,
                    smoothed_rate: <float>$smooth,
                    confidence: <float>$conf,
                    computed_at: time::now()
                }""",
                {
                    "pid": s.product_id,
                    "pillar": s.pillar,
                    "discipline": s.discipline,
                    "n": s.n_emissions,
                    "na": s.n_acted_on,
                    "ni": s.n_ignored,
                    "nr": s.n_rejected,
                    "raw": s.raw_rate,
                    "smooth": s.smoothed_rate,
                    "conf": s.confidence,
                },
            )
            try:
                await bus.emit(
                    "effectiveness.score.recomputed",
                    {
                        "product_id": str(s.product_id),
                        "pillar": s.pillar,
                        "discipline": s.discipline,
                        "score": round(s.smoothed_rate, 3),
                    },
                )
            except Exception as exc:
                print(f"warn: effectiveness topic emit failed: {exc!r}", file=sys.stderr)
