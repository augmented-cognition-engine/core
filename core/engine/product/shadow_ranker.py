"""Shadow-mode parallel ranker + automated rationale-quality scoring.

Per spec section "Rollback Plan" and "Measurement Plan / Shadow-mode comparison":
- Run new ranker and legacy ranker in parallel
- Log both to audit table
- Score each top-recommendation by 5-criterion rationale-quality rubric
- Aggregate over 7 days; gate flag flip on >= 70% threshold
"""

from __future__ import annotations

from typing import Any


def score_rationale_quality(rec: dict[str, Any]) -> int:
    """Score 0-5 based on 5 criteria from spec Measurement Plan.

    +1: blocking_patterns is non-empty
    +1: ambition_relevance > 0.5
    +1: rationale references phase + target (heuristic substring check)
    +1: floor and gap are populated and consistent
    +1: score is not 0.0 (no zero-score top-5)
    """
    score = 0
    if rec.get("blocking_patterns"):
        score += 1
    if (rec.get("ambition_relevance") or 0.0) > 0.5:
        score += 1
    rationale = (rec.get("rationale") or "").lower()
    has_phase = any(p in rationale for p in ["poc", "alpha", "beta", "ga", "discovery", "mature", "phase"])
    has_target = any(t in rationale for t in ["demo", "target", "days from", "block"])
    if has_phase and has_target:
        score += 1
    floor = rec.get("floor")
    gap = rec.get("gap")
    if floor is not None and gap is not None and floor >= 0.0 and gap >= 0.0:
        score += 1
    if (rec.get("score") or 0.0) > 0.0:
        score += 1
    return score
