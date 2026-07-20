from unittest.mock import AsyncMock, patch


async def test_ace_diagram_returns_mermaid_string():
    from core.engine.mcp.tools import ace_diagram

    fake_service = AsyncMock()
    fake_service.generate = AsyncMock(return_value="flowchart TB\n    engine[engine]")

    with patch("core.engine.mcp.tools._build_diagram_service", return_value=fake_service):
        result = await ace_diagram(scope="system", product_id="product:platform")

    assert "mermaid" in result
    assert result["mermaid"].startswith("flowchart")
    # Sentinel: fallback string must not appear in success path.
    assert "(ungrouped)" not in result["mermaid"]


async def test_ace_diagram_surfaces_sentinel_when_fallback_fires():
    from core.engine.mcp.tools import ace_diagram

    fallback_output = 'flowchart TB\n    subgraph __ungrouped__ ["(ungrouped)"]\n    end'
    fake_service = AsyncMock()
    fake_service.generate = AsyncMock(return_value=fallback_output)

    with patch("core.engine.mcp.tools._build_diagram_service", return_value=fake_service):
        result = await ace_diagram(scope="system", product_id="product:platform")

    # Sentinel presence → service must flag degraded state for the caller.
    assert result.get("degraded") is True


async def test_ace_diagram_end_to_end_no_sentinel():
    """Real GraphReader + real DiagramService + real MermaidRenderer; only LLM is mocked.

    Boundary: output must be a parseable Mermaid string with <= 15 top-level
    containers and NO '(ungrouped)' sentinel.
    """
    from core.engine.diagram.graph_reader import GraphReader
    from core.engine.diagram.service import DiagramService

    class FixtureProductMap:
        async def get_capabilities(self, product_id, limit=500, offset=0):
            return [
                {
                    "slug": f"cap_{i}",
                    "name": f"Capability {i}",
                    "description": "",
                    "project_slug": "engine" if i < 10 else "portal",
                }
                for i in range(12)
            ]

    fake_llm_response = {
        "containers": [
            {"id": "container:engine", "technology": "Python 3.12", "description": "Backend"},
            {"id": "container:portal", "technology": "React", "description": "UI"},
        ],
        "relationships": [
            {
                "source_id": "container:portal",
                "target_id": "container:engine",
                "description": "calls",
                "technology": "HTTP",
            },
        ],
    }

    fake_llm = AsyncMock()
    fake_llm.complete_json = AsyncMock(return_value=fake_llm_response)

    reader = GraphReader(product_map=FixtureProductMap())
    with patch("core.engine.diagram.abstractor.get_llm", return_value=fake_llm):
        service = DiagramService(reader=reader)
        mermaid = await service.generate(product_id="product:platform", product_name="ACE")

    # Acceptance criteria.
    assert mermaid.startswith("flowchart"), f"Expected flowchart, got: {mermaid[:80]}"
    subgraph_count = mermaid.count("subgraph ")
    assert subgraph_count <= 15, f"Too many top-level containers: {subgraph_count}"

    # SENTINEL CHECK — if this fails, the feature is not working.
    assert "(ungrouped)" not in mermaid, (
        "LLM fallback fired — diagram is degraded. Check abstractor.py and the get_llm() mock."
    )
