"""Custom skill emergence detection.

Scans completed tasks for repeated archetype + mode + domain_path patterns.
When 5+ tasks share the same pattern with high feedback (>= 0.7), proposes
creating a custom skill. Uses the existing skill table with org set.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIN_PATTERN_COUNT = 5
MIN_AVG_FEEDBACK = 0.7


def detect_patterns(tasks: list[dict]) -> list[dict]:
    """Find repeated archetype/mode/domain_path patterns in completed tasks.

    Returns list of pattern dicts with count and avg_feedback.
    """
    # Group by (archetype, mode, domain_path)
    pattern_tasks: dict[tuple, list[dict]] = {}
    for task in tasks:
        key = (
            task.get("archetype", ""),
            task.get("mode", ""),
            task.get("domain_path", ""),
        )
        if not all(key):
            continue
        pattern_tasks.setdefault(key, []).append(task)

    # Filter by count and feedback thresholds
    suggestions = []
    for (archetype, mode, domain_path), group in pattern_tasks.items():
        if len(group) < MIN_PATTERN_COUNT:
            continue

        # Compute average feedback score
        feedback_scores = []
        for t in group:
            fb = t.get("feedback_human")
            if fb == "accepted":
                feedback_scores.append(1.0)
            elif fb == "edited":
                feedback_scores.append(0.5)
            elif fb == "rejected":
                feedback_scores.append(0.0)

        avg_feedback = sum(feedback_scores) / len(feedback_scores) if feedback_scores else 0.0

        if avg_feedback < MIN_AVG_FEEDBACK:
            continue

        suggestions.append(
            {
                "archetype": archetype,
                "mode": mode,
                "domain_path": domain_path,
                "task_count": len(group),
                "avg_feedback": round(avg_feedback, 2),
                "sample_descriptions": [t.get("description", "")[:100] for t in group[:3]],
            }
        )

    return suggestions


async def detect_skill_emergence(product_id: str, db=None) -> list[dict]:
    """Scan completed tasks for repeated patterns and propose custom skills.

    Returns list of skill suggestion dicts.
    """
    from core.engine.core.db import pool as default_pool

    if db:
        result = await db.query(
            """
            SELECT archetype, mode, domain_path, description, feedback_human, created_at
            FROM task
            WHERE product = <record>$product AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 200
            """,
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])
    else:
        async with default_pool.connection() as conn:
            result = await conn.query(
                """
                SELECT archetype, mode, domain_path, description, feedback_human, created_at
                FROM task
                WHERE product = <record>$product AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT 200
                """,
                {"product": product_id},
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])

    if not rows or not isinstance(rows, list):
        return []

    return detect_patterns(rows)
