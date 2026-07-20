"""The deep committee — the real, multi-voice x multi-phase committee primitive.

Supersedes the dead CommitteePattern stub. Resolves the reasoning lenses a build
engages (problem-derived, NO fixed roster) and runs EACH through its recipe deep
via run_reasoning, in parallel, streamed, then synthesizes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.engine.cognition.reasoning_run import run_reasoning  # imported at module-top so tests can monkeypatch it
from core.engine.orchestration.loop_context import load_loop_context  # module-top so tests can monkeypatch it

logger = logging.getLogger(__name__)

MAX_LENSES = 4

# Map a specialty slug's domain to a discipline-lens. Specialties are kebab slugs
# whose leading token names the domain (security-hardening -> security). This is a
# lightweight derivation, not a fixed roster — the SET emerges from the problem.
_SPECIALTY_DISCIPLINE = {
    "security": "security",
    "data": "data",
    "performance": "performance",
    "scale": "scale",
    "ux": "ux",
    "product": "product_strategy",
    "ml": "ai_ml",
    "ai": "ai_ml",
}


def resolve_lenses(classification: dict[str, Any]) -> list[str]:
    """Return the ordered, deduped discipline-lenses this build engages.
    Primary discipline first, then distinct disciplines implied by specialties.
    Capped at MAX_LENSES. Bookends (research/risk) are separate stages, not lenses."""
    primary = classification.get("discipline") or "architecture"
    lenses: list[str] = [primary]
    for spec in classification.get("specialties", []) or []:
        head = str(spec).split("-", 1)[0]
        disc = _SPECIALTY_DISCIPLINE.get(head)
        if disc and disc not in lenses:
            lenses.append(disc)
    return lenses[:MAX_LENSES]


# ---------------------------------------------------------------------------
# Task 2: run_deep_committee — multi-voice × multi-phase, parallel, streamed
# ---------------------------------------------------------------------------

OnEvent = Callable[[str, dict], Awaitable[None]]


@dataclass
class CommitteeResult:
    lens_outputs: dict[str, str]  # discipline -> deep conclusion
    lens_lineage: dict[str, list]  # discipline -> phases
    synthesis: str = ""
    recipe_slugs: dict[str, str] = field(default_factory=dict)  # discipline -> recipe slug used


async def _compose_for_lens(classification: dict[str, Any], product_id: str):
    """Compose a CognitiveComposition for one lens (deliberative+complex forces deep)."""
    from core.engine.cognition.composer import CognitiveComposer

    return await CognitiveComposer().compose(classification, product_id)


def _lens_classification(base: dict[str, Any], lens: str) -> dict[str, Any]:
    """A per-lens classification that routes to the lens's recipe.

    Depth is problem-driven: the base classification's mode+complexity flow
    through unchanged, so the composer's depth derivation (and fusion_mode
    short-circuit) decides whether this lens runs multi-phase or single-pass.
    A trivial build gets fusion_mode per lens (1 LLM call); a complex one
    gets the full multi-phase recipe (3–4 calls). Same primitive, problem-fit
    LLM use."""
    return {**base, "discipline": lens}


async def run_deep_committee(
    request: str,
    lenses: list[str],
    product_id: str,
    *,
    base_classification: dict[str, Any] | None = None,
    event_callback: OnEvent | None = None,
    model: str | None = None,
) -> CommitteeResult:
    """Run each lens through its recipe deep (run_reasoning), in parallel, streamed.

    Lens failures are fault-isolated: one lens raising does not crash the committee —
    surviving lenses' deep conclusions still come back. If every lens fails (or the
    lens set is empty), the result is an empty CommitteeResult."""
    if not lenses:
        return CommitteeResult(lens_outputs={}, lens_lineage={}, synthesis="")

    base = base_classification or {}

    # Load loop context ONCE per build — NOT per lens. All lenses share the same
    # prior-decision + calibration context so the ledger is consistent across voices.
    # Fail-open: any failure returns {} and lenses compose statelessly.
    _loop_ctx: dict[str, Any] = {}
    try:
        _loop_ctx = await load_loop_context(product_id, base)
        if _loop_ctx:
            base = {**base, "loop_context": _loop_ctx}
            # Emit layer5.context_loaded so canvas shows "informed by N decisions"
            try:
                from core.engine.canvas.event_protocol import EVENT_LAYER5_CONTEXT_LOADED
                from core.engine.events.bus import bus as _main_bus

                await _main_bus.emit(
                    EVENT_LAYER5_CONTEXT_LOADED,
                    {
                        "decision_count": len(_loop_ctx.get("prior_decisions", [])),
                        "capability_count": 0,
                        "discipline_count": 0,
                        "recency_count": 0,
                        "degraded_tiers": [],
                        "contradictions_count": 0,
                        "elapsed_ms": 0.0,
                        "calibration_archetypes": len(_loop_ctx.get("calibration", {})),
                    },
                )
            except Exception:
                logger.debug("layer5.context_loaded emit failed in committee (non-fatal)", exc_info=True)
    except Exception:
        logger.debug("loop_context load failed in committee (non-fatal)", exc_info=True)

    async def _one(lens: str):
        cls = _lens_classification(base, lens)
        composition = await _compose_for_lens(cls, product_id)
        # Capture recipe slug for downstream signal emission. Fallback to the
        # lens name if meta_skills is unexpectedly empty.
        recipe_slug = composition.meta_skills[0] if composition.meta_skills else lens

        async def _on_phase(idx, total, fn, output, confidence, gaps):
            if event_callback is None:
                return
            # Convention: output=None and confidence=None signals a phase START.
            # Anything else is a phase END.
            is_start = output is None and confidence is None
            event_type = "agent.phase.start" if is_start else "agent.phase.end"
            payload = {
                "lens": lens,
                "phase_idx": idx,
                "total_phases": total,
                "cognitive_function": fn,
            }
            if not is_start:
                payload["confidence"] = confidence
            await event_callback(event_type, payload)

        res = await run_reasoning(
            thought=request,
            classification=cls,
            composition=composition,
            product_id=product_id,
            model=model,
            on_phase=_on_phase,
        )
        return lens, res, recipe_slug

    raw = await asyncio.gather(*[_one(lens) for lens in lenses], return_exceptions=True)
    triples = [item for item in raw if not isinstance(item, BaseException)]
    lens_outputs = {lens: res.conclusion for lens, res, _slug in triples}
    lens_lineage = {lens: res.phases for lens, res, _slug in triples}
    recipe_slugs = {lens: slug for lens, _res, slug in triples}

    synthesis = "\n\n".join(f"## {lens}\n{out}" for lens, out in lens_outputs.items())
    return CommitteeResult(
        lens_outputs=lens_outputs,
        lens_lineage=lens_lineage,
        synthesis=synthesis,
        recipe_slugs=recipe_slugs,
    )
