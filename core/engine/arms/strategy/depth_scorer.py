# core/engine/arms/strategy/depth_scorer.py
"""Depth learning — the feedback loop on the depth dimension, mirroring composition_scorer for
lenses. Reads action_outcome over a lookback window, finds profile-classes that keep failing
verify (coarse key: arm_domain x novelty x risk), and signals a deepen-only escalation.

SAFETY (autonomous loop, bounded): escalate-ONLY (the unsafe shallow direction is unreachable),
gated on min_signals (never acts on noise), one notch per build, capped at full depth, non-fatal.
Applied by classify_work BEFORE user overrides, so the human always wins."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.engine.arms.strategy.profile import WorkProfile
from core.engine.core.db import pool as default_pool

logger = logging.getLogger(__name__)

MIN_SIGNALS = 8  # don't adapt under this many builds for a key (no acting on noise)
FAIL_THRESHOLD = 0.5  # escalate when >= this fraction of a key's builds failed verify
LOOKBACK_DAYS = 30  # window of recent outcomes considered
_LOOKBACK_LIMIT = 200  # cap rows scanned per key

# Deepen-ladder: scope first (keeps the coarse key stable while it can — scope isn't in the key),
# then risk (adds foresight), then verify_depth. One notch per call; the unsafe direction is absent.
_LADDER = (
    ("scope", ("none", "nearby", "module", "repo")),
    ("risk", ("isolated", "connected", "systemic")),
    ("verify_depth", ("smoke", "unit", "full")),
)


@dataclass
class DepthSignal:
    escalate: bool = False
    reason: str = ""


def escalate_profile(profile: WorkProfile) -> WorkProfile:
    """Deepen ONE notch along the ladder (first dim not at its max). New object; never shallows;
    if every laddered dim is maxed, returns an unchanged copy (bounded)."""
    p = WorkProfile(**vars(profile))
    for dim, ladder in _LADDER:
        cur = getattr(p, dim)
        if cur in ladder and ladder.index(cur) < len(ladder) - 1:
            setattr(p, dim, ladder[ladder.index(cur) + 1])
            return p
    return p


async def score_depth(
    profile: WorkProfile,
    arm_domain: str,
    product_id: str = "product:platform",
    *,
    min_signals: int = MIN_SIGNALS,
    pool=None,
) -> DepthSignal:
    """Coarse-key (arm_domain x novelty x risk) verify-fail-rate over the lookback window.
    escalate=True when fail_rate >= FAIL_THRESHOLD over >= min_signals builds. Non-fatal -> neutral."""
    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            rows = await db.query(
                # parked != true excludes runs the ENVIRONMENT killed (model unreachable, DB down).
                # A parked row carries passed=false, so without this an afternoon of LLM timeouts
                # would read as "this profile class keeps failing" and silently deepen the reasoning.
                # It is evidence of nothing, and it must not enter the numerator OR the denominator.
                # (Pre-parked rows have no such field — `parked != true` matches NONE, so history
                # still counts.)
                f"SELECT passed FROM action_outcome "
                f"WHERE product = <record>$product AND arm_domain = <string>$domain "
                f"AND profile_novelty = <string>$novelty AND profile_risk = <string>$risk "
                f"AND parked != true "
                f"AND created_at > time::now() - {LOOKBACK_DAYS}d LIMIT {_LOOKBACK_LIMIT}",
                {"product": product_id, "domain": arm_domain or "", "novelty": profile.novelty, "risk": profile.risk},
            )
        from core.engine.core.db import parse_rows

        rows = parse_rows(rows)
        # Belt AND braces: the WHERE already excludes parked, but the tally excludes it too. This
        # loop is the thing that actually decides whether to deepen, and a parked row leaking in
        # (schema drift, a hand-written row, a future query change) would silently teach the engine
        # that a broken environment means hard work. Defend it where the decision is made.
        rows = [r for r in rows if r.get("parked") is not True]
        total = len(rows)
        if total < min_signals:
            return DepthSignal()
        failed = sum(1 for r in rows if r.get("passed") is False)
        fail_rate = failed / total
        if fail_rate >= FAIL_THRESHOLD:
            return DepthSignal(
                escalate=True,
                reason=f"{arm_domain}/{profile.novelty}/{profile.risk}: {failed}/{total} failed -> deepen",
            )
        return DepthSignal()
    except Exception as exc:
        logger.warning("score_depth failed (non-fatal): %s", exc)
        return DepthSignal()
