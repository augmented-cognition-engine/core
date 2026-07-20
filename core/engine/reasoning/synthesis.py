# engine/reasoning/synthesis.py
"""Framework synthesis — combine results from multiple frameworks.

When layered or iterative patterns produce multiple perspectives,
synthesize into: agreements, disagreements, unique insights.
"""

from __future__ import annotations

from core.engine.core.config import settings
from core.engine.core.llm import llm


async def synthesize_framework_results(results: list[dict]) -> dict:
    """Synthesize multiple framework outputs into a unified analysis.

    Args:
        results: list of {framework_slug, output} dicts.

    Returns:
        {agreements, disagreements, unique_insights, synthesis}
    """
    if len(results) <= 1:
        return {
            "agreements": [],
            "disagreements": [],
            "unique_insights": [],
            "synthesis": results[0]["output"] if results else "",
        }

    perspectives = "\n\n".join(f"### {r['framework_slug']}:\n{r['output']}" for r in results)

    prompt = f"""You have multiple analytical perspectives on the same problem. Synthesize them.

{perspectives}

Produce a JSON response:
{{
  "agreements": ["points where all perspectives agree"],
  "disagreements": ["points where perspectives conflict, with which perspective holds which view"],
  "unique_insights": ["insights that appear in only one perspective"],
  "synthesis": "A unified conclusion that incorporates the strongest elements from all perspectives"
}}"""

    try:
        result = await llm.complete_json(prompt, model=settings.llm_budget_model)
        return {
            "agreements": result.get("agreements", []),
            "disagreements": result.get("disagreements", []),
            "unique_insights": result.get("unique_insights", []),
            "synthesis": result.get("synthesis", ""),
        }
    except Exception:
        # Fallback: concatenate outputs
        combined = "\n\n---\n\n".join(r["output"] for r in results)
        return {
            "agreements": [],
            "disagreements": [],
            "unique_insights": [],
            "synthesis": combined,
        }
