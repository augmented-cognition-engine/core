# engine/orchestration/dispatcher.py
"""Mode and pattern selection for the orchestration layer.

The dispatcher examines the request and its classification to decide:
1. Which orchestration mode (reactive / deliberative / reflective)
2. Which execution pattern (independent / team / pipeline / adversarial / fanout)

NO DEFAULTS — task characteristics determine everything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DispatchDecision:
    """Result of dispatch: which mode and pattern to use."""

    mode: str  # "reactive" | "deliberative" | "reflective"
    pattern: str  # "independent" | "team" | "pipeline" | "adversarial" | "fanout"
    reasoning: str  # Why this combination was chosen


def dispatch(request, classification: dict[str, Any]) -> DispatchDecision:
    """Select orchestration mode and execution pattern.

    Args:
        request: OrchestrationRequest
        classification: dict with domain_path, archetype, mode, complexity
    """
    # 1. Explicit pattern override from request (evolution engine knows what it wants)
    if request.pattern:
        mode = "reactive" if classification.get("complexity") == "simple" else "deliberative"
        return DispatchDecision(
            mode=mode,
            pattern=request.pattern,
            reasoning=f"Explicit pattern override: {request.pattern}",
        )

    complexity = classification.get("complexity", "simple")
    source = request.source

    # 2. Chat source + simple/moderate = fast reactive Pattern A
    if source == "chat" and complexity in ("simple", "moderate"):
        return DispatchDecision(
            mode="reactive",
            pattern="independent",
            reasoning="Chat source with simple/moderate complexity → reactive independent",
        )

    # 3. Forced skill with multi-step → Pattern C
    if request.force_skill:
        return DispatchDecision(
            mode="reactive",
            pattern="pipeline",
            reasoning=f"Forced skill '{request.force_skill}' → pipeline execution",
        )

    # 4. Multiple agent configs provided → infer pattern
    if request.agent_configs and len(request.agent_configs) > 1:
        roles = {ac.role for ac in request.agent_configs}
        if "evaluator" in roles or "critic" in roles:
            return DispatchDecision(
                mode="deliberative",
                pattern="adversarial",
                reasoning="Agent configs include evaluator/critic → adversarial pattern",
            )
        # All same role → fanout
        if len(roles) == 1:
            return DispatchDecision(
                mode="reactive",
                pattern="fanout",
                reasoning="Multiple agents with same role → fan-out pattern",
            )
        # Different roles → pipeline
        return DispatchDecision(
            mode="deliberative",
            pattern="pipeline",
            reasoning="Multiple agents with different roles → pipeline pattern",
        )

    # 5. Complex task → deliberative, LLM decides pattern
    if complexity == "complex":
        return DispatchDecision(
            mode="deliberative",
            pattern="pipeline",
            reasoning="Complex task → deliberative pipeline (LLM plans decomposition)",
        )

    # 6. Simple/moderate single task → reactive Pattern A
    return DispatchDecision(
        mode="reactive",
        pattern="independent",
        reasoning=f"Standard {complexity} task → reactive independent",
    )
