# engine/cognition/self_consistency.py
"""Self-consistency sampling for close-call LLM evaluations.

Instead of escalating to a stronger (more expensive) model when confidence is
low, we sample the *same* model N times in parallel and aggregate results.

Why this works:
- Uncorrelated failure modes: independent samples fail on different edge cases
- Majority vote / score averaging cancels noise more effectively than one
  expensive opinion
- 3× Haiku in parallel is faster than 1 Sonnet call and often more accurate

Usage in evaluators:
    samples = await sample_structured(prompt, MySchema, model=budget_model, n=3)
    avg = aggregate_scores(samples, score_field="score")
"""

from __future__ import annotations

import asyncio
import logging
from typing import TypeVar

from pydantic import BaseModel

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def sample_structured(
    prompt: str,
    schema: type[T],
    model: str,
    n: int = 3,
) -> list[T]:
    """Run N parallel structured completions. Returns only successful results.

    Failed samples are silently dropped — caller aggregates what's available.
    Never raises; returns empty list if all samples fail.
    """
    llm = get_llm()

    async def _one() -> T | None:
        try:
            return await llm.complete_structured(prompt, schema=schema, model=model)
        except Exception as exc:
            logger.debug("Self-consistency sample failed (non-fatal): %s", exc)
            return None

    results = await asyncio.gather(*[_one() for _ in range(n)])
    return [r for r in results if r is not None]


def aggregate_scores(results: list, score_field: str = "score") -> float:
    """Average scores across samples. Returns 0.5 if no valid results."""
    scores = [getattr(r, score_field, None) for r in results]
    valid = [s for s in scores if s is not None and isinstance(s, (int, float))]
    if not valid:
        return 0.5
    return sum(valid) / len(valid)


def disagreement(results: list, score_field: str = "score") -> float:
    """Spread (max - min) of sample scores — a self-consistency honesty signal.

    0.0 = the samples agree (stable judgment); up to 1.0 = maximal disagreement.
    Returns 0.0 with fewer than 2 valid scores (disagreement is not measurable).

    The close-call evaluator already samples the same model N times; this turns the
    discarded spread into a signal that the verdict is unstable, so an inflated
    self-reported score can be discounted before it feeds selection and learning.
    """
    scores = [getattr(r, score_field, None) for r in results]
    valid = [s for s in scores if s is not None and isinstance(s, (int, float))]
    if len(valid) < 2:
        return 0.0
    return max(valid) - min(valid)


def most_conservative(results: list[T], violation_field: str = "violated_constraints") -> T | None:
    """Return the sample with the most constraint violations (most cautious verdict)."""
    if not results:
        return None
    return max(results, key=lambda r: len(getattr(r, violation_field, []) or []))
