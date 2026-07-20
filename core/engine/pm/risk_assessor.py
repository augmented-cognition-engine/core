"""Risk assessment for gate transitions — pure scoring, no DB access."""

from __future__ import annotations

HIGH_RISK_DISCIPLINES = {"security", "architecture", "data_modeling"}


def assess_risk(entity_type: str, context: dict) -> dict:
    """Score risk for a gate transition.

    Args:
        entity_type: 'idea', 'initiative', 'milestone', 'work_item'
        context: Dict with optional keys:
            - complexity: 'simple' | 'moderate' | 'complex' | 'ambitious'
            - disciplines: list[str]
            - file_count: int
            - capability_count: int (how many capabilities affected)

    Returns:
        {risk_level, auto_approve, reason, risk_factors}
    """
    factors: list[str] = []
    complexity = context.get("complexity", "simple")
    disciplines = set(context.get("disciplines", []))
    file_count = context.get("file_count", 0)
    capability_count = context.get("capability_count", 1)

    # Check high-risk signals
    risky_disciplines = disciplines & HIGH_RISK_DISCIPLINES
    if risky_disciplines:
        factors.append(f"High-risk discipline: {', '.join(sorted(risky_disciplines))}")

    if file_count > 10:
        factors.append(f"Touches {file_count} files (>10)")

    if capability_count >= 2:
        factors.append(f"Cross-capability impact: {capability_count} capabilities")

    if complexity in ("complex", "ambitious"):
        factors.append(f"Complexity: {complexity}")

    # Score
    if risky_disciplines or file_count > 10 or capability_count >= 2:
        return {
            "risk_level": "high",
            "auto_approve": False,
            "reason": "Requires human review: " + "; ".join(factors),
            "risk_factors": factors,
        }

    if file_count > 3 or len(disciplines) >= 2:
        mid_factors = []
        if file_count > 3:
            mid_factors.append(f"Touches {file_count} files")
        if len(disciplines) >= 2:
            mid_factors.append(f"{len(disciplines)} disciplines involved")
        return {
            "risk_level": "medium",
            "auto_approve": True,
            "reason": "Auto-approved (medium risk, notification sent): " + "; ".join(mid_factors),
            "risk_factors": mid_factors,
        }

    return {
        "risk_level": "low",
        "auto_approve": True,
        "reason": "Auto-approved: low risk",
        "risk_factors": [],
    }
