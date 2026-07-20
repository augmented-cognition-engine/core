from core.engine.diagram.ir import (
    ComponentNode,
    ContainerNode,
    DiagramIR,
    Relationship,
    SystemNode,
)


def test_diagram_ir_round_trips_minimal_system():
    system = SystemNode(id="sys:ace", name="ACE", description="Autonomous PM")
    container = ContainerNode(
        id="container:engine",
        name="engine",
        description="Python backend",
        technology="Python 3.12",
        parent_system="sys:ace",
    )
    component = ComponentNode(
        id="component:scanner",
        name="scanner",
        description="AST + git scanner",
        parent_container="container:engine",
        file_refs=["core/engine/scanner/scanner.py"],
    )
    rel = Relationship(
        source_id="container:engine",
        target_id="container:portal",
        description="serves API",
        technology="HTTP",
    )
    ir = DiagramIR(
        systems=[system],
        containers=[container],
        components=[component],
        relationships=[rel],
    )
    assert ir.systems[0].name == "ACE"
    assert ir.containers[0].parent_system == "sys:ace"
    assert ir.components[0].parent_container == "container:engine"
    assert len(ir.relationships) == 1


def test_diagram_ir_rejects_orphan_container():
    # Container pointing at a non-existent system should raise on validate().
    import pytest

    from core.engine.diagram.ir import ContainerNode, DiagramIR

    ir = DiagramIR(
        systems=[],
        containers=[
            ContainerNode(
                id="c:x",
                name="x",
                description="",
                technology="",
                parent_system="sys:missing",
            )
        ],
        components=[],
        relationships=[],
    )
    with pytest.raises(ValueError, match="orphan container"):
        ir.validate()
