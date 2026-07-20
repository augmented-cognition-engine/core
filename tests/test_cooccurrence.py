# tests/test_cooccurrence.py
import pytest


def test_extract_subdomain_pairs_single_domain():
    """Single domain_path produces no pairs."""
    from core.engine.graph.cooccurrence import extract_subdomain_pairs

    task = {"domain_path": "architecture", "intelligence_loaded": {}}
    pairs = extract_subdomain_pairs(task)
    assert pairs == []


def test_extract_subdomain_pairs_with_cross_domain():
    """Cross-domain insights produce pairs with the task's domain."""
    from core.engine.graph.cooccurrence import extract_subdomain_pairs

    task = {
        "domain_path": "ux.design-systems",
        "intelligence_loaded": {
            "cross_domain": [{"source_subdomain_slug": "engineering"}],
        },
    }
    pairs = extract_subdomain_pairs(task)
    assert len(pairs) == 1
    assert ("design-systems", "engineering") in pairs or ("engineering", "design-systems") in pairs


def test_extract_subdomain_pairs_no_cross_domain_key():
    """Handles missing cross_domain key gracefully."""
    from core.engine.graph.cooccurrence import extract_subdomain_pairs

    task = {"domain_path": "architecture", "intelligence_loaded": {}}
    pairs = extract_subdomain_pairs(task)
    assert pairs == []


def test_normalize_direction():
    """Bidirectional pairs are canonicalized: in=min, out=max."""
    from core.engine.graph.cooccurrence import normalize_pair

    a, b = normalize_pair("subdomain:zzz", "subdomain:aaa")
    assert a == "subdomain:aaa"
    assert b == "subdomain:zzz"


def test_strength_formula():
    """Strength = min(1.0, co_occurrence / 50)."""
    from core.engine.graph.cooccurrence import calculate_strength

    assert calculate_strength(0) == 0.0
    assert calculate_strength(10) == pytest.approx(0.2)
    assert calculate_strength(25) == pytest.approx(0.5)
    assert calculate_strength(50) == pytest.approx(1.0)
    assert calculate_strength(100) == pytest.approx(1.0)
