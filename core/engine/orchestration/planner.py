# engine/orchestration/planner.py
"""Deliberative planning via LLM.

When the dispatcher selects deliberative mode, the planner uses a
budget-tier LLM to decompose the task into an ``ExecutionPlan`` of
typed ``PlanStep`` nodes.  Falls back to single-step execution on
any LLM failure — the system must never stall on planning errors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

_VALID_PATTERNS = frozenset(["independent", "pipeline", "adversarial", "fanout"])
_MAX_PLAN_STEPS = 3


def _validate_plan_inputs(description: str, classification: dict) -> None:
    """Validate planning inputs before calling the LLM.

    Raises ValidationError for empty descriptions or missing classification
    so the planner never sends a meaningless prompt and wastes budget tokens.
    """
    if not description or not description.strip():
        raise ValidationError("description must be non-empty for execution planning")
    if not isinstance(classification, dict):
        raise ValidationError(f"classification must be a dict, got {type(classification).__name__}")


@dataclass
class PlanStep:
    """One step in an execution plan."""

    step_id: str
    role: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Complete execution plan for a task."""

    pattern: str
    mode: str
    steps: list[PlanStep]
    classification: dict[str, Any]
    intelligence_snapshot: dict[str, Any]
    reasoning: str = ""


PLANNING_PROMPT = """You are a task decomposition planner for ACE, an AI intelligence engine.

Given a task description and its classification, decide how to decompose it into steps.

Available patterns:
- independent: Single agent executes the full task
- pipeline: Sequential specialists, each building on prior output
- adversarial: Multiple agents produce independent positions, then challenge each other, then a synthesizer merges
- fanout: Multiple agents with the same role work in parallel on different aspects

Task: {description}
Classification: {classification}
Intelligence context available: {has_intel}

Respond with JSON:
{{
  "pattern": "independent|pipeline|adversarial|fanout",
  "reasoning": "why this pattern fits",
  "steps": [
    {{
      "step_id": "step_1",
      "role": "researcher|analyst|creator|executor|advisor|sentinel",
      "description": "what this step does",
      "depends_on": []
    }}
  ]
}}

Use the smallest meaningful composition: at most three steps. For a pipeline,
the final step must synthesize the evidence and make the requested decision.
Keep each step description focused enough to produce a concise handoff.
"""


def _json_fallback(obj: Any) -> Any:
    """Render anything the graph hands us into something JSON can carry.

    The old code tried to STRIP unserializable values with a top-level isinstance filter. It could
    not work: classification["recent_decisions"] IS a list, so it passed the filter, and json.dumps
    then died on the TieredDecision dataclasses inside it — taking planning down for every
    deliberative request that had recent decisions to reason with. plan_execution falls back to a
    single step on any failure, so it never announced itself; ACE just quietly got dumber the more
    it knew.

    Converting beats stripping, and that distinction is the point. Dropping the decisions would have
    silenced the crash and STILL lost the context the L5 loader worked to gather — the same bug,
    quieter. The planner is supposed to SEE them.

    Handles dataclasses (TieredDecision), pydantic models, datetimes (a TieredDecision contains one,
    so asdict alone would still have blown up), and falls back to str() — which is always printable
    and always better in a prompt than a missing key.
    """
    from dataclasses import asdict, is_dataclass
    from datetime import date, datetime

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        try:
            return asdict(obj)  # nested datetimes come back through this same fallback
        except Exception:  # pragma: no cover - exotic dataclass; str() is still useful
            return str(obj)
    if hasattr(obj, "model_dump"):  # pydantic
        try:
            return obj.model_dump(mode="json")
        except Exception:  # pragma: no cover
            return str(obj)
    return str(obj)


async def plan_execution(
    description: str,
    classification: dict[str, Any],
    snapshot: dict[str, Any],
    llm=None,
) -> ExecutionPlan:
    """Use LLM to plan task decomposition.

    Falls back to single-step execution on any failure so the system
    never stalls on a planning error.
    """
    _validate_plan_inputs(description, classification)

    if llm is None:
        from core.engine.core.llm import llm as default_llm

        llm = default_llm

    has_intel = "yes" if snapshot.get("insights") else "no"

    prompt = PLANNING_PROMPT.format(
        description=description[:1000],
        classification=json.dumps(classification, default=_json_fallback),
        has_intel=has_intel,
    )

    try:
        from core.engine.core.config import settings

        result = await llm.complete_json(prompt, model=settings.llm_budget_model)

        pattern = result.get("pattern", "independent")
        steps: list[PlanStep] = []
        for s in result.get("steps", []):
            steps.append(
                PlanStep(
                    step_id=s.get("step_id", f"step_{len(steps) + 1}"),
                    role=s.get("role", "executor"),
                    description=s.get("description", ""),
                    depends_on=s.get("depends_on", []),
                    config=s.get("config", {}),
                )
            )

        # Pipeline latency grows linearly and the supported CLI provider has a
        # hard per-call timeout. Preserve a real multi-stage composition while
        # bounding the run: framing, central alternative/critique, synthesis.
        if len(steps) > _MAX_PLAN_STEPS:
            steps = [steps[0], steps[len(steps) // 2], steps[-1]]

        if not steps:
            steps = [PlanStep(step_id="step_1", role="executor", description=description)]

        return ExecutionPlan(
            pattern=pattern,
            mode="deliberative",
            steps=steps,
            classification=classification,
            intelligence_snapshot=snapshot,
            reasoning=result.get("reasoning", ""),
        )
    except Exception as exc:
        logger.warning("LLM planning failed, falling back to single step: %s", exc)
        return ExecutionPlan(
            pattern="independent",
            mode="reactive",
            steps=[
                PlanStep(
                    step_id="step_1",
                    role=classification.get("archetype", "executor"),
                    description=description,
                )
            ],
            classification=classification,
            intelligence_snapshot=snapshot,
            reasoning=f"Planning failed ({exc}), falling back to single-step execution",
        )
