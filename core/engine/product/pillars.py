"""7-pillar systems-architecture taxonomy + legacy-dim mapping.

Per docs/discipline-taxonomy.md v1.6.
"""

from __future__ import annotations

from enum import Enum


class Pillar(str, Enum):
    EXPERIENCE = "experience"
    INTERFACE = "interface"
    LOGIC = "logic"
    STATE = "state"
    OPERATIONS = "operations"
    EVOLUTION = "evolution"
    TRUST = "trust"


PILLARS: list[Pillar] = [
    Pillar.EXPERIENCE,
    Pillar.INTERFACE,
    Pillar.LOGIC,
    Pillar.STATE,
    Pillar.OPERATIONS,
    Pillar.EVOLUTION,
    Pillar.TRUST,
]

# Legacy QUALITY_DIMENSIONS → primary pillar.
# (Some dims have a secondary pillar — not modeled here for v1; aggregation
# uses primary only. Splits are documented in the taxonomy doc.)
LEGACY_DIM_TO_PILLAR: dict[str, Pillar] = {
    "ux": Pillar.EXPERIENCE,
    "accessibility": Pillar.EXPERIENCE,
    "api_design": Pillar.INTERFACE,
    "integration": Pillar.INTERFACE,
    "data_modeling": Pillar.STATE,
    "business_logic": Pillar.LOGIC,
    "error_handling": Pillar.LOGIC,
    "data": Pillar.STATE,
    "versioning": Pillar.STATE,
    "observability": Pillar.OPERATIONS,
    "deployment": Pillar.OPERATIONS,
    "devops": Pillar.OPERATIONS,
    "performance": Pillar.OPERATIONS,
    "configuration": Pillar.OPERATIONS,
    "testing": Pillar.EVOLUTION,
    "documentation": Pillar.EVOLUTION,
    "code_conventions": Pillar.EVOLUTION,
    "dependency_management": Pillar.EVOLUTION,
    "architecture": Pillar.EVOLUTION,
    "security": Pillar.TRUST,
    # Classifier disciplines added to close audit gap (decision:st6v2yrtd3qrpd4lh9kb).
    "ai_ml": Pillar.TRUST,  # model safety, alignment, output quality — trust concerns
    "product_strategy": Pillar.EVOLUTION,  # how the product evolves over time
    "scale": Pillar.OPERATIONS,  # capacity, backpressure, load — production reliability
    # Partnership-spec disciplines (taxonomy v1.6, spec v1.1).
    "aix": Pillar.EXPERIENCE,
    "content_design": Pillar.EXPERIENCE,
    "engineering_culture": Pillar.EVOLUTION,
}


def aggregate_to_pillars(dim_scores: dict[str, float]) -> dict[Pillar, float]:
    """Roll up flat dimension scores to 7 pillar scores.

    Pillars with no contributing dimensions in `dim_scores` get 0.0.
    Aggregation is unweighted mean of contributing dims.
    """
    by_pillar: dict[Pillar, list[float]] = {p: [] for p in PILLARS}
    for dim, score in dim_scores.items():
        pillar = LEGACY_DIM_TO_PILLAR.get(dim)
        if pillar is not None:
            by_pillar[pillar].append(float(score))
    return {pillar: (sum(scores) / len(scores) if scores else 0.0) for pillar, scores in by_pillar.items()}
