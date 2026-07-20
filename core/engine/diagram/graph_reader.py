"""Read ACE's product graph and build a raw DiagramIR.

This is deterministic and LLM-free: it groups capabilities by their project_slug
into Container nodes, emits one Component per capability, and leaves
Relationships empty (inferred later by the abstractor from shared file paths or
explicit dependency edges). The point of this layer is to produce a faithful,
un-editorialized snapshot of what's actually in the graph.
"""

from __future__ import annotations

from collections import defaultdict

from core.engine.diagram.ir import (
    ComponentNode,
    ContainerNode,
    DiagramIR,
    SystemNode,
)


class GraphReader:
    """Read capabilities from ProductMap and emit a raw C4 IR tree."""

    def __init__(self, product_map):
        self._product_map = product_map

    async def read(self, product_id: str, product_name: str) -> DiagramIR:
        """Build a DiagramIR from capabilities.

        Args:
            product_id: SurrealDB product record ID (e.g., "product:platform")
            product_name: Human name for the system (e.g., "ACE")

        Returns:
            DiagramIR with one System, one Container per project_slug, and one
            Component per capability.
        """
        caps = await self._product_map.get_capabilities(product_id)

        system_id = f"sys:{product_id.split(':', 1)[-1]}"
        system = SystemNode(
            id=system_id,
            name=product_name,
            description=f"System boundary for {product_name}",
        )

        # Group capabilities by project_slug → one Container per group.
        by_project: dict[str, list[dict]] = defaultdict(list)
        for cap in caps:
            by_project[cap.get("project_slug") or "root"].append(cap)

        containers: list[ContainerNode] = []
        components: list[ComponentNode] = []
        for project_slug, project_caps in sorted(by_project.items()):
            container_id = f"container:{project_slug}"
            containers.append(
                ContainerNode(
                    id=container_id,
                    name=project_slug,
                    description=f"{len(project_caps)} capabilities",
                    technology="",  # filled by abstractor
                    parent_system=system_id,
                )
            )
            for cap in project_caps:
                components.append(
                    ComponentNode(
                        id=f"component:{cap['slug']}",
                        name=cap.get("name") or cap["slug"],
                        description=cap.get("description", ""),
                        parent_container=container_id,
                        file_refs=[],
                    )
                )

        return DiagramIR(
            systems=[system],
            containers=containers,
            components=components,
            relationships=[],
        )
