"""Test suite for the graph reader — deterministic capability mapping."""

import pytest

from core.engine.diagram.graph_reader import GraphReader
from core.engine.diagram.ir import DiagramIR


class FakeProductMap:
    """In-memory stand-in — real ProductMap hits SurrealDB."""

    async def get_capabilities(self, product_id, limit=500, offset=0):
        return [
            {
                "slug": "scanner",
                "name": "Code Scanner",
                "description": "AST + git",
                "project_slug": "engine",
            },
            {
                "slug": "mcp",
                "name": "MCP Server",
                "description": "Tool exposure",
                "project_slug": "engine",
            },
            {
                "slug": "portal_ui",
                "name": "Portal UI",
                "description": "React frontend",
                "project_slug": "portal",
            },
        ]


@pytest.mark.asyncio
async def test_graph_reader_produces_system_container_component_tree():
    reader = GraphReader(product_map=FakeProductMap())
    ir = await reader.read(product_id="product:platform", product_name="ACE")

    assert isinstance(ir, DiagramIR)
    assert len(ir.systems) == 1
    assert ir.systems[0].name == "ACE"

    # Containers = project_slug groupings ("engine", "portal")
    container_names = sorted(c.name for c in ir.containers)
    assert container_names == ["engine", "portal"]

    # Components = one per capability, parented correctly
    engine_components = [c for c in ir.components if c.parent_container.endswith("engine")]
    assert {c.name for c in engine_components} == {"Code Scanner", "MCP Server"}

    ir.validate()  # no orphans
