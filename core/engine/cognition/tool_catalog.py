# engine/cognition/tool_catalog.py
"""Tool catalog + advisory renderer for phase-level tool-binding.

Maps tool slugs to one-line descriptions and renders the advisory
"## Tools relevant to this phase" prompt section. Advisory only — the
pure-computation phase LLM cannot invoke tools; this surfaces which tools
are well-suited to a cognitive step for the outer agent / human.
"""

from __future__ import annotations

# slug → one-line description (the ACE engineering-hygiene + retrieval tools
# the builder branches use). Unknown slugs render bare (slug only).
TOOL_CATALOG: dict[str, str] = {
    "ace_code_context": "Retrieve structural code context (symbols, callers, dependencies) for a file or component.",
    "ace_blast_radius": "Compute the impact radius of a change — what else it touches.",
    "ace_module_coupling": "Measure coupling between modules to find architectural seams.",
    "ace_diff_impact": "Assess what a specific diff affects across the codebase.",
    "ace_dependency_chain": "Trace the dependency chain into and out of a symbol or module.",
    "ace_pr_review": "Run an engineering-hygiene review pass over a change set.",
    "ace_search": "Semantic + graph search over the knowledge graph.",
    "ace_load": "Load a specific record (decision, insight, capability) from the graph.",
    # Design-branch tools (a different ecosystem from the ace_* engineering tools).
    "refero_search_screens": "Research real production UI screens/flows for this problem class — ground design in evidence, not AI-slop defaults.",
    "shadcn_registry_search": "Find design-system components that satisfy the constraint (composition-correct primitives).",
    "figma_code_connect": "Verify a proposed component maps to a real design-system code component.",
}


def render_phase_tools(tool_slugs: list[str]) -> str:
    """Render the advisory tool section for a phase. Returns '' when no tools."""
    if not tool_slugs:
        return ""
    lines = [
        "\n## Tools relevant to this phase",
        "If acting on this reasoning, these tools are well-suited to this step:",
    ]
    for slug in tool_slugs:
        desc = TOOL_CATALOG.get(slug, "")
        lines.append(f"  - {slug}: {desc}" if desc else f"  - {slug}")
    return "\n".join(lines)
