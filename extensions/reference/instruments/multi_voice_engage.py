"""multi-voice-engage instrument — the in-recipe wrapper around execute_engagement.

This is the partnership thesis in a recipe phase: invoke a multi-archetype team
(pm + skeptic + ux_designer) from inside the `Voices` phase of the
product_decision_intelligence recipe. Each archetype reasons in parallel as a
light multi-voice spin; results are merged for the next phase.

We use execute_engagement (multi-voice LIGHT) not run_deep_committee (multi-voice
DEEP). The deep committee orchestrates the OUTER build path; nesting it inside a
recipe phase would cause recursive committee execution. execute_engagement is the
right shape for in-recipe multi-voice — already-existing kernel primitive.
"""

from __future__ import annotations

from typing import Any

# Imported at module top so tests can monkey-patch this name.
from core.engine.orchestrator.engagement import execute_engagement

_ARCHETYPES = ["pm", "skeptic", "ux_designer"]


async def run(*, thought: str, product_id: str = "product:platform", **_kwargs: Any) -> dict[str, Any]:
    """Engage a product team (pm + skeptic + ux_designer) on the thought.

    Returns:
        {
            "merged_output": "<synthesized cross-archetype output>",
            "perspectives": ["pm", "skeptic", "ux_designer"],
        }
    """
    classification = {
        "discipline": "product_strategy",
        "mode": "deliberative",
        "complexity": "moderate",
        "engagement": {
            "perspectives": _ARCHETYPES,
            "adversarial_pair": None,
            "rationale": "product-decision team: a PM, a Skeptic, and a User-Advocate reason in parallel.",
        },
    }
    result = await execute_engagement(thought, classification, product_id)
    return {
        "merged_output": getattr(result, "merged_output", ""),
        "perspectives": list(_ARCHETYPES),
    }
