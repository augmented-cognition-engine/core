"""Mermaid flowchart renderer.

Emits one subgraph per Container, nodes inside for Components, and edges for
Relationships. Mermaid is chosen for Phase 1 because it renders natively in
GitHub, portal markdown, and PR comments without any runtime dependency.
"""

from __future__ import annotations

import re

from core.engine.diagram.ir import DiagramIR
from core.engine.diagram.renderers.base import Renderer


def _safe_id(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def _safe_label(raw: str) -> str:
    # Mermaid treats [ ] ( ) as syntax — strip or escape.
    return raw.replace("[", "(").replace("]", ")").replace('"', "'")


class MermaidRenderer(Renderer):
    def render(self, ir: DiagramIR) -> str:
        lines: list[str] = ["flowchart TB"]
        components_by_container: dict[str, list] = {}
        for comp in ir.components:
            components_by_container.setdefault(comp.parent_container, []).append(comp)

        for container in ir.containers:
            cid = _safe_id(container.id)
            label = _safe_label(container.name)
            if container.technology:
                label = f"{label}<br/><i>{_safe_label(container.technology)}</i>"
            lines.append(f'    subgraph {cid} ["{label}"]')
            for comp in components_by_container.get(container.id, []):
                comp_id = _safe_id(comp.id)
                lines.append(f'        {comp_id}["{_safe_label(comp.name)}"]')
            lines.append("    end")

        for rel in ir.relationships:
            src = _safe_id(rel.source_id)
            dst = _safe_id(rel.target_id)
            label = _safe_label(rel.description) if rel.description else ""
            if label:
                lines.append(f"    {src} -->|{label}| {dst}")
            else:
                lines.append(f"    {src} --> {dst}")

        return "\n".join(lines)
