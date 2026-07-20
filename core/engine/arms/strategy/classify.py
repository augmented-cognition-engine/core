"""classify_work — produce a WorkProfile. Graph-grounds scope/risk, reasons novelty/type
from the objective + conversation, and lets user overrides win. The profile is a
recommendation, never a lock. Injectable classifier → deterministic tests."""

from __future__ import annotations

import logging

from core.engine.arms.strategy.profile import WorkProfile

logger = logging.getLogger(__name__)

# Safe middle when no classifier is available (unit tests / degraded). Never LLM-calls.
STATIC_DEFAULT_PROFILE = WorkProfile()


async def classify_work(
    solution, *, conversation=None, overrides=None, classifier=None, scorer=None, arm_domain=None
) -> WorkProfile:
    """Return the work's depth profile. classifier -> profile; scorer -> deepen-only learned nudge
    (applied BEFORE overrides so the user always wins); overrides force any dimension."""
    if classifier is None:
        # static-middle default is never nudged (the safe degraded path)
        return _apply_overrides(WorkProfile(**vars(STATIC_DEFAULT_PROFILE)), overrides)
    try:
        profile = await classifier(solution, conversation, overrides)
        profile = await _apply_learning(profile, scorer, arm_domain, solution)
        return _apply_overrides(profile, overrides)
    except Exception as exc:
        logger.warning("classify_work failed (non-fatal); using default: %s", exc)
        return _apply_overrides(WorkProfile(**vars(STATIC_DEFAULT_PROFILE)), overrides)


async def _apply_learning(profile, scorer, arm_domain, solution):
    """Deepen-only learned nudge. Non-fatal; the static default + overrides paths never reach here."""
    if scorer is None:
        return profile
    try:
        product_id = getattr(solution, "product_id", None) or "product:platform"
        signal = await scorer(profile, arm_domain, product_id)
        if getattr(signal, "escalate", False):
            from core.engine.arms.strategy.depth_scorer import escalate_profile

            return escalate_profile(profile)
        return profile
    except Exception as exc:
        logger.warning("classify_work depth-learning nudge failed (non-fatal): %s", exc)
        return profile


def _apply_overrides(profile: WorkProfile, overrides) -> WorkProfile:
    """User overrides always win — the depth is never locked."""
    if not overrides:
        return profile
    for dim in ("scope", "novelty", "risk", "verify_depth", "task_type"):
        if overrides.get(dim):
            setattr(profile, dim, overrides[dim])
    return profile
