"""Historical confidence — enrich task classification with evidence from past work."""

from __future__ import annotations

import logging
from collections import Counter

import core.engine.core.db as _db
from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


async def enrich_classification(classification: dict, product_id: str) -> dict:
    """Add historical context to a classification.

    Queries recent tasks with same domain_path and archetype, computes
    aggregate statistics, and adds a historical_context dict to the classification.
    """
    domain = classification.get("domain_path", "")
    archetype = classification.get("archetype", "")

    if not domain or not archetype:
        classification["historical_context"] = _empty_context()
        return classification

    async with _db.pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """
                SELECT perspective, feedback_human, self_assessment,
                       intelligence_utilization.utilization_rate AS util_rate, created_at
                FROM task
                WHERE product = <record>$product
                  AND domain_path = <string>$domain
                  AND archetype = <string>$archetype
                  AND self_assessment IS NOT NONE
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"product": product_id, "domain": domain, "archetype": archetype},
            )
        )

    if not rows:
        classification["historical_context"] = _empty_context()
        return classification

    assessments = [r["self_assessment"] for r in rows if r.get("self_assessment") is not None]
    perspectives = [r["perspective"] for r in rows if r.get("perspective")]
    util_rates = [r["util_rate"] for r in rows if r.get("util_rate") is not None]

    avg_feedback = sum(assessments) / len(assessments) if assessments else 0.0
    avg_util = sum(util_rates) / len(util_rates) if util_rates else 0.0

    classification["historical_context"] = {
        "similar_task_count": len(rows),
        "avg_feedback": round(avg_feedback, 2),
        "common_perspectives": Counter(perspectives).most_common(2),
        "avg_utilization": round(avg_util, 2),
        "confidence_note": _generate_note(len(rows), avg_feedback),
    }
    return classification


def _empty_context() -> dict:
    return {
        "similar_task_count": 0,
        "avg_feedback": 0.0,
        "common_perspectives": [],
        "avg_utilization": 0.0,
        "confidence_note": "First task in this domain — no historical data yet.",
    }


def _generate_note(count: int, avg: float) -> str:
    if count == 0:
        return "First task in this domain — no historical data yet."
    if count < 3:
        return f"Limited history ({count} similar tasks)."
    if avg >= 0.8:
        return f"Strong track record — {count} similar tasks averaged {avg:.0%} confidence."
    if avg >= 0.6:
        return f"Moderate track record — {count} similar tasks, room for improvement."
    return f"Challenging domain — similar tasks have had mixed results ({avg:.0%} avg)."
