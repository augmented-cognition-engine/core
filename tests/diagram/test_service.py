from unittest.mock import AsyncMock

from core.engine.diagram.ir import ContainerNode, DiagramIR, SystemNode
from core.engine.diagram.service import DiagramService


async def test_service_reads_curates_and_renders():
    raw = DiagramIR(
        systems=[SystemNode(id="sys:ace", name="ACE", description="")],
        containers=[
            ContainerNode(
                id="container:engine",
                name="engine",
                description="",
                technology="",
                parent_system="sys:ace",
            )
        ],
        components=[],
        relationships=[],
    )
    curated = DiagramIR(
        systems=raw.systems,
        containers=[
            ContainerNode(
                id="container:engine",
                name="engine",
                description="backend",
                technology="Python 3.12",
                parent_system="sys:ace",
            )
        ],
        components=[],
        relationships=[],
    )

    reader = AsyncMock()
    reader.read = AsyncMock(return_value=raw)
    abstractor = AsyncMock()
    abstractor.curate = AsyncMock(return_value=curated)

    service = DiagramService(reader=reader, abstractor=abstractor)
    out = await service.generate(product_id="product:platform", product_name="ACE")

    assert "flowchart" in out
    assert "Python 3.12" in out
    reader.read.assert_awaited_once()
    abstractor.curate.assert_awaited_once()
