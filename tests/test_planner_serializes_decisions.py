"""The planner crashed the moment ACE had decisions to reason with.

Found by running a real build (not by any test):

    TypeError: Object of type TieredDecision is not JSON serializable
      core/engine/orchestration/planner.py:114  in plan_execution
          classification=json.dumps(_serializable_cls)

The filter above it was meant to prevent exactly this:

    # Strip non-JSON-serializable values (e.g. CognitiveComposition dataclass)
    _serializable_cls = {k: v for k, v in classification.items()
                         if isinstance(v, (str, int, float, bool, list, dict, type(None)))}

...but it only inspects the TOP level. classification["recent_decisions"] IS a list — so it sails
through — and json.dumps then dies on the TieredDecision dataclasses INSIDE it. (Which themselves
contain a datetime, so even asdict() would not have been enough.)

The result: every deliberative request crashed in planning as soon as the L5 loader surfaced any
recent decisions — i.e. precisely when ACE had the most context to reason with. plan_execution
falls back to a single step on any failure, so it never announced itself; it just quietly got
dumber the more it knew. A build failed with "no actions produced — nothing to build", which blamed
the arm for the planner's bug.

The fix must not merely stop the crash. Dropping the decisions would silence the error and STILL
lose the context the loader worked to gather — the same bug, quieter. They have to reach the prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.engine.orchestrator.context import TieredDecision


def _decision(title="Use SurrealDB over Postgres") -> TieredDecision:
    return TieredDecision(
        decision_id="decision:abc",
        title=title,
        rationale="graph-native, one store for graph+documents",
        decision_type="architecture",
        discipline_hint="data",
        affected_capabilities=["capability:storage"],
        created_at=datetime.now(timezone.utc),  # a datetime — json.dumps dies on this too
        tier="recency",
        relevance_score=0.9,
        outcome="accepted",
        status="active",
        affected_capabilities_confidence=None,
    )


class _CapturingLLM:
    """Records the prompt so we can prove the decisions actually REACHED it."""

    def __init__(self):
        self.prompts: list[str] = []

    async def complete_json(self, prompt, **kw):
        self.prompts.append(prompt)
        return {"pattern": "single", "steps": [{"role": "executor", "description": "do it", "depends_on": []}]}

    async def complete(self, prompt, **kw):
        self.prompts.append(prompt)
        return '{"pattern": "single", "steps": []}'


class _FiveStepLLM(_CapturingLLM):
    async def complete_json(self, prompt, **kw):
        self.prompts.append(prompt)
        roles = ["researcher", "creator", "analyst", "sentinel", "advisor"]
        return {
            "pattern": "pipeline",
            "steps": [
                {
                    "step_id": f"step_{index}",
                    "role": role,
                    "description": role,
                    "depends_on": [],
                }
                for index, role in enumerate(roles, start=1)
            ],
        }


@pytest.mark.asyncio
async def test_planning_survives_decisions_nested_inside_a_list():
    """The exact production crash: a list value passes the shallow type filter, and the dataclasses
    inside it blow up json.dumps."""
    from core.engine.orchestration.planner import plan_execution

    llm = _CapturingLLM()
    classification = {
        "discipline": "code",
        "recent_decisions": [_decision(), _decision("Adopt the arm registry")],  # the killer
    }

    plan = await plan_execution("add retry logic", classification, {"insights": []}, llm=llm)

    assert plan is not None, "planning must not die on the context it was given"
    assert llm.prompts, "planning must actually have reached the model, not silently fallen back"


@pytest.mark.asyncio
async def test_the_decisions_actually_reach_the_prompt():
    """Not-crashing is not enough. If we merely DROP the decisions, the planner still loses the
    context the L5 loader gathered — the same bug, just quieter. It has to SEE them."""
    from core.engine.orchestration.planner import plan_execution

    llm = _CapturingLLM()
    classification = {"discipline": "code", "recent_decisions": [_decision("Use SurrealDB over Postgres")]}

    await plan_execution("add retry logic", classification, {"insights": []}, llm=llm)

    prompt = llm.prompts[0]
    assert "SurrealDB over Postgres" in prompt, (
        "the decision must survive into the prompt. Silently dropping it would fix the crash and "
        "keep the intelligence loss — which was the expensive half of the bug."
    )


@pytest.mark.asyncio
async def test_a_genuinely_unserializable_object_still_does_not_crash_planning():
    """The guard must be total. Anything the graph hands us — a dataclass, an object, a datetime —
    must degrade to something printable rather than take the planner down."""
    from core.engine.orchestration.planner import plan_execution

    class _Exotic:
        def __repr__(self):
            return "<exotic>"

    llm = _CapturingLLM()
    classification = {"discipline": "code", "weird": {"nested": [_Exotic()]}, "when": datetime.now(timezone.utc)}

    plan = await plan_execution("do the thing", classification, {"insights": []}, llm=llm)

    assert plan is not None
    assert llm.prompts, "it must still have reached the model"


@pytest.mark.asyncio
async def test_planner_bounds_pipeline_without_dropping_final_synthesizer():
    from core.engine.orchestration.planner import plan_execution

    plan = await plan_execution(
        "make a consequential decision",
        {"discipline": "product_strategy"},
        {"insights": [{"content": "a durable preference"}]},
        llm=_FiveStepLLM(),
    )

    assert [step.role for step in plan.steps] == ["researcher", "analyst", "advisor"]
