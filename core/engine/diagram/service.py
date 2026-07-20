"""DiagramService — orchestrates graph reader -> abstractor -> renderer."""

from __future__ import annotations

from core.engine.diagram.abstractor import DiagramAbstractor
from core.engine.diagram.graph_reader import GraphReader
from core.engine.diagram.renderers.base import Renderer
from core.engine.diagram.renderers.mermaid import MermaidRenderer


class DiagramService:
    def __init__(
        self,
        reader: GraphReader,
        abstractor: DiagramAbstractor | None = None,
        renderer: Renderer | None = None,
    ):
        self._reader = reader
        self._abstractor = abstractor or DiagramAbstractor()
        self._renderer = renderer or MermaidRenderer()

    async def generate(self, product_id: str, product_name: str) -> str:
        raw = await self._reader.read(product_id=product_id, product_name=product_name)
        curated = await self._abstractor.curate(raw)
        curated.validate()
        return self._renderer.render(curated)
