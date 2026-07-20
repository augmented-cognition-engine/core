"""Automated linguistic audit on BriefingPayload — partnership-feel proxy.

Per spec Measurement Plan: pass-rate target >= 95% of briefings.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.product.briefing_payload import BriefingPayload
from core.engine.product.shadow_ranker import score_rationale_quality


@dataclass
class AuditResult:
    total: int
    passing: int
    pass_rate: float
    failures: list[dict]


def audit_briefing_payload(payload: BriefingPayload) -> AuditResult:
    """Audit each top recommendation's rationale; return aggregate pass-rate."""
    total = len(payload.top_recommendations)
    if total == 0:
        return AuditResult(total=0, passing=0, pass_rate=0.0, failures=[])

    passing = 0
    failures = []
    for rec in payload.top_recommendations:
        rec_dict = {
            "blocking_patterns": rec.blocking_patterns,
            "ambition_relevance": rec.ambition_relevance,
            "rationale": rec.rationale,
            "floor": rec.floor,
            "gap": rec.gap,
            "score": rec.score,
        }
        score = score_rationale_quality(rec_dict)
        if score >= 4:
            passing += 1
        else:
            failures.append({"rec": rec_dict, "score": score})

    return AuditResult(
        total=total,
        passing=passing,
        pass_rate=passing / total,
        failures=failures,
    )
