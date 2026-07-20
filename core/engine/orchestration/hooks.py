# engine/orchestration/hooks.py
"""Post-task hook registry.

Extracts the inline post-task hooks from engine/orchestrator/executor.py
into a composable registry.  Each hook receives a HookContext and runs
best-effort (failures are logged, never bubbled).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PostTaskHook = Callable[["HookContext"], Awaitable[None]]


@dataclass
class HookContext:
    """Context passed to each post-task hook."""

    task_id: str
    product_id: str
    domain_path: str
    output: str
    snapshot: dict[str, Any]  # intelligence_loaded
    classification: dict[str, Any]
    # --- Added for composition memory ---
    frameworks_used: list[str] = field(default_factory=list)
    engagement_result: dict[str, Any] | None = None
    token_accumulator: Any | None = None  # TokenAccumulator, Any to avoid circular import
    # --- Added for routing feedback loop ---
    phase_traces: list[dict] = field(default_factory=list)  # from MultiPhaseExecutor._last_trace
    # --- Added for compounding metric ---
    task_description: str = ""
    started_at: float | None = None  # time.time() at task start


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_hooks: list[tuple[str, PostTaskHook]] = []


def register_hook(name: str, hook: PostTaskHook) -> None:
    """Register a post-task hook by name."""
    _hooks.append((name, hook))


def get_hooks() -> list[tuple[str, PostTaskHook]]:
    """Return all registered hooks."""
    return list(_hooks)


async def run_hooks(context: HookContext, event_bus=None) -> None:
    """Run all registered hooks. Each hook is best-effort (logs warnings on failure)."""
    for name, hook in _hooks:
        try:
            if event_bus:
                from core.engine.orchestration.events import HookStarted

                await event_bus.emit(
                    HookStarted(
                        run_id=context.task_id,
                        product_id=context.product_id,
                        hook_name=name,
                    )
                )
            await hook(context)
            if event_bus:
                from core.engine.orchestration.events import HookCompleted

                await event_bus.emit(
                    HookCompleted(
                        run_id=context.task_id,
                        product_id=context.product_id,
                        hook_name=name,
                        result_summary="ok",
                    )
                )
        except Exception as exc:
            logger.warning("Post-task hook '%s' failed: %s", name, exc)


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


async def cooccurrence_hook(ctx: HookContext) -> None:
    """Track co-occurrence for the synaptic graph."""
    from core.engine.graph.cooccurrence import track as track_cooccurrence

    task_for_tracking = {
        "domain_path": ctx.domain_path,
        "intelligence_loaded": ctx.snapshot,
    }
    await track_cooccurrence(task_for_tracking, ctx.product_id)


async def utilization_and_roi_hook(ctx: HookContext) -> None:
    """Detect ROI events from task output."""
    from core.engine.core.db import pool
    from core.engine.intelligence.roi_detector import detect_roi_events

    async with pool.connection() as db:
        task_for_roi = {
            "id": ctx.task_id,
            "domain_path": ctx.domain_path,
            "intelligence_loaded": ctx.snapshot,
        }
        utilization = ctx.snapshot.get("intelligence_utilization", {})
        await detect_roi_events(task_for_roi, utilization, ctx.product_id, db)


async def calibration_hook(ctx: HookContext) -> None:
    """Apply calibrated assessment if calibration data exists."""
    from core.engine.core.db import parse_one, pool
    from core.engine.intelligence.calibration import apply_calibration

    async with pool.connection() as db:
        task_row = parse_one(
            await db.query(
                "SELECT self_assessment FROM <record>$tid",
                {"tid": ctx.task_id},
            )
        )
        raw_confidence = (task_row or {}).get("self_assessment", 0.7)

        cal_result = await db.query(
            "SELECT data FROM calibration WHERE product = <record>$product LIMIT 1",
            {"product": ctx.product_id},
        )
        cal_row = parse_one(cal_result)
        if cal_row and cal_row.get("data"):
            adjusted = apply_calibration(raw_confidence, ctx.domain_path, cal_row["data"])
            await db.query(
                "UPDATE <record>$tid SET calibrated_assessment = $cal",
                {"tid": ctx.task_id, "cal": adjusted},
            )


# Module-level imports for composition_signal_hook (required for test patching)
from core.engine.core.db import pool  # noqa: E402
from core.engine.core.model_costs import alternative_model_for, cost_for_call  # noqa: E402
from core.engine.intelligence.token_baseline import estimate_baseline  # noqa: E402


def _outcome_confidence_from_traces(phase_traces: list[dict]) -> float | None:
    """Compute mean confidence from non-tainted phase traces.

    Returns None if no traces or all phases are tainted (execution failure).
    Used as a proxy for routing quality: low confidence = possible routing miss.
    """
    if not phase_traces:
        return None
    valid = [t["confidence"] for t in phase_traces if not t.get("tainted", False) and t.get("confidence")]
    if not valid:
        return None
    return sum(valid) / len(valid)


async def composition_signal_hook(ctx: HookContext) -> None:
    """Write composition signal record with full tuple + token usage + routing quality."""
    classification = ctx.classification
    engagement = classification.get("engagement", {})
    perspectives = engagement.get("perspectives", [classification.get("perspective", "practitioner")])
    discipline = classification.get("discipline", classification.get("domain_path", ""))
    complexity = classification.get("complexity", "moderate")

    # Token data from accumulator
    acc = ctx.token_accumulator
    token_input = acc.total_input() if acc else 0
    token_output = acc.total_output() if acc else 0
    token_total = acc.total() if acc else 0

    # Engagement data
    eng = ctx.engagement_result or {}
    spin_count = eng.get("spin_count", len(perspectives))
    adversarial_diversity = eng.get("adversarial_diversity")

    # Utilization from task record (may be None)
    util = ctx.snapshot.get("intelligence_utilization", {})
    utilization_rate = util.get("utilization_rate") if util else None

    # Baseline estimate for savings
    baseline = await estimate_baseline(discipline, complexity, ctx.product_id)
    token_delta = (baseline - token_total) if baseline is not None else None
    estimated_saved = max(0, token_delta) if token_delta is not None else None

    # Perspective weights (from scored composition stored on classification)
    perspective_weights = classification.get("perspective_weights", {p: 1.0 for p in perspectives})

    # Routing quality signals — these feed the learning loop
    outcome_confidence = _outcome_confidence_from_traces(ctx.phase_traces)
    discipline_confidence = classification.get("discipline_confidence")
    mode_confidence = classification.get("mode_confidence")
    archetype_confidence = classification.get("archetype_confidence")
    # Flag: classifier was uncertain about this routing (mode_confidence < 0.5)
    routing_uncertain = bool(mode_confidence is not None and mode_confidence < 0.5)

    if routing_uncertain:
        logger.info(
            "composition_signal: low mode_confidence=%.2f for %s/%s — routing may be unreliable",
            mode_confidence,
            discipline,
            classification.get("mode", ""),
        )

    # --- Cost-aware fields (Phase A §F) ---
    model_used = getattr(ctx, "model_used", None) or classification.get("model")
    call_count_used = getattr(ctx, "call_count_used", None)
    call_budget_estimated = getattr(ctx, "call_budget_estimated", None)
    budget_estimated = classification.get("token_budget")
    budget_used = token_output  # output tokens are the budget consumer
    if model_used:
        cost_usd = cost_for_call(model_used, token_input, token_output)
        alt_model = alternative_model_for(model_used)
        estimated_alternative_cost_usd = cost_for_call(alt_model, token_input, token_output) if alt_model else None
    else:
        cost_usd = None
        estimated_alternative_cost_usd = None
    # Overthinking: long-chain output AND running on a model whose alternative
    # would have been cheaper in total. Both conditions must hold.
    overthinking_flag = False
    if token_input > 0 and token_output > 0 and cost_usd is not None and estimated_alternative_cost_usd is not None:
        ratio = token_output / token_input
        if ratio > 5.0 and cost_usd > estimated_alternative_cost_usd:
            overthinking_flag = True

    async with pool.connection() as db:
        await db.query(
            """
            CREATE composition_signal SET
                task_id = <record>$task_id,
                discipline = $discipline,
                perspectives = $perspectives,
                perspective_weights = $perspective_weights,
                engagement_type = $engagement_type,
                archetype = $archetype,
                mode = $mode,
                complexity = $complexity,
                specialties_loaded = $specialties_loaded,
                frameworks_used = $frameworks_used,
                skill_used = $skill_used,
                utilization_rate = $utilization_rate,
                spin_count = $spin_count,
                adversarial_diversity = $adversarial_diversity,
                token_input = $token_input,
                token_output = $token_output,
                token_total = $token_total,
                token_delta = $token_delta,
                estimated_tokens_saved = $estimated_saved,
                outcome_confidence = $outcome_confidence,
                discipline_confidence = $discipline_confidence,
                mode_confidence = $mode_confidence,
                archetype_confidence = $archetype_confidence,
                routing_uncertain = $routing_uncertain,
                model_used = $model_used,
                budget_estimated = $budget_estimated,
                budget_used = $budget_used,
                call_budget_estimated = $call_budget_estimated,
                call_count_used = $call_count_used,
                cost_usd = $cost_usd,
                estimated_alternative_cost_usd = $estimated_alternative_cost_usd,
                overthinking_flag = $overthinking_flag
            """,
            {
                "product": ctx.product_id,
                "task_id": ctx.task_id,
                "discipline": discipline,
                "perspectives": perspectives,
                "perspective_weights": perspective_weights,
                "engagement_type": eng.get("engagement_type", "single"),
                "archetype": classification.get("archetype", ""),
                "mode": classification.get("mode", ""),
                "complexity": complexity,
                "specialties_loaded": classification.get("specialties", []),
                "frameworks_used": ctx.frameworks_used or [],
                "skill_used": classification.get("skill_used"),
                "utilization_rate": utilization_rate,
                "spin_count": spin_count,
                "adversarial_diversity": adversarial_diversity,
                "token_input": token_input,
                "token_output": token_output,
                "token_total": token_total,
                "token_delta": token_delta,
                "estimated_saved": estimated_saved,
                "outcome_confidence": outcome_confidence,
                "discipline_confidence": discipline_confidence,
                "mode_confidence": mode_confidence,
                "archetype_confidence": archetype_confidence,
                "routing_uncertain": routing_uncertain,
                "model_used": model_used,
                "budget_estimated": budget_estimated,
                "budget_used": budget_used,
                "call_budget_estimated": call_budget_estimated,
                "call_count_used": call_count_used,
                "cost_usd": cost_usd,
                "estimated_alternative_cost_usd": estimated_alternative_cost_usd,
                "overthinking_flag": overthinking_flag,
            },
        )

        # Write instrument_perf records for each active phase (feeds FrameworkClassifier)
        composition = classification.get("cognitive_composition")
        if composition and composition.active_phases:
            discipline = classification.get("discipline", classification.get("domain_path", ""))
            task_type = classification.get("task_type", "")
            meta_skills = composition.meta_skills

            for i, phase in enumerate(composition.active_phases):
                phase_slugs = composition.resolved_instruments.get(str(i), [])
                for slug in phase_slugs:
                    for meta_skill in meta_skills[:1]:  # primary meta-skill only
                        try:
                            await db.query(
                                """
                                CREATE instrument_perf SET
                                    product = <record>$product,
                                    meta_skill = $meta_skill,
                                    phase = $phase,
                                    cognitive_function = $cognitive_function,
                                    framework_slug = $framework_slug,
                                    task_type = $task_type,
                                    discipline = $discipline,
                                    outcome_score = $outcome_score,
                                    created_at = time::now()
                                """,
                                {
                                    "product": ctx.product_id,
                                    "meta_skill": meta_skill,
                                    "phase": i,
                                    "cognitive_function": phase.cognitive_function,
                                    "framework_slug": slug,
                                    "task_type": task_type,
                                    "discipline": discipline,
                                    # outcome_confidence (mean of non-tainted phase
                                    # confidences) is the learning signal; None for
                                    # shallow/all-tainted runs leaves the row unscored.
                                    "outcome_score": outcome_confidence,
                                },
                            )
                        except Exception as exc:
                            logger.debug("instrument_perf write failed (non-fatal): %s", exc)

            # Write tool_perf records for each active phase (feeds ToolClassifier).
            # Parallel to instrument_perf: advisory tools surfaced for a cognitive
            # step, scored by the same outcome_confidence signal.
            for i, phase in enumerate(composition.active_phases):
                phase_tools = getattr(composition, "resolved_tools", {}).get(str(i), [])
                for tool_slug in phase_tools:
                    for meta_skill in meta_skills[:1]:  # primary meta-skill only
                        try:
                            await db.query(
                                """
                                CREATE tool_perf SET
                                    product = <record>$product,
                                    meta_skill = $meta_skill,
                                    phase = $phase,
                                    cognitive_function = $cognitive_function,
                                    tool_slug = $tool_slug,
                                    task_type = $task_type,
                                    discipline = $discipline,
                                    outcome_score = $outcome_score,
                                    created_at = time::now()
                                """,
                                {
                                    "product": ctx.product_id,
                                    "meta_skill": meta_skill,
                                    "phase": i,
                                    "cognitive_function": phase.cognitive_function,
                                    "tool_slug": tool_slug,
                                    "task_type": task_type,
                                    "discipline": discipline,
                                    "outcome_score": outcome_confidence,
                                },
                            )
                        except Exception as exc:
                            logger.debug("tool_perf write failed (non-fatal): %s", exc)


async def compounding_hook(ctx: HookContext) -> None:
    """Record this task's duration + token cost keyed by (discipline, class_hash).

    Makes the compounding claim measurable: recurring task classes should
    trend toward lower duration_ms / token_total over time as intelligence
    accumulates. Non-fatal on any failure — purely observational.
    """
    import time as _time

    from core.engine.intelligence.compounding import record_task_duration

    if not ctx.started_at or not ctx.task_description:
        return
    duration_ms = int((_time.time() - ctx.started_at) * 1000)
    token_total = ctx.token_accumulator.total() if ctx.token_accumulator else 0
    discipline = ctx.classification.get("discipline", ctx.classification.get("domain_path", ""))

    try:
        async with pool.connection() as db:
            await record_task_duration(
                db=db,
                product_id=ctx.product_id,
                description=ctx.task_description,
                discipline=discipline or "",
                duration_ms=duration_ms,
                token_total=token_total,
            )
    except Exception as exc:
        logger.debug("compounding_hook write failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Register built-in hooks at module load time
# ---------------------------------------------------------------------------

register_hook("cooccurrence", cooccurrence_hook)
register_hook("utilization_and_roi", utilization_and_roi_hook)
register_hook("calibration", calibration_hook)
# composition_signal MUST run after utilization_and_roi (reads utilization data)
register_hook("composition_signal", composition_signal_hook)
register_hook("compounding", compounding_hook)
