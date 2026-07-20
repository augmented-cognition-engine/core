"""Compounding metric — measures whether recurring task classes get faster over time.

ACE's pitch is "day-1 speed on day-300" — intelligence compounds so similar tasks
shouldn't take the same time, every time. This module buckets tasks by a content-
derived class_hash and records their completion duration + token cost. A nightly
roll-up (or live query) can then show per-class p50/p95 trajectories.

Intentionally cheap on the write path: one DB INSERT, no LLM, no embedding call.
Upgrades to embedding-based clustering are additive.
"""

from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

_NORMALIZE_RE = re.compile(r"\s+")


def task_class_hash(description: str) -> str:
    """Deterministic 16-char hash that buckets similar-looking task descriptions.

    Normalization: lowercase + collapse whitespace. Two descriptions only
    differing in case or spacing share a bucket. For true fuzzy clustering,
    upgrade this to an embedding-similarity lookup against existing classes.
    """
    normalized = _NORMALIZE_RE.sub(" ", (description or "").strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


async def record_task_duration(
    db,
    product_id: str,
    description: str,
    discipline: str,
    duration_ms: int,
    token_total: int,
) -> None:
    """Persist a single task's duration + token cost keyed by its class_hash.

    Non-fatal — any failure is logged but not raised. The metric is observational;
    losing a single sample must never break task flow.
    """
    try:
        class_hash = task_class_hash(description)
        sample = (description or "")[:120]
        await db.query(
            """CREATE task_class_duration SET
               product = <record>$product,
               discipline = $discipline,
               class_hash = $class_hash,
               description_sample = $description_sample,
               duration_ms = $duration_ms,
               token_total = $token_total,
               completed_at = time::now()""",
            {
                "product": product_id,
                "discipline": discipline,
                "class_hash": class_hash,
                "description_sample": sample,
                "duration_ms": duration_ms,
                "token_total": token_total,
            },
        )
    except Exception as exc:
        logger.warning("record_task_duration failed (non-fatal): %s", exc)


async def get_class_trajectory(db, product_id: str, class_hash: str, limit: int = 50) -> list[dict]:
    """Return the chronological history for one task class.

    Ordered oldest → newest so callers can trivially compute deltas / trends.
    """
    try:
        from core.engine.core.db import parse_rows

        result = await db.query(
            """SELECT duration_ms, token_total, completed_at
               FROM task_class_duration
               WHERE product = <record>$product AND class_hash = $class_hash
               ORDER BY completed_at ASC
               LIMIT $limit""",
            {"product": product_id, "class_hash": class_hash, "limit": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.warning("get_class_trajectory failed (non-fatal): %s", exc)
        return []
