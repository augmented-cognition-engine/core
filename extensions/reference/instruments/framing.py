"""product-framing instrument — frames a raw product thought into a decision.

This is the bespoke instrument the `Frame` phase of product_decision_intelligence
invokes. It demonstrates the run(**kwargs) + _call_llm() indirection pattern
that ALL kernel instruments use. The _call_llm indirection makes the
instrument testable without touching real LLM endpoints — tests
monkey-patch _call_llm.
"""

from __future__ import annotations

import json
from typing import Any


async def _call_llm(prompt: str, model: str | None = None, system: str | None = None) -> str:
    """Default LLM call — uses the kernel's resolved provider via get_llm().

    Tests monkey-patch this function to avoid real network calls.
    """
    from core.engine.core.config import settings
    from core.engine.core.llm import get_llm

    return await get_llm().complete(
        prompt,
        model=model or settings.llm_budget_model,
        system=system,
    )


_SYSTEM_PROMPT = (
    "You are a product-decision framer. Pure analysis — no tools, no follow-up "
    "questions. Output strict JSON with keys: decision, success_measure, scope_boundary."
)


async def run(*, thought: str, **_kwargs: Any) -> dict[str, Any]:
    """Frame a raw product thought into a decision + success measure + scope.

    Returns:
        {
            "decision": "<one-sentence decision being made>",
            "success_measure": "<how we'll know it worked>",
            "scope_boundary": "<what is in / out of scope>",
        }
    """
    prompt = (
        "A product partner is bringing you a thought. Frame it into a decision "
        "we can actually commit to. Be concrete; no hedging.\n\n"
        f"THOUGHT: {thought}\n\n"
        "Return strict JSON with these three keys: decision, success_measure, scope_boundary."
    )
    raw = await _call_llm(prompt, system=_SYSTEM_PROMPT)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)
