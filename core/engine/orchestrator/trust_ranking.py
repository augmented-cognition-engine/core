# core/engine/orchestrator/trust_ranking.py
"""Trust as a believability multiplier in retrieval ranking — pure, no I/O.

The provenance system (capture/provenance.py) scores every insight's `trust` from its source kind.
This is where that score becomes load-bearing: retrieval rank is scaled by trust, so a confidently
phrased self-generated conclusion (trust 0.50) cannot out-rank a well-trusted human capture. The
multiplier is NEUTRAL (1.0) for un-reconciled insights (trust IS NONE) — trust only ever DISCOUNTS
content explicitly scored low; it never penalizes missing data. This is what damps the active loop's
reasoning -> graph -> reasoning feedback into a stable loop instead of an echo chamber.
"""

from __future__ import annotations


def trust_multiplier(trust: float | None) -> float:
    """Believability multiplier in [0, 1]. None -> 1.0 (neutral). Non-numeric -> 1.0 (never crash
    retrieval). A real 0.0 is honored (floored), distinct from None."""
    if trust is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(trust)))
    except (TypeError, ValueError):
        return 1.0


def trust_weighted(score: float, trust: float | None) -> float:
    """Scale a relevance score (confidence, or a confidence/utilization blend) by trust."""
    try:
        base = float(score)
    except (TypeError, ValueError):
        base = 0.0
    return base * trust_multiplier(trust)
