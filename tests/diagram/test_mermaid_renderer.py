from core.engine.diagram.ir import (
    ContainerNode,
    DiagramIR,
    Relationship,
    SystemNode,
)
from core.engine.diagram.renderers.mermaid import MermaidRenderer


def test_mermaid_renderer_emits_flowchart_with_subgraphs():
    ir = DiagramIR(
        systems=[SystemNode(id="sys:ace", name="ACE", description="")],
        containers=[
            ContainerNode(
                id="container:engine",
                name="engine",
                description="backend",
                technology="Python 3.12",
                parent_system="sys:ace",
            ),
            ContainerNode(
                id="container:portal", name="portal", description="ui", technology="React", parent_system="sys:ace"
            ),
        ],
        components=[],
        relationships=[
            Relationship(
                source_id="container:portal", target_id="container:engine", description="calls", technology="HTTP"
            ),
        ],
    )
    out = MermaidRenderer().render(ir)

    assert out.startswith("flowchart")
    assert "subgraph" in out
    assert "engine" in out
    assert "Python 3.12" in out
    assert "portal" in out
    assert "-->" in out
    assert "calls" in out


def test_mermaid_renderer_escapes_brackets_in_names():
    ir = DiagramIR(
        systems=[SystemNode(id="sys:x", name="X", description="")],
        containers=[
            ContainerNode(
                id="container:weird",
                name="weird[node]",
                description="",
                technology="",
                parent_system="sys:x",
            )
        ],
        components=[],
        relationships=[],
    )
    out = MermaidRenderer().render(ir)
    # Unescaped brackets break Mermaid parsing.
    assert "weird[node]" not in out
    assert "weird" in out
