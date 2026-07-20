"""LLM-driven curation pass: raw DiagramIR -> consulting-grade DiagramIR.

Does three things:
  1. Fills container technology tags (language, framework).
  2. Rewrites container descriptions in a consulting tone.
  3. Infers relationships between containers.

Fails soft: any LLM error or malformed response produces a sentinel container
named "(ungrouped)" so regressions surface loudly in boundary tests instead of
silently shipping raw graph dumps as "architecture diagrams."
"""

from __future__ import annotations

import logging
from dataclasses import replace

from core.engine.core.llm import get_llm
from core.engine.diagram.ir import ContainerNode, DiagramIR, Relationship

logger = logging.getLogger(__name__)

SENTINEL_CONTAINER_NAME = "(ungrouped)"

_PROMPT = """\
You are curating a C4-style architecture diagram. Given the raw IR below
(containers grouped from a code graph), return JSON with:

  containers: [{{"id": <existing id>, "technology": <short tag>, "description": <one-sentence>}}]
  relationships: [{{"source_id": <id>, "target_id": <id>, "description": <short>, "technology": <transport>}}]

Rules:
  - Keep container ids exactly as given. Do not invent new ones.
  - Technology tags must be concrete ("Python 3.12", "React + Vite", "SurrealDB v3").
  - Relationships must reference existing container ids only.
  - Omit a container from the output to leave it unchanged.

Raw IR:
{ir_json}
"""


class DiagramAbstractor:
    async def curate(self, ir: DiagramIR) -> DiagramIR:
        try:
            llm = get_llm()
            import json

            ir_json = json.dumps(
                {
                    "system": ir.systems[0].name if ir.systems else "",
                    "containers": [{"id": c.id, "name": c.name, "summary": c.description} for c in ir.containers],
                },
                indent=2,
            )
            response = await llm.complete_json(
                prompt=_PROMPT.format(ir_json=ir_json),
            )
            return self._apply(ir, response)
        except Exception as exc:
            logger.warning("DiagramAbstractor fallback: %s", exc)
            return self._fallback(ir)

    def _apply(self, ir: DiagramIR, response: dict) -> DiagramIR:
        by_id = {c.id: c for c in ir.containers}
        for patch in response.get("containers", []):
            cid = patch.get("id")
            if cid in by_id:
                by_id[cid] = replace(
                    by_id[cid],
                    technology=patch.get("technology", by_id[cid].technology),
                    description=patch.get("description", by_id[cid].description),
                )
        curated_containers = list(by_id.values())
        valid_ids = set(by_id)
        curated_rels = [
            Relationship(
                source_id=r["source_id"],
                target_id=r["target_id"],
                description=r.get("description", ""),
                technology=r.get("technology", ""),
            )
            for r in response.get("relationships", [])
            if r.get("source_id") in valid_ids and r.get("target_id") in valid_ids
        ]
        return DiagramIR(
            systems=ir.systems,
            containers=curated_containers,
            components=ir.components,
            relationships=curated_rels,
        )

    def _fallback(self, ir: DiagramIR) -> DiagramIR:
        sentinel_id = "container:__ungrouped__"
        sentinel = ContainerNode(
            id=sentinel_id,
            name=SENTINEL_CONTAINER_NAME,
            description="LLM abstraction unavailable — raw graph grouping",
            technology="",
            parent_system=ir.systems[0].id if ir.systems else "sys:unknown",
        )
        return DiagramIR(
            systems=ir.systems,
            containers=list(ir.containers) + [sentinel],
            components=ir.components,
            relationships=ir.relationships,
        )
