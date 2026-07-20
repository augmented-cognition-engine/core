from unittest.mock import AsyncMock, patch

import pytest

from core.engine.diagram.abstractor import DiagramAbstractor
from core.engine.diagram.ir import ContainerNode, DiagramIR, SystemNode


@pytest.fixture
def raw_ir():
    return DiagramIR(
        systems=[SystemNode(id="sys:ace", name="ACE", description="")],
        containers=[
            ContainerNode(
                id="container:engine",
                name="engine",
                description="20 caps",
                technology="",
                parent_system="sys:ace",
            ),
            ContainerNode(
                id="container:portal",
                name="portal",
                description="5 caps",
                technology="",
                parent_system="sys:ace",
            ),
        ],
        components=[],
        relationships=[],
    )


async def test_abstractor_fills_technology_and_adds_relationships(raw_ir):
    fake_response = {
        "containers": [
            {"id": "container:engine", "technology": "Python 3.12", "description": "Autonomous PM backend"},
            {"id": "container:portal", "technology": "React + Vite", "description": "Consulting portal UI"},
        ],
        "relationships": [
            {
                "source_id": "container:portal",
                "target_id": "container:engine",
                "description": "calls MCP tools",
                "technology": "HTTP+JSON",
            },
        ],
    }
    llm = AsyncMock()
    llm.complete_json = AsyncMock(return_value=fake_response)

    with patch("core.engine.diagram.abstractor.get_llm", return_value=llm):
        abstractor = DiagramAbstractor()
        curated = await abstractor.curate(raw_ir)

    engine = next(c for c in curated.containers if c.id == "container:engine")
    assert engine.technology == "Python 3.12"
    assert engine.description == "Autonomous PM backend"
    assert len(curated.relationships) == 1
    # Sentinel: no fallback container.
    assert not any(c.name == "(ungrouped)" for c in curated.containers)


async def test_abstractor_falls_back_with_sentinel_on_llm_error(raw_ir):
    llm = AsyncMock()
    llm.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

    with patch("core.engine.diagram.abstractor.get_llm", return_value=llm):
        abstractor = DiagramAbstractor()
        curated = await abstractor.curate(raw_ir)

    # Fallback emits sentinel so downstream tests/monitoring catch silent failures.
    assert any(c.name == "(ungrouped)" for c in curated.containers)
