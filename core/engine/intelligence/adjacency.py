# engine/intelligence/adjacency.py
"""Discipline adjacency graph — used for confidence-based fallback routing.

When the classifier's discipline_confidence is below a threshold, the loader
queries adjacent disciplines to fill gaps in the intelligence snapshot.

Adjacency is determined by semantic proximity:
  - Same tier (Quality / Product / Operational / Team / Data / Infrastructure)
  - Cross-tier semantic overlap (e.g. error_handling ↔ security, testing ↔ observability)

Usage:
    from core.engine.intelligence.adjacency import get_adjacent_disciplines
    adjacent = get_adjacent_disciplines("security", max_n=2)
    # → ["error_handling", "testing"]
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Static adjacency map
# Each discipline maps to an ordered list of neighbours (closest first).
# Bidirectional — A→B implies B→A (enforced at build time via _mirror()).
# ---------------------------------------------------------------------------

_ADJACENCY_RAW: dict[str, list[str]] = {
    # Quality tier — correctness, reliability, user-facing quality
    "security": ["error_handling", "testing", "observability", "dependency_management"],
    "testing": ["error_handling", "observability", "code_conventions", "security"],
    "performance": ["observability", "concurrency", "caching", "database_performance"],
    "ux": ["accessibility", "documentation", "mobile"],
    "devops": ["infrastructure", "configuration", "observability"],
    "accessibility": ["ux", "mobile", "documentation"],
    "documentation": ["code_conventions", "ux", "api_design"],
    # Product tier — structure, contracts, domain
    "architecture": ["api_design", "data_modeling", "integration", "business_logic"],
    "api_design": ["architecture", "integration", "versioning", "error_handling"],
    "data_modeling": ["architecture", "storage", "data_pipelines", "business_logic"],
    "business_logic": ["architecture", "data_modeling", "error_handling"],
    "integration": ["api_design", "architecture", "messaging", "versioning"],
    # Operational tier — runtime, config, lifecycle
    "error_handling": ["testing", "observability", "resilience", "security"],
    "observability": ["error_handling", "performance", "devops"],
    "configuration": ["devops", "dependency_management", "infrastructure"],
    "versioning": ["api_design", "dependency_management", "integration"],
    # Concurrency / resilience cluster
    "concurrency": ["performance", "resilience", "architecture"],
    "resilience": ["error_handling", "concurrency", "devops", "networking"],
    # Data / pipeline cluster
    "data_pipelines": ["data_modeling", "storage", "messaging", "search"],
    "storage": ["data_modeling", "data_pipelines", "state_management"],
    "messaging": ["data_pipelines", "real_time", "integration"],
    "state_management": ["architecture", "data_modeling", "real_time"],
    # Networking / real-time
    "networking": ["resilience", "real_time", "infrastructure"],
    "real_time": ["messaging", "networking", "state_management"],
    # Infra
    "infrastructure": ["devops", "networking", "configuration"],
    # Team / conventions
    "code_conventions": ["testing", "documentation", "type_system"],
    "dependency_management": ["configuration", "security", "versioning"],
    "type_system": ["code_conventions", "api_design"],
    # Specialist
    "mobile": ["ux", "accessibility", "networking"],
    "search": ["data_modeling", "data_pipelines", "performance"],
    "ai_ml_integration": ["architecture", "data_pipelines", "api_design", "observability"],
}

# ---------------------------------------------------------------------------
# Mirror: ensure bidirectionality
# ---------------------------------------------------------------------------


def _mirror(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {k: list(v) for k, v in raw.items()}
    for source, targets in raw.items():
        for target in targets:
            if target in graph and source not in graph[target]:
                graph[target].append(source)
    return graph


_ADJACENCY: dict[str, list[str]] = _mirror(_ADJACENCY_RAW)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_adjacent_disciplines(discipline: str, max_n: int = 2) -> list[str]:
    """Return the top-N adjacent disciplines for a given discipline.

    Returns an empty list if the discipline is unknown or has no adjacency.
    The list is ordered from closest to furthest.

    Args:
        discipline: The primary discipline slug.
        max_n:      Maximum number of neighbours to return (default 2).
    """
    neighbours = _ADJACENCY.get(discipline, [])
    return neighbours[:max_n]


def adjacency_overlap(d1: str, d2: str) -> bool:
    """True if d2 is adjacent to d1 (one-hop)."""
    return d2 in _ADJACENCY.get(d1, [])
