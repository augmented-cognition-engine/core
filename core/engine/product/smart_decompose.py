# engine/product/smart_decompose.py
"""Smart Decomposer — break specs into agent-optimized work units.

Given a spec, produces a DAG of work units with:
- Parallel groups (units that can run simultaneously)
- Dependencies (A must finish before B)
- Agent config per unit (archetype, mode)
- Predicted file conflicts between units
"""

import logging
from datetime import datetime, timezone

from core.engine.core.db import parse_one
from core.engine.core.exceptions import DecompositionError, ValidationError
from core.engine.core.llm import get_llm
from core.engine.orchestration.dispatch_planner import DispatchSchedule, plan_dispatch

logger = logging.getLogger(__name__)


async def _write_rejection_traces(
    pool,
    product_id: str,
    spec_id: str,
    traces: list[dict],
) -> None:
    """Write rejected decomposition alternatives to failure_memory.

    Non-fatal: any DB error is silently swallowed.
    Only writes when traces is non-empty.
    """
    if not traces:
        return
    for trace in traces:
        try:
            async with pool.connection() as db:
                await db.query(
                    "CREATE failure_memory CONTENT $data",
                    {
                        "data": {
                            "product": product_id,
                            "discipline": "decomposition",
                            "spec_id": spec_id,
                            "type": "decomposition_rejection",
                            "summary": trace.get("summary", ""),
                            "reason": trace.get("reason", ""),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
        except Exception:
            pass  # Non-fatal


ARCHETYPES = {"creator", "analyst", "sentinel", "researcher"}
MODES = {"deliberative", "reactive", "exploratory", "procedural"}


class WorkUnit:
    """A single unit of work in a decomposition plan."""

    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        files_create: list[str] = None,
        files_modify: list[str] = None,
        depends_on: list[str] = None,
        archetype: str = "creator",
        mode: str = "deliberative",
        reasoning: str = "",
    ):
        self.id = id
        self.title = title
        self.description = description
        self.files_create = files_create or []
        self.files_modify = files_modify or []
        self.depends_on = depends_on or []
        self.archetype = archetype
        self.mode = mode
        self.reasoning = reasoning

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "files_create": self.files_create,
            "files_modify": self.files_modify,
            "depends_on": self.depends_on,
            "archetype": self.archetype,
            "mode": self.mode,
            "reasoning": self.reasoning,
        }


class DecompositionPlan:
    """Result of decomposing a spec into work units."""

    def __init__(self, spec_id: str, units: list[WorkUnit], schedule: DispatchSchedule, airspace=None):
        self.spec_id = spec_id
        self.units = units
        self.schedule = schedule
        self.airspace = airspace  # dict[str, AirspaceAssignment] | None

    def to_dict(self) -> dict:
        result = {
            "spec_id": self.spec_id,
            "units": [u.to_dict() for u in self.units],
            "batches": [{"task_ids": b.task_ids, "mode": b.mode, "reason": b.reason} for b in self.schedule.batches],
            "conflicts": self.schedule.conflicts,
            "total_units": len(self.units),
            "parallel_groups": sum(1 for b in self.schedule.batches if b.mode == "parallel"),
        }
        if self.airspace:
            result["airspace"] = {
                uid: {
                    "owned_files": sorted(a.owned_files),
                    "boundary_files": sorted(a.boundary_files),
                    "capability_slugs": a.capability_slugs,
                    "source": a.source,
                }
                for uid, a in self.airspace.items()
            }
        return result


class SmartDecomposer:
    """Decompose specs into agent-optimized work units."""

    def __init__(
        self,
        db_pool,
        plan_evaluator=None,
        branch_count: int = 3,
    ):
        self._pool = db_pool
        self._llm = get_llm()
        self._plan_evaluator = plan_evaluator
        self._branch_count = branch_count

    def _validate_decompose_inputs(self, spec_id: str, product_id: str) -> None:
        """Validate decomposition inputs before loading spec from DB.

        Raises DecompositionError for empty spec_id and ValidationError for
        malformed product_id, so the orchestrator gets a clear error rather
        than a confusing DB miss.
        """
        if not spec_id or not spec_id.strip():
            raise DecompositionError("spec_id must be non-empty")
        if not product_id or ":" not in product_id:
            raise ValidationError(f"Invalid product_id: {product_id!r}")

    async def decompose(self, spec_id: str, product_id: str) -> DecompositionPlan:
        """Decompose a spec into a DAG of work units.

        1. Load the spec
        2. LLM decomposes into work units with file predictions
        3. Run dispatch_planner to determine parallel vs sequential
        4. Assign agent archetype/mode per unit
        5. Return DecompositionPlan
        """
        self._validate_decompose_inputs(spec_id, product_id)
        # Load spec
        async with self._pool.connection() as db:
            spec_result = await db.query(
                "SELECT * FROM <record>$spec_id",
                {"spec_id": spec_id},
            )
            spec = parse_one(spec_result)

        if not spec:
            raise DecompositionError(f"Spec {spec_id} not found")

        logger.info("Decomposing spec=%s product=%s", spec_id, product_id)

        # LLM decomposes
        if self._plan_evaluator is not None:
            units, rejection_traces = await self._decompose_best_of_n(spec)
        else:
            units, rejection_traces = await self._llm_decompose(spec)
        await _write_rejection_traces(self._pool, product_id, spec_id, rejection_traces)

        # Run conflict-aware scheduling
        task_dicts = [
            {
                "id": u.id,
                "files_create": u.files_create,
                "files_modify": u.files_modify,
                "depends_on": u.depends_on,
            }
            for u in units
        ]
        schedule = plan_dispatch(task_dicts)

        logger.info(
            "Decomposed spec=%s into %d units, %d batches, %d conflicts",
            spec_id,
            len(units),
            len(schedule.batches),
            len(schedule.conflicts),
        )
        return DecompositionPlan(spec_id=spec_id, units=units, schedule=schedule)

    async def _llm_decompose(self, spec: dict) -> tuple[list[WorkUnit], list[dict]]:
        """LLM breaks spec into work units. Returns (units, rejection_traces).

        Prompt requests {chosen: [...], rejected: [...]} format.
        Falls back gracefully if LLM returns a plain list (backward compat).
        """
        objective = spec.get("objective", "")
        criteria = spec.get("acceptance_criteria", [])
        files = spec.get("estimated_files", [])
        constraints = spec.get("constraints", [])

        criteria_text = "\n".join(f"- {c.get('criterion', c) if isinstance(c, dict) else c}" for c in criteria)
        files_text = "\n".join(f"- {f}" for f in files) if files else "(none specified)"
        constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "(none)"

        prompt = f"""Decompose this spec into 2-6 work units that agents can execute.

OBJECTIVE: {objective}

ACCEPTANCE CRITERIA:
{criteria_text}

ESTIMATED FILES:
{files_text}

CONSTRAINTS:
{constraints_text}

For each work unit, provide:
- id: "unit-1", "unit-2", etc.
- title: short title
- description: what to do (2-3 sentences, specific enough for an agent)
- files_create: files this unit creates (array of strings)
- files_modify: files this unit modifies (array of strings)
- depends_on: array of unit IDs this depends on (empty if independent)
- archetype: "creator" (build code), "analyst" (review/assess), "sentinel" (test/verify), "researcher" (investigate)
- mode: "deliberative" (careful planning), "procedural" (follow steps), "reactive" (quick fix)
- reasoning: one sentence explaining why you chose this archetype + mode for THIS task

Group related work. Tests should be separate units from implementation.
Minimize dependencies — maximize what can run in parallel.

Before finalizing, consider 1-2 alternative approaches you rejected and why.

Return JSON with this structure:
{{
  "chosen": [<work_units array>],
  "rejected": [
    {{"summary": "one-line description of rejected approach", "reason": "why rejected in one sentence"}},
    ...
  ]
}}"""

        result = await self._llm.complete_json(prompt)

        # Parse chosen units — fall back to raw list if LLM ignores format
        if isinstance(result, list):
            raw_units = result
            rejection_traces: list[dict] = []
        else:
            raw_units = result.get("chosen", result.get("units", result.get("work_units", [])))
            rejection_traces = [r for r in result.get("rejected", []) if isinstance(r, dict) and r.get("summary")]

        units = []
        for raw in raw_units:
            if not isinstance(raw, dict):
                continue
            units.append(
                WorkUnit(
                    id=raw.get("id", f"unit-{len(units) + 1}"),
                    title=raw.get("title", "Untitled"),
                    description=raw.get("description", ""),
                    files_create=raw.get("files_create", []),
                    files_modify=raw.get("files_modify", []),
                    depends_on=raw.get("depends_on", []),
                    archetype=raw.get("archetype", "creator") if raw.get("archetype") in ARCHETYPES else "creator",
                    mode=raw.get("mode", "deliberative") if raw.get("mode") in MODES else "deliberative",
                    reasoning=raw.get("reasoning", ""),
                )
            )

        return units, rejection_traces

    async def _decompose_best_of_n(self, spec: dict) -> tuple[list[WorkUnit], list[dict]]:
        """Generate branch_count candidate plans, return the highest-scoring one.

        All rejection traces from all candidates are merged.
        Falls back to a single call if all branches fail.
        """
        all_traces: list[dict] = []
        candidates: list[tuple[list[WorkUnit], float]] = []

        for _ in range(self._branch_count):
            try:
                units, traces = await self._llm_decompose(spec)
                all_traces.extend(traces)
                score = await self._plan_evaluator.evaluate(spec, units)
                candidates.append((units, score))
            except Exception:
                pass  # Skip failed branches — non-fatal

        if not candidates:
            logger.warning(
                "All %d branches failed in _decompose_best_of_n; falling back to single call",
                self._branch_count,
            )
            units, traces = await self._llm_decompose(spec)
            all_traces.extend(traces)
            return units, all_traces

        best_units = max(candidates, key=lambda c: c[1])[0]
        return best_units, all_traces

    async def replan(self, spec_id: str, feedback: dict, product_id: str) -> DecompositionPlan:
        """Re-decompose incorporating feedback context (blockers, staleness, changes).

        Loads the original spec, appends feedback context to the LLM prompt
        so the new plan accounts for what changed or what went wrong.
        """
        self._validate_decompose_inputs(spec_id, product_id)
        # Load spec
        async with self._pool.connection() as db:
            spec_result = await db.query(
                "SELECT * FROM <record>$spec_id",
                {"spec_id": spec_id},
            )
            spec = parse_one(spec_result)

        if not spec:
            raise DecompositionError(f"Spec {spec_id} not found for replan")

        logger.info("Replanning spec=%s reason=%r product=%s", spec_id, feedback.get("reason"), product_id)

        # Enrich spec with feedback context for the LLM
        feedback_context = []
        if feedback.get("stale"):
            feedback_context.append(
                f"WARNING: The following files were modified since the original plan: "
                f"{', '.join(feedback.get('overlapping_files', []))}. "
                f"Your new plan must account for these changes."
            )
        if feedback.get("reason"):
            feedback_context.append(f"Replan reason: {feedback['reason']}")
        if feedback.get("blocker_content"):
            feedback_context.append(
                f"Agent reported blocker: {feedback['blocker_content']}. Find an alternative approach."
            )

        if feedback_context:
            spec = dict(spec)  # copy
            existing_constraints = spec.get("constraints") or []
            spec["constraints"] = existing_constraints + feedback_context

        # Re-decompose with enriched context
        units, rejection_traces = (
            await self._decompose_best_of_n(spec)
            if self._plan_evaluator is not None
            else await self._llm_decompose(spec)
        )
        await _write_rejection_traces(self._pool, product_id, spec_id, rejection_traces)

        task_dicts = [
            {
                "id": u.id,
                "files_create": u.files_create,
                "files_modify": u.files_modify,
                "depends_on": u.depends_on,
            }
            for u in units
        ]
        schedule = plan_dispatch(task_dicts)

        logger.info(
            "Replan complete: spec=%s units=%d batches=%d",
            spec_id,
            len(units),
            len(schedule.batches),
        )
        return DecompositionPlan(spec_id=spec_id, units=units, schedule=schedule)
