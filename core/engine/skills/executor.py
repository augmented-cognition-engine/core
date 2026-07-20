# engine/skills/executor.py
"""Skill executor — run a multi-phase skill as a state machine.

Each phase:
  1. Executes its slots (solo / parallel / adversarial / iterative / pipeline)
  2. Evaluates exit criteria (confidence threshold or evaluator slot)
  3. Routes to next phase via PhaseExit transition rules

Phase patterns supported:
  solo        — single slot, single LLM call
  parallel    — all slots run concurrently, outputs aggregated
  pipeline    — slots run sequentially, each receives prior output
  adversarial — two slots run in parallel, divergence measured, synthesize if needed
  iterative   — slots loop until termination condition (convergence / approval)
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.llm import llm
from core.engine.orchestrator.loader import load_intelligence
from core.engine.skills.models import Phase, PhaseExit, Skill, Slot

logger = logging.getLogger(__name__)

from core.engine.orchestrator.executor import ARCHETYPE_INSTRUCTIONS, MODE_INSTRUCTIONS

# ---------------------------------------------------------------------------
# Model tier resolution
# ---------------------------------------------------------------------------

_TIER_MODELS = {
    "budget": "budget",  # maps to settings.llm_budget_model in _get_model()
    "premium": "premium",
    "default": "default",
}


def _get_model(tier: str, override: str | None = None) -> str:
    if override:
        return settings.llm_budget_model if override == "budget" else settings.llm_model
    if tier == "budget":
        return settings.llm_budget_model
    return settings.llm_model


# ---------------------------------------------------------------------------
# Framework loading (shared by all slot types)
# ---------------------------------------------------------------------------


async def _load_framework_prompts(framework_slugs: list[str], product_id: str) -> str:
    if not framework_slugs:
        return ""
    try:
        async with pool.connection() as db:
            parts = []
            for slug in framework_slugs:
                rows = await db.query(
                    "SELECT name, system_prompt FROM framework WHERE slug = <string>$slug LIMIT 1",
                    {"slug": slug},
                )
                result = rows[0] if rows and isinstance(rows[0], list) else (rows or [])
                if result:
                    fw = result[0]
                    prompt = fw.get("system_prompt") or fw.get("description", "")
                    if prompt:
                        parts.append(f'<framework slug="{slug}">\n{prompt}\n</framework>')
            return "\n".join(parts)
    except Exception as exc:
        logger.warning("Failed to load frameworks %s: %s", framework_slugs, exc)
        return ""


# ---------------------------------------------------------------------------
# Single slot execution
# ---------------------------------------------------------------------------


async def _execute_slot(
    slot: Slot,
    task_description: str,
    product_id: str,
    prior_context: str,
    llm_model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
    slot_label: str = "",
) -> dict:
    """Execute one agent slot. Returns {output, confidence, duration_ms}."""
    start = time.monotonic()

    # Load intelligence — use slot specialties + discipline from classification
    try:
        snapshot = await load_intelligence(
            discipline,
            product_id,
            mode=slot.mode,
            specialties=slot.specialties or None,
            adjacent_disciplines=adjacent_disciplines or None,
        )
    except Exception:
        snapshot = {"insights": [], "total_count": 0}

    # Build intel block
    intel_lines = []
    for ins in snapshot.get("specialty_insights", snapshot.get("insights", []))[:12]:
        intel_lines.append(f"- [{ins.get('confidence', 0):.2f}] {ins.get('content', '')}")
    intel_block = ("\n\n## Intelligence\n" + "\n".join(intel_lines)) if intel_lines else ""

    # Archetype + mode instructions
    arch_inst = ARCHETYPE_INSTRUCTIONS.get(slot.archetype, ARCHETYPE_INSTRUCTIONS.get("executor", ""))
    mode_inst = MODE_INSTRUCTIONS.get(slot.mode, MODE_INSTRUCTIONS.get("reactive", ""))

    # Framework instructions
    fw_block = await _load_framework_prompts(slot.frameworks, product_id)
    if fw_block:
        fw_block = f"\n\n## Reasoning Frameworks\n{fw_block}"

    # Prior context
    prior_block = f"\n\n## Prior Context\n{prior_context}" if prior_context else ""

    # Slot role label
    role_block = f"\n\n## Your Role\n{slot_label}" if slot_label else ""

    prompt = (
        f"{arch_inst}\n{mode_inst}{fw_block}{role_block}"
        f"\n\n## Task\n{task_description}"
        f"{intel_block}{prior_block}"
        "\n\nProvide a thorough response. End with a confidence score (0.0-1.0) "
        "on the last line as: CONFIDENCE: <score>"
    )

    try:
        raw_output = await llm.complete(prompt, model=llm_model)
    except Exception as exc:
        logger.error("Slot %s failed: %s", slot_label or slot.archetype, exc)
        return {
            "output": "",
            "confidence": 0.0,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "error": str(exc),
        }

    # Extract confidence from output
    confidence = 0.7
    lines = raw_output.strip().split("\n")
    if lines and lines[-1].startswith("CONFIDENCE:"):
        try:
            confidence = float(lines[-1].split(":", 1)[1].strip())
            raw_output = "\n".join(lines[:-1]).strip()
        except (ValueError, IndexError):
            pass

    return {
        "output": raw_output,
        "confidence": confidence,
        "duration_ms": int((time.monotonic() - start) * 1000),
    }


# ---------------------------------------------------------------------------
# Phase pattern executors
# ---------------------------------------------------------------------------


async def _run_solo(
    phase: Phase,
    task: str,
    product_id: str,
    context: str,
    model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
) -> dict:
    slot = phase.slots[0]
    result = await _execute_slot(slot, task, product_id, context, model, discipline, adjacent_disciplines)
    return {"output": result["output"], "confidence": result["confidence"], "slot_results": [result]}


async def _run_parallel(
    phase: Phase,
    task: str,
    product_id: str,
    context: str,
    model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
) -> dict:
    tasks = [
        _execute_slot(
            slot,
            task,
            product_id,
            context,
            _get_model(slot.model_tier, model if model == "budget" else None),
            discipline,
            adjacent_disciplines,
        )
        for slot in phase.slots
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    slot_results = []
    outputs = []
    confidences = []
    for r in results:
        if isinstance(r, Exception):
            slot_results.append({"output": "", "confidence": 0.0, "error": str(r)})
        else:
            slot_results.append(r)
            if r.get("output"):
                outputs.append(r["output"])
                confidences.append(r.get("confidence", 0.7))

    if not outputs:
        return {"output": "", "confidence": 0.0, "slot_results": slot_results}

    aggregation = phase.aggregation
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    if aggregation == "last":
        final_output = outputs[-1]
    elif aggregation == "merge":
        final_output = "\n\n---\n\n".join(outputs)
    elif aggregation in ("synthesize", "vote", "rank"):
        # Synthesize with a lightweight LLM call
        synthesis_prompt = (
            f"You are synthesizing outputs from {len(outputs)} parallel agents working on the same task.\n\n"
            f"## Task\n{task}\n\n"
            + "\n\n".join(f"## Agent {i + 1} Output\n{o}" for i, o in enumerate(outputs))
            + "\n\nSynthesize these into a single coherent response. "
            "Preserve the best insights from each. Resolve contradictions explicitly."
        )
        try:
            final_output = await llm.complete(synthesis_prompt, model=model)
        except Exception:
            final_output = outputs[0]
    else:
        final_output = outputs[0]

    return {"output": final_output, "confidence": avg_confidence, "slot_results": slot_results}


async def _run_pipeline(
    phase: Phase,
    task: str,
    product_id: str,
    context: str,
    model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
) -> dict:
    accumulated = context
    last_result: dict = {}
    slot_results = []

    for slot in phase.slots:
        result = await _execute_slot(
            slot, task, product_id, accumulated, _get_model(slot.model_tier), discipline, adjacent_disciplines
        )
        slot_results.append(result)
        if result.get("output"):
            accumulated += f"\n\n{result['output']}"
        last_result = result

    return {
        "output": last_result.get("output", ""),
        "confidence": last_result.get("confidence", 0.7),
        "slot_results": slot_results,
    }


async def _run_adversarial(
    phase: Phase,
    task: str,
    product_id: str,
    context: str,
    model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
) -> dict:
    """Generator vs critic. Measure divergence; synthesize only if they disagree."""
    if len(phase.slots) < 2:
        return await _run_solo(phase, task, product_id, context, model, discipline, adjacent_disciplines)

    generator_slot, critic_slot = phase.slots[0], phase.slots[1]

    gen_result, crit_result = await asyncio.gather(
        _execute_slot(
            generator_slot, task, product_id, context, model, discipline, adjacent_disciplines, slot_label="generator"
        ),
        _execute_slot(
            critic_slot, task, product_id, context, model, discipline, adjacent_disciplines, slot_label="critic"
        ),
    )

    gen_out = gen_result.get("output", "")
    crit_out = crit_result.get("output", "")

    # Measure divergence via simple token overlap
    from difflib import SequenceMatcher

    similarity = SequenceMatcher(None, gen_out[:500], crit_out[:500]).ratio()
    divergence = 1.0 - similarity

    if divergence < 0.3:
        # Outputs substantially agree — skip synthesis
        return {
            "output": gen_out,
            "confidence": max(gen_result.get("confidence", 0.7), crit_result.get("confidence", 0.7)),
            "slot_results": [gen_result, crit_result],
            "divergence": divergence,
            "synthesis_skipped": True,
        }

    # Synthesize
    synthesis_prompt = (
        f"Two agents analyzed the same task and reached different conclusions.\n\n"
        f"## Task\n{task}\n\n"
        f"## Generator Output\n{gen_out}\n\n"
        f"## Critic Output\n{crit_out}\n\n"
        "Synthesize these into a single response. Explicitly address where they diverge. "
        "Adopt the critic's corrections where valid. Preserve the generator's strengths."
    )
    try:
        synthesized = await llm.complete(synthesis_prompt, model=model)
    except Exception:
        synthesized = gen_out

    avg_conf = (gen_result.get("confidence", 0.7) + crit_result.get("confidence", 0.7)) / 2
    return {
        "output": synthesized,
        "confidence": avg_conf,
        "slot_results": [gen_result, crit_result],
        "divergence": divergence,
        "synthesis_skipped": False,
    }


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------


_PATTERN_RUNNERS = {
    "solo": _run_solo,
    "parallel": _run_parallel,
    "pipeline": _run_pipeline,
    "adversarial": _run_adversarial,
}


async def _execute_phase(
    phase: Phase,
    task: str,
    product_id: str,
    accumulated_context: str,
    model: str,
    discipline: str = "architecture",
    adjacent_disciplines: list[str] | None = None,
) -> dict:
    """Dispatch a phase to the appropriate pattern runner."""
    start = time.monotonic()

    if not phase.slots:
        return {"output": "", "confidence": 0.0, "duration_ms": 0}

    runner = _PATTERN_RUNNERS.get(phase.pattern, _run_solo)
    result = await runner(phase, task, product_id, accumulated_context, model, discipline, adjacent_disciplines)

    result["phase"] = phase.name
    result["pattern"] = phase.pattern
    result["duration_ms"] = int((time.monotonic() - start) * 1000)

    # Run evaluator slot if present
    if phase.evaluator and result.get("output"):
        eval_result = await _execute_slot(
            phase.evaluator,
            f"Evaluate this output for the task: {task}\n\nOutput to evaluate:\n{result['output']}",
            product_id,
            "",
            model,
            discipline,
            adjacent_disciplines,
            slot_label="evaluator",
        )
        result["evaluator_output"] = eval_result.get("output", "")
        # Evaluator confidence overrides phase confidence
        result["confidence"] = eval_result.get("confidence", result.get("confidence", 0.7))

    return result


# ---------------------------------------------------------------------------
# State machine — resolve phase transitions
# ---------------------------------------------------------------------------


def _resolve_next_phase(
    target: str,
    phase_map: dict[str, int],
    current_idx: int,
    total: int,
) -> int | None:
    """Return the index of the next phase, or None if done/abort."""
    if target == "next":
        next_idx = current_idx + 1
        return next_idx if next_idx < total else None
    if target == "done":
        return None
    if target == "abort":
        return None
    if target.startswith("jump:"):
        name = target[5:]
        return phase_map.get(name, current_idx + 1)
    if target == "loop":
        return current_idx
    if target == "escalate":
        return current_idx  # caller handles model upgrade
    if target == "request_context":
        return None  # pause; caller surfaces question
    return current_idx + 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


_SKILL_CONFIDENCE_THRESHOLD = 0.6


async def execute_skill(
    skill: Skill,
    task_description: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
    model: str | None = None,
    classification: dict | None = None,
) -> dict:
    """Execute a skill as a state machine of phases.

    Each phase executes its slots, evaluates exit criteria, and routes
    to the next phase based on PhaseExit transition rules.

    Args:
        classification: Optional classifier output. When provided, discipline
            and confidence are used for intelligence loading and adjacency fallback.

    Returns:
        {output, skill_slug, phase_results, phases_completed, total_duration_ms,
         termination_reason}
    """
    phases = skill.phases  # model_validator already migrated jobs → phases
    if not phases:
        return {
            "output": "",
            "skill_slug": skill.slug,
            "phase_results": [],
            "phases_completed": 0,
            "total_duration_ms": 0,
            "termination_reason": "no_phases",
        }

    # Resolve discipline: classification > skill definition > fallback
    cls = classification or {}
    discipline = cls.get("discipline") or skill.effective_discipline or "architecture"
    discipline_confidence = cls.get("discipline_confidence", 1.0)

    # Adjacent discipline fallback when confidence is low
    adjacent: list[str] = []
    if discipline_confidence < _SKILL_CONFIDENCE_THRESHOLD:
        from core.engine.intelligence.adjacency import get_adjacent_disciplines

        adjacent = get_adjacent_disciplines(discipline, max_n=2)
        if adjacent:
            logger.info(
                "Skill %s: low discipline confidence (%.2f) for '%s' — loading adjacent: %s",
                skill.slug,
                discipline_confidence,
                discipline,
                adjacent,
            )

    llm_model = settings.llm_budget_model if model == "budget" else settings.llm_model
    phase_map = {p.name: i for i, p in enumerate(phases)}

    phase_results: list[dict] = []
    accumulated_context = ""
    current_idx = 0
    attempts: dict[str, int] = {}
    termination_reason = "completed"
    total_start = time.monotonic()

    try:
        while 0 <= current_idx < len(phases):
            phase = phases[current_idx]
            attempt_num = attempts.get(phase.name, 0) + 1
            attempts[phase.name] = attempt_num

            # Execute the phase
            phase_result = await _execute_phase(
                phase, task_description, product_id, accumulated_context, llm_model, discipline, adjacent or None
            )
            phase_result["attempt"] = attempt_num
            phase_results.append(phase_result)

            output = phase_result.get("output", "")
            confidence = phase_result.get("confidence", 0.7)

            if output:
                accumulated_context += f"\n\n### Phase: {phase.name}\n{output}"

            # Evaluate exit condition
            exit_rules: PhaseExit = phase.exit
            success = confidence >= exit_rules.confidence_threshold

            if success:
                target = exit_rules.on_success
            elif attempt_num < exit_rules.max_attempts:
                # Retry same phase (implicit loop up to max_attempts)
                logger.info(
                    "Phase %s attempt %d/%d failed (conf=%.2f), retrying",
                    phase.name,
                    attempt_num,
                    exit_rules.max_attempts,
                    confidence,
                )
                continue
            else:
                target = exit_rules.on_failure
                logger.info("Phase %s exhausted %d attempts, routing: %s", phase.name, attempt_num, target)

            # Handle escalation: upgrade model and retry from scratch
            if target == "escalate":
                if exit_rules.escalation_tier:
                    llm_model = _get_model(exit_rules.escalation_tier)
                attempts[phase.name] = 0  # reset counter after escalation
                continue

            # Handle explicit infinite-loop retry (on_failure="loop" means keep trying)
            if target == "loop":
                attempts[phase.name] = 0  # reset so max_attempts check doesn't block it
                continue

            # Handle request_context: surface as termination
            if target == "request_context":
                termination_reason = "request_context"
                break

            if target == "abort":
                termination_reason = "aborted"
                break

            next_idx = _resolve_next_phase(target, phase_map, current_idx, len(phases))
            if next_idx is None:
                termination_reason = "done" if target == "done" else "aborted"
                break
            current_idx = next_idx

    except Exception as exc:
        logger.error(
            "execute_skill(%s) failed at phase %d/%d: %s",
            skill.slug,
            current_idx,
            len(phases),
            exc,
            exc_info=True,
        )
        return {
            "output": "",
            "skill_slug": skill.slug,
            "phase_results": phase_results,
            "phases_completed": len({r["phase"] for r in phase_results if r.get("output")}),
            "total_phases": len(phases),
            "total_duration_ms": int((time.monotonic() - total_start) * 1000),
            "termination_reason": "error",
            "error": str(exc),
        }

    # Final output = last completed phase with output
    final_output = ""
    for r in reversed(phase_results):
        if r.get("output"):
            final_output = r["output"]
            break

    phases_completed = len({r["phase"] for r in phase_results if r.get("output")})

    return {
        "output": final_output,
        "skill_slug": skill.slug,
        "phase_results": phase_results,
        "phases_completed": phases_completed,
        "total_phases": len(phases),
        "total_duration_ms": int((time.monotonic() - total_start) * 1000),
        "termination_reason": termination_reason,
    }
