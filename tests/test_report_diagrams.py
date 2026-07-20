# tests/test_report_diagrams.py
"""Tests for DiagramGenerator — SVG heat map and Mermaid DSL output."""


def test_svg_heatmap_returns_svg_string():
    """svg_risk_heatmap() returns a string starting with <svg."""
    from core.engine.reports.diagrams import DiagramGenerator

    health = [
        {"discipline": "security", "avg_score": 0.2, "gap_count": 2},
        {"discipline": "testing", "avg_score": 0.75, "gap_count": 0},
    ]
    result = DiagramGenerator().svg_risk_heatmap(health)
    assert isinstance(result, str)
    assert result.strip().startswith("<svg")
    assert "</svg>" in result
    # Both discipline labels should appear
    assert "security" in result
    assert "testing" in result


def test_svg_heatmap_empty_input():
    """svg_risk_heatmap() returns a valid non-crashing SVG for empty input."""
    from core.engine.reports.diagrams import DiagramGenerator

    result = DiagramGenerator().svg_risk_heatmap([])
    assert isinstance(result, str)
    assert "<svg" in result
    assert "</svg>" in result


def test_svg_heatmap_none_score_does_not_crash():
    """avg_score=None from DB must not raise TypeError."""
    from core.engine.reports.diagrams import DiagramGenerator

    health = [{"discipline": "security", "avg_score": None, "gap_count": 0}]
    result = DiagramGenerator().svg_risk_heatmap(health)
    assert "<svg" in result
    assert "</svg>" in result


def test_mermaid_arch_map_groups_by_category():
    """mermaid_architecture_map() groups capabilities into subgraphs by category."""
    from core.engine.reports.diagrams import DiagramGenerator

    caps = [
        {"slug": "auth", "category": "Core", "depends_on": []},
        {"slug": "api_gateway", "category": "Core", "depends_on": []},
        {"slug": "orchestrator", "category": "Intelligence", "depends_on": []},
    ]
    result = DiagramGenerator().mermaid_architecture_map(caps)
    assert "flowchart LR" in result
    assert "Core" in result
    assert "Intelligence" in result
    # Both nodes in Core should appear
    assert "auth" in result.lower() or "Auth" in result
    assert "api" in result.lower()


def test_mermaid_arch_map_empty_caps():
    """mermaid_architecture_map() returns valid fallback DSL for empty input."""
    from core.engine.reports.diagrams import DiagramGenerator

    result = DiagramGenerator().mermaid_architecture_map([])
    assert isinstance(result, str)
    assert "flowchart" in result


def test_mermaid_cap_graph_emits_edges():
    """mermaid_capability_graph() emits --> edges for depends_on relationships."""
    from core.engine.reports.diagrams import DiagramGenerator

    caps = [
        {"slug": "api", "depends_on": []},
        {"slug": "auth", "depends_on": ["capability:api"]},
    ]
    result = DiagramGenerator().mermaid_capability_graph(caps)
    assert "graph TD" in result
    assert "-->" in result
    assert "api" in result.lower()
    assert "auth" in result.lower()


def test_mermaid_cap_graph_limits_to_20_nodes():
    """mermaid_capability_graph() uses at most 20 capabilities."""
    from core.engine.reports.diagrams import DiagramGenerator

    caps = [{"slug": f"cap_{i}", "depends_on": []} for i in range(25)]
    result = DiagramGenerator().mermaid_capability_graph(caps)
    # Count node definition lines (lines with [...])
    node_lines = [ln for ln in result.splitlines() if "[" in ln and "-->" not in ln]
    assert len(node_lines) <= 20


def test_mermaid_methods_none_slug_does_not_crash():
    """capabilities with slug=None must not crash either Mermaid method."""
    from core.engine.reports.diagrams import DiagramGenerator

    caps = [{"slug": None, "category": "Core", "depends_on": [None]}]
    gen = DiagramGenerator()
    arch = gen.mermaid_architecture_map(caps)
    graph = gen.mermaid_capability_graph(caps)
    assert "flowchart" in arch
    assert "graph" in graph
