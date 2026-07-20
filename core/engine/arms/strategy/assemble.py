"""assemble — pure: a WorkProfile → the ordered phase categories. The 'if-then depth'."""

from __future__ import annotations

from core.engine.arms.strategy.profile import WorkProfile


def assemble(profile: WorkProfile) -> list[str]:
    """Ordered phase categories gated independently by each dimension."""
    cats: list[str] = []
    if profile.scope in ("module", "repo"):
        cats.append("ground_scan")  # understand before deciding
    if profile.novelty in ("greenfield", "extend") or profile.scope == "repo":
        cats.append("explore")  # fanout → pairwise/maxdiff → converge
    if profile.novelty == "greenfield":
        cats.append("architect")  # design the chosen direction
    if profile.risk == "systemic":
        cats.append("foresight")  # consequences / Graph Tensions
    cats.append("generate")  # always
    if profile.novelty in ("extend", "modify"):
        cats.append("integrate")
    cats.append("verify")  # always; depth = profile.verify_depth
    return cats
