"""Run multi-perspective engagement for canvas, emitting labeled agent events.

Wraps engine/orchestrator/engagement.py spin execution.
Each perspective spin emits: agent.perspective.start → token…token → end.
Multi-perspective sessions also emit: synthesis.start → step → end.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_END,
    EVENT_AGENT_PERSPECTIVE_START,
    EVENT_AGENT_PERSPECTIVE_TOKEN,
    EVENT_SYNTHESIS_END,
    EVENT_SYNTHESIS_START,
    EVENT_SYNTHESIS_STEP,
    AgentPerspectiveEndPayload,
    AgentPerspectiveStartPayload,
    AgentPerspectiveTokenPayload,
    SynthesisStepPayload,
)
from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.orchestrator.engagement import _build_spin_prompt, synthesize_spins
from core.engine.orchestrator.engagement_models import SpinOutput

logger = logging.getLogger(__name__)

_TOKEN_FLUSH_CHARS = 40  # flush a perspective.token delta once this many chars accrue


async def _assemble_canvas_prompt(
    task: str,
    perspective: str,
    classification: dict,
    product_id: str,
) -> tuple[str, list[str]]:
    """Build the same spin prompt _execute_single_spin uses (intelligence-injected),
    without touching that function. Returns (prompt, resolved_specialty_slugs).

    Fusion-mode cognitive-structure injection is intentionally omitted: canvas
    multi-perspective engagement is not fusion mode (depth >= 3), so that branch
    never fires for this path.
    """
    # Lazy imports — mirror engagement.py's circular-import avoidance.
    from core.engine.orchestrator.dual_loader import load_dual_intelligence
    from core.engine.orchestrator.specialty_resolver import resolve_specialties

    specialties = classification.get("specialties", [])
    mode = classification.get("mode", "reactive")
    org_context = classification.get("org_context", [])

    resolved = await resolve_specialties(specialties, product_id)
    resolved_slugs = [r.get("slug", "") for r in resolved.get("resolved", [])]
    # budget_multiplier intentionally defaults to 1.0 — classification doesn't
    # carry it on the canvas path, so we let load_dual_intelligence use its default.
    snapshot = await load_dual_intelligence(
        specialties=resolved_slugs,
        product_id=product_id,
        org_context=org_context,
        mode=mode,
        discipline=classification.get("discipline", ""),
    )

    prompt = _build_spin_prompt(task=task, perspective=perspective, prior_handoff=None, prior_questions=None)
    insights = snapshot.get("insights", [])
    if insights:
        insight_lines = [
            f"- [{i.get('tier', '')}] {i.get('content', '')} (confidence: {i.get('confidence', 0)})"
            for i in insights[:10]
        ]
        prompt += "\n\n## Relevant Intelligence\n" + "\n".join(insight_lines)
    return prompt, resolved_slugs


async def _stream_spin_content(
    task: str,
    perspective: str,
    classification: dict,
    product_id: str,
    on_delta: "Callable[[str], Awaitable[None]]",
    max_tokens: int = 2048,
) -> SpinOutput:
    """Stream a perspective's reasoning, flushing batched text deltas via on_delta.

    Returns a SpinOutput whose content is the full streamed text. handoff/confidence
    are left minimal — the canvas consumes content live; cross-perspective handoff
    is not used on the parallel canvas path (see run_canvas_engagement). Never
    raises: on failure it returns a degraded SpinOutput, mirroring _execute_single_spin.
    """
    try:
        prompt, resolved_slugs = await _assemble_canvas_prompt(task, perspective, classification, product_id)
        content = ""
        pending = ""
        async for chunk in llm.stream(prompt, model=settings.llm_model, max_tokens=max_tokens):
            if not chunk:
                continue
            content += chunk
            pending += chunk
            if len(pending) >= _TOKEN_FLUSH_CHARS:
                await on_delta(pending)
                pending = ""
        if pending:
            await on_delta(pending)
        return SpinOutput(
            content=content,
            handoff="",
            confidence=0.0,
            open_questions=[],
            perspective=perspective,
            specialties_used=resolved_slugs,
        )
    except Exception as exc:  # mirror _execute_single_spin's non-fatal contract
        logger.warning("canvas stream spin failed for %s: %s", perspective, exc)
        return SpinOutput(
            content=f"[Spin failed: {exc}]",
            handoff="",
            confidence=0.0,
            open_questions=[],
            perspective=perspective,
            specialties_used=[],
        )


OnCanvasEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


async def run_canvas_engagement(
    task: str,
    classification: dict[str, Any],
    product_id: str,
    on_canvas_event: OnCanvasEvent,
) -> str:
    """Run engagement spins for a canvas framework request.

    Emits labeled canvas events per agent perspective and for synthesis.
    Perspectives run in parallel (independent contexts) to stay within timeout.
    Returns the final synthesized analysis text (not the structured artifact).
    """
    engagement = classification.get("engagement") or {}
    perspectives: list[str] = engagement.get("perspectives") or ["executor"]
    total = len(perspectives)

    # Pre-allocate result slots so ordering is preserved after parallel execution
    spins: list[SpinOutput | None] = [None] * total

    async def _run_one(i: int, perspective: str) -> None:
        await on_canvas_event(
            EVENT_AGENT_PERSPECTIVE_START,
            AgentPerspectiveStartPayload(
                archetype=perspective,
                mode=classification.get("mode", "deliberative"),
                perspective_index=i,
                total_perspectives=total,
            ).model_dump(),
        )

        spin_classification = {**classification, "archetype": perspective}

        async def _on_delta(text: str) -> None:
            await on_canvas_event(
                EVENT_AGENT_PERSPECTIVE_TOKEN,
                AgentPerspectiveTokenPayload(
                    archetype=perspective,
                    delta=text,
                    perspective_index=i,
                ).model_dump(),
            )

        spin = await _stream_spin_content(
            task=task,
            perspective=perspective,
            classification=spin_classification,
            product_id=product_id,
            on_delta=_on_delta,
            max_tokens=2048,
        )
        spins[i] = spin
        # NOTE: no EVENT_AGENT_PERSPECTIVE_STEP — the streamed deltas already carried
        # the full content; emitting the step would double it on the frontend track.

        await on_canvas_event(
            EVENT_AGENT_PERSPECTIVE_END,
            AgentPerspectiveEndPayload(
                archetype=perspective,
                handoff=spin.handoff or "",
                confidence=spin.confidence,
                perspective_index=i,
            ).model_dump(),
        )

    await asyncio.gather(*[_run_one(i, p) for i, p in enumerate(perspectives)])

    completed = [s for s in spins if s is not None]

    if len(completed) == 1:
        return completed[0].content

    await on_canvas_event(EVENT_SYNTHESIS_START, {})
    synthesis = await synthesize_spins(completed, task)
    await on_canvas_event(
        EVENT_SYNTHESIS_STEP,
        SynthesisStepPayload(content=synthesis).model_dump(),
    )
    await on_canvas_event(EVENT_SYNTHESIS_END, {})
    return synthesis
