"""Reusable streamed multi-phase reasoning entrypoint.

Models the assembly in engine/orchestration/executor.py (fetch framework prompts
-> llm_call -> MultiPhaseExecutor.execute) as a standalone, streaming-capable
call the canvas can use. Deep compositions run the real phase pipeline (emitting
on_phase per phase); shallow/fused ones do a single pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.engine.cognition import run_ledger
from core.engine.cognition.fusion import render_context_sections
from core.engine.cognition.models import CognitiveComposition
from core.engine.cognition.multiphase import MultiPhaseExecutor
from core.engine.core.llm import get_llm
from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION, should_apply_cgrs

OnPhase = Callable[[int, int, str, str, float, list[str]], Awaitable[None]]


@dataclass
class ReasoningResult:
    conclusion: str
    phases: list[dict[str, Any]] = field(default_factory=list)  # {cognitive_function, output, confidence}


async def _load_framework_prompts(composition: CognitiveComposition, product_id: str) -> dict[str, str]:
    """Fetch slug -> system_prompt for the composition's resolved instruments.
    Mirrors executor.py's framework-prompt fetch; missing slugs fall back to
    PromptFusion text inside the executor."""
    slugs: list[str] = []
    for fw_slugs in composition.resolved_instruments.values():
        slugs.extend(fw_slugs)
    if not slugs:
        return {}
    prompts: dict[str, str] = {}
    try:
        from core.engine.core.db import parse_rows
        from core.engine.core.db import pool as _pool

        async with _pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT slug, system_prompt FROM framework WHERE slug IN $slugs;",
                    {"slugs": slugs},
                )
            )
        for row in rows:
            if row.get("system_prompt"):
                prompts[row["slug"]] = row["system_prompt"]
    except Exception:
        pass
    return prompts


async def run_reasoning(
    *,
    thought: str,
    classification: dict[str, Any],
    composition: CognitiveComposition,
    product_id: str,
    model: str | None,
    on_phase: OnPhase | None,
) -> ReasoningResult:
    cgrs_active = should_apply_cgrs(classification)

    async def _llm_call(system_prompt: str, user_prompt: str) -> str:
        effective_system = system_prompt
        if cgrs_active:
            if system_prompt:
                effective_system = f"{CGRS_SUPPRESSION}\n\n{system_prompt}"
            else:
                effective_system = CGRS_SUPPRESSION
        max_tokens_kwargs = {}
        if composition.max_tokens_per_phase is not None:
            max_tokens_kwargs["max_tokens"] = composition.max_tokens_per_phase
        return await get_llm().complete(user_prompt, system=effective_system, model=model, **max_tokens_kwargs)

    framework_prompts = await _load_framework_prompts(composition, product_id)

    run_id = await run_ledger.create_run(
        product_id=product_id,
        thought=thought,
        meta_skills=composition.meta_skills,
        depth=composition.depth,
        discipline=classification.get("discipline"),
    )

    # Shallow / fused: MultiPhaseExecutor returns "" — do a single pass instead.
    if composition.fusion_mode or not composition.active_phases:
        system_prompt = "You are a reasoning partner. Respond concisely and concretely."
        # Composition-level grounding (e.g. the loop-context "What we already
        # know" section — prior decisions + calibration) must reach the actual
        # LLM prompt on this branch too, not just the multiphase pipeline.
        context_block = render_context_sections(composition.prompt_sections)
        if context_block:
            system_prompt = f"{system_prompt}\n\n{context_block}"
        try:
            conclusion = await _llm_call(system_prompt, thought)
        except Exception:
            # Close the ledger as failed so the run never leaks as 'running';
            # then let the error propagate unchanged.
            await run_ledger.finalize_run(run_id=run_id, conclusion="", phases=[], trace=[], status="failed")
            raise
        await run_ledger.finalize_run(run_id=run_id, conclusion=conclusion, phases=[], trace=[], status="complete")
        return ReasoningResult(conclusion=conclusion, phases=[])

    phases: list[dict[str, Any]] = []

    async def _capture(idx, total, fn, output, confidence, gaps):
        phases.append({"cognitive_function": fn, "output": output, "confidence": confidence})
        if on_phase is not None:
            await on_phase(idx, total, fn, output, confidence, gaps)

    executor = MultiPhaseExecutor(llm_call=_llm_call, on_phase=_capture)
    try:
        conclusion = await executor.execute(
            description=thought,
            composition=composition,
            framework_prompts=framework_prompts,
            intel_context="",
            product_id=product_id,
        )
    except Exception:
        # Close the ledger as failed (preserving any phases captured so far)
        # so the run never leaks as 'running'; then re-raise unchanged.
        await run_ledger.finalize_run(
            run_id=run_id,
            conclusion=(phases[-1]["output"] if phases else ""),
            phases=phases,
            trace=list(getattr(executor, "_last_trace", []) or []),
            status="failed",
        )
        raise
    final = conclusion or (phases[-1]["output"] if phases else "")
    # The executor's _last_trace carries the rich per-phase Progress Ledger
    # (confidence, gaps, branched, refine_rounds, tainted...).
    trace = list(getattr(executor, "_last_trace", []) or [])
    await run_ledger.finalize_run(run_id=run_id, conclusion=final, phases=phases, trace=trace, status="complete")
    return ReasoningResult(conclusion=final, phases=phases)
