"""ace_suggest_phase — infer phase from observable state.

Uses capability count and completion rate to suggest a phase. Manual
ace_set_phase remains the override.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.core.db import parse_rows


@dataclass
class SuggestedPhase:
    phase: str
    confidence: float
    signals: dict
    rationale: str


async def suggest_phase(pool, product_id: str) -> SuggestedPhase:
    async with pool.connection() as db:
        result = await db.query(
            "SELECT status FROM capability WHERE product = <record>$pid",
            {"pid": product_id},
        )
    rows = parse_rows(result)
    cap_count = len(rows)
    if cap_count > 0:
        built = sum(1 for r in rows if r.get("status") == "built")
        completion = built / cap_count
    else:
        completion = 0.0

    signals = {"capability_count": cap_count, "completion_rate": completion}

    if cap_count < 3:
        return SuggestedPhase(
            phase="discovery",
            confidence=0.7,
            signals=signals,
            rationale=f"{cap_count} capabilities — fits Discovery (idea worth pursuing).",
        )
    if completion < 0.6:
        return SuggestedPhase(
            phase="poc",
            confidence=0.7,
            signals=signals,
            rationale=(
                f"{cap_count} capabilities; {completion * 100:.0f}% complete — fits POC (proving the idea works)."
            ),
        )
    if completion < 0.8:
        return SuggestedPhase(
            phase="alpha",
            confidence=0.65,
            signals=signals,
            rationale=(
                f"{cap_count} capabilities; {completion * 100:.0f}% complete — "
                f"fits Alpha (early users won't have a terrible time)."
            ),
        )
    if completion < 0.95:
        return SuggestedPhase(
            phase="beta",
            confidence=0.6,
            signals=signals,
            rationale=(
                f"{cap_count} capabilities; {completion * 100:.0f}% complete — "
                f"fits Beta (paying users; reliability load-bearing)."
            ),
        )
    return SuggestedPhase(
        phase="ga",
        confidence=0.55,
        signals=signals,
        rationale=(
            f"{cap_count} capabilities; {completion * 100:.0f}% complete — fits GA (production-grade everywhere)."
        ),
    )
