# engine/reasoning/selector.py
"""Framework selector — choose 1-3 reasoning frameworks for a task.

Selection logic from Doc 24:
1. Activation signal matching (keyword scan)
2. Archetype affinity filtering (>= 0.3)
3. Mode affinity filtering (>= 0.3)
4. Task type affinity weighting (optional — defaults to 1.0 if missing)
5. Composability constraint check (no conflicts)
6. Score = signal_match * archetype_weight * mode_weight * task_type_weight
7. Top 1-3 by score, above threshold 0.4
8. Determine composition pattern
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.engine.core.db import pool
from core.engine.reasoning.models import Framework, FrameworkSelection

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.4
MAX_FRAMEWORKS = 3
MIN_AFFINITY = 0.3

# Modes/complexity where frameworks are skipped (fast path)
SKIP_MODES = {"reactive", "procedural"}
SKIP_COMPLEXITY = {"simple"}

# Families that participate in iterative generate/evaluate patterns
GENERATIVE_FAMILIES = {"generative", "predictive"}
EVALUATIVE_FAMILIES = {"evaluative", "adversarial", "diagnostic"}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.lower()))


def score_framework(
    fw: Framework,
    description_tokens: set[str],
    archetype: str,
    mode: str,
    task_type: str = "",
) -> float:
    """Score a framework for a given task. Returns 0.0 if filtered out."""
    # Signal matching
    if not fw.activation_signals:
        return 0.0

    matched = 0
    for signal in fw.activation_signals:
        signal_tokens = _tokenize(signal)
        if signal_tokens & description_tokens:
            matched += 1

    if matched == 0:
        return 0.0

    signal_score = matched / len(fw.activation_signals)

    # Archetype affinity
    arch_weight = fw.archetype_affinity.get(archetype, 0.0)
    if arch_weight < MIN_AFFINITY:
        return 0.0

    # Mode affinity
    mode_weight = fw.mode_affinity.get(mode, 0.0)
    if mode_weight < MIN_AFFINITY:
        return 0.0

    # Task type affinity — optional; default 1.0 (universal) when missing or task_type unknown
    task_type_weight = fw.task_type_affinity.get(task_type, 1.0) if task_type else 1.0

    return signal_score * arch_weight * mode_weight * task_type_weight


def check_composability(selected: list[Framework], candidate: Framework) -> bool:
    """Check if candidate conflicts with any already-selected framework."""
    candidate_conflicts = set(candidate.composability.get("conflicts", []))
    for existing in selected:
        if existing.slug in candidate_conflicts:
            return False
        existing_conflicts = set(existing.composability.get("conflicts", []))
        if candidate.slug in existing_conflicts:
            return False
    return True


def determine_pattern(frameworks: list[Framework]) -> str:
    """Determine composition pattern based on selected frameworks."""
    if len(frameworks) <= 1:
        return "stacked"

    families = {fw.family for fw in frameworks}
    has_generative = bool(families & GENERATIVE_FAMILIES)
    has_evaluative = bool(families & EVALUATIVE_FAMILIES)

    if has_generative and has_evaluative:
        return "iterative"

    return "layered"


async def select_frameworks(
    classification: dict[str, Any],
    product_id: str,
    description: str = "",
    max_frameworks: int = MAX_FRAMEWORKS,
    force: bool = False,
) -> FrameworkSelection | None:
    """Select 1-3 reasoning frameworks for a task.

    Returns None if: complexity=simple, mode=reactive/procedural, or no frameworks above threshold.
    When force=True, skips the complexity/mode gates.
    """
    # Deprecated: framework selection is now handled by engine.cognition.composer.
    # This function is retained for backward compatibility only.
    # New code should call CognitiveComposer.compose() instead.
    complexity = classification.get("complexity", "simple")
    mode = classification.get("mode", "reactive")
    archetype = classification.get("archetype", "executor")
    task_type = classification.get("task_type", "")

    # Fast path: skip frameworks for simple/reactive tasks (unless forced)
    if not force and (complexity in SKIP_COMPLEXITY or mode in SKIP_MODES):
        return None

    description_tokens = _tokenize(description)
    description_tokens |= _tokenize(classification.get("discipline", "") or classification.get("domain_path", ""))

    # Query available frameworks
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM framework WHERE product IS NONE OR product = <record>$product",
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

    if not rows:
        return None

    # Score all frameworks
    scored: list[tuple[float, Framework]] = []
    for row in rows:
        fw = Framework(
            slug=row.get("slug", ""),
            name=row.get("name", ""),
            family=row.get("family", ""),
            tier=row.get("tier", "built-in"),
            description=row.get("description", ""),
            system_prompt=row.get("system_prompt", ""),
            activation_signals=row.get("activation_signals", []),
            archetype_affinity=row.get("archetype_affinity", {}),
            mode_affinity=row.get("mode_affinity", {}),
            task_type_affinity=row.get("task_type_affinity", {}),
            composability=row.get("composability", {}),
        )

        score = score_framework(fw, description_tokens, archetype, mode, task_type)
        if score >= SCORE_THRESHOLD:
            scored.append((score, fw))

    if not scored:
        return None

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Select top frameworks with composability checks
    selected: list[Framework] = []
    selected_scores: list[float] = []

    for score, fw in scored:
        if len(selected) >= max_frameworks:
            break
        if check_composability(selected, fw):
            selected.append(fw)
            selected_scores.append(score)

    if not selected:
        return None

    pattern = determine_pattern(selected)

    logger.info(
        f"Frameworks selected: {[fw.slug for fw in selected]} "
        f"(pattern={pattern}, scores={[f'{s:.2f}' for s in selected_scores]})"
    )

    return FrameworkSelection(
        frameworks=selected,
        composition_pattern=pattern,
        scores=selected_scores,
    )
