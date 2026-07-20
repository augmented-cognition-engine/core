"""Synthetic task runner — execute and score tasks with specific intelligence.

Used by the domain research agent to A/B test intelligence variants.
Budget LLM for ALL scoring (runs hundreds of times per night).
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.exceptions import ValidationError
from core.engine.core.tokens import TokenAccumulator, clear_accumulator, set_accumulator

logger = logging.getLogger(__name__)


def _validate_synthetic_inputs(task_desc: str, domain: str) -> None:
    """Validate synthetic task inputs before LLM execution.

    Raises ValidationError for empty task descriptions or domain strings,
    preventing meaningless LLM calls that waste tokens and skew A/B scores.
    """
    if not task_desc or not task_desc.strip():
        raise ValidationError("task_desc must be non-empty")
    if not domain or not domain.strip():
        raise ValidationError("domain must be non-empty")


EXECUTE_PROMPT = """You are an expert working in the domain: {domain}

Task: {task_desc}

{intelligence_context}

Provide a thorough, high-quality response."""

SCORE_PROMPT = """Score this task output on 4 criteria (0.0-1.0 each):

Task: {task_desc}
Output: {output}
Expected quality signals: {quality_signals}

Score each criterion:
1. patterns_followed (weight 0.3): Does the output follow known patterns and best practices?
2. correct_complete (weight 0.3): Is the output correct and complete?
3. anti_patterns_avoided (weight 0.2): Does the output avoid known anti-patterns?
4. conventions_used (weight 0.2): Does the output use established conventions?

Return JSON: {{"patterns_followed": <float>, "correct_complete": <float>, "anti_patterns_avoided": <float>, "conventions_used": <float>}}"""


async def run_synthetic_task(
    task_desc: str,
    intelligence_context: str,
    domain: str,
    llm,
) -> tuple[str, int]:
    """Execute a synthetic task. Returns (output_text, total_tokens).

    Raises ValidationError if task_desc or domain are empty.
    """
    _validate_synthetic_inputs(task_desc, domain)
    logger.debug("Synthetic task started: domain=%r task_len=%d", domain, len(task_desc))
    acc = TokenAccumulator()
    set_accumulator(acc)
    try:
        prompt = EXECUTE_PROMPT.format(
            domain=domain,
            task_desc=task_desc[:1000],
            intelligence_context=intelligence_context[:3000],
        )
        output = await llm.complete(prompt, model=settings.llm_budget_model, max_tokens=1024)
        return output, acc.total()
    finally:
        clear_accumulator()


async def score_output(
    task_desc: str,
    output: str,
    quality_signals: list[str],
    llm,
) -> float:
    """Score a task output using 4 weighted criteria. Returns 0.0-1.0."""
    prompt = SCORE_PROMPT.format(
        task_desc=task_desc[:500],
        output=output[:2000],
        quality_signals=", ".join(quality_signals[:10]),
    )

    try:
        result = await llm.complete_json(prompt, model=settings.llm_budget_model)
        weights = {
            "patterns_followed": 0.3,
            "correct_complete": 0.3,
            "anti_patterns_avoided": 0.2,
            "conventions_used": 0.2,
        }
        total = 0.0
        for criterion, weight in weights.items():
            score = float(result.get(criterion, 0.5))
            score = max(0.0, min(1.0, score))
            total += score * weight
        return round(total, 3)
    except Exception as exc:
        logger.warning("Scoring failed: %s", exc)
        return 0.5
