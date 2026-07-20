"""ambition_relevance term — maps target's required_patterns to pillar/discipline.

Reads from required_pattern_relevance table.
"""

from __future__ import annotations

from typing import Optional

from core.engine.core.db import parse_rows

_DEFAULT_RELEVANCE = 0.5


async def compute_ambition_relevance(
    pool,
    pillar: str,
    discipline: Optional[str],
    required_patterns: list[str],
) -> float:
    """Sum contribution from each required_pattern that maps to (pillar, discipline).

    Returns a value in [0, 1]. If no pattern matches the target slot, returns the
    default 0.5 (deprioritized but non-zero — doesn't fully kill the dimension).
    """
    if not required_patterns:
        return _DEFAULT_RELEVANCE

    async with pool.connection() as db:
        result = await db.query(
            """SELECT pillar, discipline, contribution
               FROM required_pattern_relevance
               WHERE pattern IN $patterns""",
            {"patterns": required_patterns},
        )
    rows = parse_rows(result)

    total = 0.0
    matched = False
    for r in rows:
        if r.get("pillar") != pillar:
            continue
        row_discipline = r.get("discipline")
        if discipline is None or row_discipline == discipline or row_discipline is None:
            total += float(r.get("contribution", 0.0))
            matched = True

    if not matched:
        return _DEFAULT_RELEVANCE
    normalized = total / max(1, len(required_patterns))
    return max(0.0, min(1.0, normalized))
