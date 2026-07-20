# engine/graph/classifier.py
"""Graph-aware task classifier.

Augments the LLM classification with concrete code-graph context so the
orchestrator makes better decisions about archetype, mode, and engagement.

When graph context includes risk flags, the classifier biases toward
deliberative mode.  When multiple fragile files are involved, it biases
toward multi-perspective engagement.  Historical agent performance data
from the graph informs archetype and perspective selection.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.orchestrator.classifier import _validate

logger = logging.getLogger(__name__)


def _build_graph_context_section(graph_context: dict) -> str:
    """Format graph context into a text section for the LLM prompt."""
    sections: list[str] = []

    # Relevant files
    files = graph_context.get("relevant_files", [])
    if files:
        sections.append("Code context from the intelligence graph:")
        for f in files[:10]:
            parts = [f["path"]]
            fc = f.get("function_count", 0)
            dc = f.get("dependent_count", 0)
            cf = f.get("change_frequency", 0)
            if fc:
                parts.append(f"{fc} functions")
            if dc:
                parts.append(f"{dc} dependents")
            if cf:
                parts.append(f"changed {cf}x")
            sections.append(f"  - {', '.join(parts)}")

    # Decisions
    decisions = graph_context.get("decisions", [])
    if decisions:
        sections.append("\nRecent decisions in this code area:")
        for d in decisions[:5]:
            outcome = d.get("outcome", "unknown")
            sections.append(f"  - {d['title']} (outcome: {outcome})")

    # Risk flags
    risk_flags = graph_context.get("risk_flags", [])
    if risk_flags:
        sections.append("\nRisk flags:")
        for r in risk_flags:
            sections.append(f"  - {r}")

    # Agent history
    history = graph_context.get("agent_history", [])
    if history:
        sections.append("\nHistorical agent configs used on these files:")
        for h in history[:5]:
            sections.append(f"  - {h.get('perspective', '?')}/{h.get('mode', '?')}/{h.get('archetype', '?')}")

    return "\n".join(sections) if sections else ""


async def classify_with_graph(
    description: str,
    graph_context: dict,
    product_id: str = "product:default",
) -> dict:
    """Classify a task using both LLM and graph context.

    The graph context informs:
    - Which files are relevant (from the graph, not LLM guessing)
    - Risk level (fragile files -> deliberative mode)
    - Best agent config (from historical success)
    - Whether multi-perspective engagement is needed

    Returns the same shape as ``classify_task()``:
    ``{domain_path, archetype, mode, complexity, perspective, specialties, org_context, engagement}``
    """
    graph_section = _build_graph_context_section(graph_context)
    risk_flags = graph_context.get("risk_flags", [])
    relevant_files = graph_context.get("relevant_files", [])

    # Build risk-aware hints
    risk_hint = ""
    if risk_flags:
        risk_hint = (
            "\n\nIMPORTANT: Risk flags are present. "
            "Prefer deliberative mode for careful reasoning. "
            "If multiple fragile files are involved, consider multi-perspective engagement."
        )

    fragile_count = sum(
        1 for f in relevant_files if f.get("change_frequency", 0) > 5 or f.get("fragility_score", 0) > 0.7
    )
    engagement_hint = ""
    if fragile_count >= 2:
        engagement_hint = (
            "\nMultiple fragile files detected. "
            "Consider using adversarial pairing (e.g., practitioner vs strategist) "
            "to validate the approach."
        )

    try:
        result = await llm.complete_json(
            f"""Classify this task across seven dimensions.

Task: {description}

{graph_section}
{risk_hint}
{engagement_hint}

Dimensions:
1. domain_path -- one of: strategy, operations, finance, technology, revenue, marketing, product, legal, people, security, experience, data (top level), with a subdomain guess in kebab-case
2. archetype -- the type of work:
   - creator: building something new
   - analyst: analyzing information, producing insights
   - executor: running a defined task precisely
   - researcher: investigating, gathering information
   - advisor: recommending a decision or course of action
   - sentinel: monitoring, reviewing, flagging issues
3. mode -- how to think:
   - deliberative: step-by-step, thorough, considering alternatives
   - reactive: fast, pattern-match, direct answer
   - exploratory: broad, divergent, generating possibilities
   - conversational: interactive, needs clarification
   - procedural: follow a checklist or process
   - reflective: self-assessing, quality-focused
4. complexity -- simple | moderate | complex
5. perspective -- theorist | practitioner | strategist | operator
6. specialties -- list of up to 3 relevant specialty slugs (kebab-case, empty list if none)
7. org_context -- list of up to 5 short strings describing relevant org context (empty list if none)
8. engagement -- {{"perspectives": ["..."], "adversarial_pair": null or ["a","b"], "rationale": "why"}}

Return JSON:
{{"domain_path": "domain.subdomain", "archetype": "...", "mode": "...", "complexity": "...", "perspective": "...", "specialties": [], "org_context": [], "engagement": {{"perspectives": ["..."], "adversarial_pair": null, "rationale": "..."}}}}""",
            model=settings.llm_budget_model,
        )
        return _validate(result)
    except Exception as e:
        logger.warning("classify_with_graph failed: %s", e)
        # Return a sensible default biased by risk flags
        mode = "deliberative" if risk_flags else "reactive"
        return {
            "domain_path": "technology",
            "archetype": "executor",
            "mode": mode,
            "perspective": "practitioner",
            "complexity": "moderate" if risk_flags else "simple",
            "specialties": [],
            "org_context": [],
            "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
        }
