# tests/test_adjacency.py
"""Tests for the discipline adjacency graph used in confidence-based routing."""

from core.engine.intelligence.adjacency import adjacency_overlap, get_adjacent_disciplines


def test_known_discipline_returns_adjacent():
    """Known disciplines return a non-empty list of neighbours."""
    adjacent = get_adjacent_disciplines("security")
    assert len(adjacent) >= 1
    assert all(isinstance(d, str) for d in adjacent)


def test_max_n_respected():
    """max_n limits the number of returned neighbours."""
    assert len(get_adjacent_disciplines("architecture", max_n=1)) == 1
    assert len(get_adjacent_disciplines("architecture", max_n=3)) == 3


def test_unknown_discipline_returns_empty():
    """Unknown disciplines return an empty list — no KeyError."""
    assert get_adjacent_disciplines("nonexistent_discipline") == []


def test_adjacency_is_bidirectional():
    """If A is adjacent to B, B must be adjacent to A."""
    for d, neighbours in {
        "security": ["error_handling", "testing"],
        "architecture": ["api_design", "data_modeling"],
        "ai_ml_integration": ["architecture", "data_pipelines"],
    }.items():
        for neighbour in neighbours:
            back = get_adjacent_disciplines(neighbour, max_n=10)
            assert d in back, f"{d} → {neighbour} exists but {neighbour} → {d} is missing"


def test_adjacency_overlap_true():
    """adjacency_overlap returns True for direct neighbours."""
    assert adjacency_overlap("security", "error_handling")
    assert adjacency_overlap("architecture", "api_design")
    assert adjacency_overlap("devops", "observability")


def test_adjacency_overlap_false():
    """adjacency_overlap returns False for unrelated disciplines."""
    assert not adjacency_overlap("mobile", "architecture")
    assert not adjacency_overlap("documentation", "concurrency")


def test_all_31_disciplines_present():
    """All 31 taxonomy disciplines have adjacency entries."""
    from core.engine.intelligence.adjacency import _ADJACENCY

    expected = {
        "security",
        "testing",
        "performance",
        "ux",
        "devops",
        "accessibility",
        "documentation",
        "architecture",
        "api_design",
        "data_modeling",
        "business_logic",
        "integration",
        "error_handling",
        "observability",
        "configuration",
        "versioning",
        "concurrency",
        "resilience",
        "data_pipelines",
        "storage",
        "messaging",
        "state_management",
        "networking",
        "real_time",
        "infrastructure",
        "code_conventions",
        "dependency_management",
        "type_system",
        "mobile",
        "search",
        "ai_ml_integration",
    }
    missing = expected - set(_ADJACENCY.keys())
    assert not missing, f"Missing disciplines in adjacency graph: {missing}"
