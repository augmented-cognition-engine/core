"""Tests for synthesizer insight-to-graph routing."""

from core.engine.capture.synthesizer import _route_to_graph


def test_fact_routes_to_specialty():
    assert _route_to_graph("fact") == "specialty"


def test_pattern_routes_to_specialty():
    assert _route_to_graph("pattern") == "specialty"


def test_discovery_routes_to_specialty():
    assert _route_to_graph("discovery") == "specialty"


def test_convention_routes_to_org():
    assert _route_to_graph("convention") == "org"


def test_preference_routes_to_org():
    assert _route_to_graph("preference") == "org"


def test_decision_routes_to_org():
    assert _route_to_graph("decision") == "org"


def test_correction_routes_to_inherit():
    assert _route_to_graph("correction") == "inherit"


def test_unknown_defaults_to_org():
    assert _route_to_graph("unknown_type") == "org"
