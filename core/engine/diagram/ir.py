"""C4-inspired intermediate representation for architecture diagrams.

Three zoom levels: System (product boundary) → Container (deployable/runtime unit)
→ Component (module inside a container). Relationships are typed edges between
any two nodes. The IR is the stable contract between the graph reader, the LLM
abstractor, and renderer adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SystemNode:
    id: str
    name: str
    description: str


@dataclass
class ContainerNode:
    id: str
    name: str
    description: str
    technology: str
    parent_system: str


@dataclass
class ComponentNode:
    id: str
    name: str
    description: str
    parent_container: str
    file_refs: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    source_id: str
    target_id: str
    description: str
    technology: str = ""


@dataclass
class DiagramIR:
    systems: list[SystemNode] = field(default_factory=list)
    containers: list[ContainerNode] = field(default_factory=list)
    components: list[ComponentNode] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def validate(self) -> None:
        system_ids = {s.id for s in self.systems}
        container_ids = {c.id for c in self.containers}
        for c in self.containers:
            if c.parent_system not in system_ids:
                raise ValueError(f"orphan container {c.id}: parent_system={c.parent_system}")
        for comp in self.components:
            if comp.parent_container not in container_ids:
                raise ValueError(f"orphan component {comp.id}: parent_container={comp.parent_container}")
