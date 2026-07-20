# engine/orchestrator/engagement.py
"""Multi-spin engagement execution engine.

Orchestrates one or more perspective spins — pipeline or adversarial — to
produce a unified response.  Each spin loads its own intelligence snapshot,
receives the prior spin's handoff, and contributes to a final synthesis.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher

from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput
from core.engine.orchestrator.verification_gate import VerificationGate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Perspective framing (legacy — kept for backward compatibility)
# ---------------------------------------------------------------------------

PERSPECTIVE_FRAMING: dict[str, str] = {
    "theorist": (
        "Focus on what is true and what is possible. Reason from scientific "
        "foundations and first principles. Surface assumptions, define the "
        "problem space, and identify theoretical constraints before solutions."
    ),
    "strategist": (
        "Focus on priorities, tradeoffs, and business impact. Evaluate options "
        "against goals, assess risk vs. reward, and recommend the path that "
        "maximises value while managing downside."
    ),
    "practitioner": (
        "Focus on how to build it. Provide concrete implementation details, "
        "proven patterns, code-level guidance, and practical techniques drawn "
        "from hands-on experience."
    ),
    "operator": (
        "Focus on delivery, sequencing, coordination, and risk. Define the "
        "execution plan — who does what, in what order, what can go wrong, "
        "and how to keep things on track."
    ),
}

# ---------------------------------------------------------------------------
# Archetype framing — canonical engagement vocabulary
#
# Archetypes (creator/analyst/executor/researcher/advisor/sentinel) are the
# primary axis.  Legacy perspective names (theorist/strategist/practitioner/
# operator) are included here so that ARCHETYPE_FRAMING is the single lookup
# table for both old and new names.  Callers should prefer archetype names
# going forward; perspective names remain accepted for backward compat.
# ---------------------------------------------------------------------------

ARCHETYPE_FRAMING: dict[str, str] = {
    # Legacy perspective names — kept for backward compat
    "theorist": (
        "Focus on what is fundamentally true. Reason from first principles. "
        "Surface assumptions and identify theoretical constraints before solutions."
    ),
    "strategist": (
        "Focus on priorities, tradeoffs, and impact. Evaluate options against "
        "goals and recommend the path that maximises value."
    ),
    "practitioner": (
        "Focus on how to build it. Provide concrete implementation details, proven patterns, and practical techniques."
    ),
    "operator": (
        "Focus on delivery and risk. Define the execution plan — sequencing, coordination, what can go wrong."
    ),
    # Archetype names — preferred going forward
    "analyst": (
        "Focus on evidence and structure. Decompose the problem, evaluate data, and reach well-reasoned conclusions."
    ),
    "creator": (
        "Focus on generating novel solutions. Explore the solution space broadly "
        "before converging on the best approach."
    ),
    "executor": ("Focus on precise implementation. Follow requirements exactly and produce concrete, working output."),
    "researcher": (
        "Focus on gathering comprehensive information. Cast a wide net, surface "
        "minority viewpoints, and synthesize findings."
    ),
    "advisor": ("Focus on decision quality. Present options with honest tradeoffs and a clear recommendation."),
    "sentinel": ("Focus on risk and quality. Identify what could go wrong, flag concerns, and verify assumptions."),
}

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_spin_prompt(
    task: str,
    perspective: str,
    prior_handoff: str | None,
    prior_questions: list[str] | None,
) -> str:
    """Build the prompt for a single perspective spin.

    Looks up framing from ARCHETYPE_FRAMING, which covers both archetype names
    (analyst, creator, executor, researcher, advisor, sentinel) and legacy
    perspective names (theorist, strategist, practitioner, operator).
    Falls back to PERSPECTIVE_FRAMING for any name not in ARCHETYPE_FRAMING.
    """
    framing = ARCHETYPE_FRAMING.get(perspective) or PERSPECTIVE_FRAMING.get(perspective, "")

    sections = [
        f"## Task\n{task}",
        f"## Your Perspective: {perspective}\n{framing}",
    ]

    if prior_handoff:
        sections.append(f"## Handoff from Prior Perspective\n{prior_handoff}")

    if prior_questions:
        questions_text = "\n".join(f"- {q}" for q in prior_questions)
        sections.append(f"## Open Questions to Address\n{questions_text}")

    sections.append(
        "## Output Format\n"
        "Return structured output with:\n"
        "- content: your analysis/response from this perspective\n"
        "- handoff: a concise brief for the next perspective (what they should know)\n"
        "- confidence: 0.0-1.0 how confident you are in your output\n"
        "- open_questions: questions the next perspective should address\n"
        f'- perspective: "{perspective}"\n'
        "- specialties_used: which specialties you drew on"
    )

    return "\n\n".join(sections)


def _build_adversarial_synthesis_prompt(
    task: str,
    spin_a: SpinOutput,
    spin_b: SpinOutput,
) -> str:
    """Build prompt for adversarial synthesis of two competing spins."""
    return (
        f"## Task\n{task}\n\n"
        f"## Perspective A — {spin_a.perspective}\n{spin_a.content}\n\n"
        f"## Perspective B — {spin_b.perspective}\n{spin_b.content}\n\n"
        "## Your Job\n"
        "Synthesize these two perspectives into a single, stronger response.\n\n"
        "**Important:** Your goal is to seek truth, not declare a winner. "
        "Both perspectives may hold valid insights. Identify where they agree, "
        "where they genuinely conflict, and resolve conflicts by examining the "
        "evidence and reasoning — not by splitting the difference.\n\n"
        "Produce a unified output that is better than either perspective alone."
    )


# ---------------------------------------------------------------------------
# Adversarial analysis — adaptive termination + diversity metric
# ---------------------------------------------------------------------------

_AGREEMENT_THRESHOLD = 0.75  # handoff similarity above this = skip synthesis


def compute_spin_diversity(spin_a: SpinOutput, spin_b: SpinOutput) -> float:
    """Measure how different two spin outputs are (0.0 = identical, 1.0 = completely different).

    Uses 1 - SequenceMatcher ratio on the handoff sections, since handoffs
    distill the key points each perspective chose to emphasize.
    """
    if not spin_a.handoff or not spin_b.handoff:
        return 1.0
    return 1.0 - SequenceMatcher(None, spin_a.handoff, spin_b.handoff).ratio()


def should_skip_synthesis(spin_a: SpinOutput, spin_b: SpinOutput) -> bool:
    """If adversarial spins substantially agree, skip the synthesis LLM call.

    Returns True when handoffs are highly similar (agreement > threshold),
    indicating the debate didn't surface meaningful disagreement.
    """
    diversity = compute_spin_diversity(spin_a, spin_b)
    return diversity < (1.0 - _AGREEMENT_THRESHOLD)


# ---------------------------------------------------------------------------
# classify_spin — budget LLM call for per-spin classification
# ---------------------------------------------------------------------------


async def classify_spin(
    task_description: str,
    perspective: str,
    prior_handoff: str | None,
    product_id: str,
) -> dict:
    """Budget LLM call to get archetype/mode/specialties for a specific perspective.

    Returns a dict with at least ``archetype``, ``mode``, ``specialties``.
    """
    context = ""
    if prior_handoff:
        context = f"\nContext from prior perspective: {prior_handoff}"

    result = await llm.complete_json(
        f"""Classify this task for a {perspective} perspective.

Task: {task_description}{context}

Return JSON with:
- archetype: creator|analyst|executor|researcher|advisor|sentinel
- mode: deliberative|reactive|exploratory|conversational|procedural|reflective
- specialties: list of up to 3 relevant specialty slugs (kebab-case)

JSON:""",
        model=settings.llm_budget_model,
    )

    return {
        "archetype": result.get("archetype", "executor"),
        "mode": result.get("mode", "reactive"),
        "specialties": result.get("specialties", []),
    }


# ---------------------------------------------------------------------------
# synthesize_spins
# ---------------------------------------------------------------------------


async def synthesize_spins(spins: list[SpinOutput], task: str) -> str:
    """Synthesize multiple spin outputs into a unified response.

    If only one spin is provided, returns its content directly (no LLM call).
    """
    if len(spins) == 1:
        return spins[0].content

    spin_sections = []
    for spin in spins:
        spin_sections.append(f"### {spin.perspective} (confidence: {spin.confidence})\n{spin.content}")
    all_spins = "\n\n".join(spin_sections)

    return await llm.complete(
        f"## Task\n{task}\n\n"
        f"## Perspective Outputs\n{all_spins}\n\n"
        "## Synthesis Instructions\n"
        "Combine these perspectives into a single, unified response. "
        "Preserve the strongest insights from each perspective. "
        "Resolve any conflicts. Do not mention the perspectives explicitly — "
        "produce a seamless final answer.",
        model=settings.llm_model,
    )


# ---------------------------------------------------------------------------
# Single-spin executor
# ---------------------------------------------------------------------------


async def _execute_single_spin(
    task_description: str,
    perspective: str,
    prior_handoff: str | None,
    prior_questions: list[str] | None,
    classification: dict,
    product_id: str,
    event_callback: Callable[..., Awaitable[None]] | None = None,
    snapshot: dict | None = None,
    budget_multiplier: float = 1.0,
    max_tokens: int = 8192,
) -> SpinOutput:
    """Execute one perspective spin: resolve specialties, load intelligence, call LLM.

    If ``snapshot`` is provided (pre-loaded shared context), it is used directly
    instead of making a fresh DB round-trip.  This ensures all spins in a single
    engagement see the same frozen context snapshot.
    """
    # Lazy imports to avoid circular dependencies
    from core.engine.orchestrator.dual_loader import load_dual_intelligence
    from core.engine.orchestrator.specialty_resolver import resolve_specialties

    try:
        specialties = classification.get("specialties", [])
        mode = classification.get("mode", "reactive")
        org_context = classification.get("org_context", [])

        if snapshot is not None:
            # Use the pre-loaded shared snapshot — no DB round-trip needed.
            resolved_slugs = snapshot.get("specialties_loaded", specialties)
        else:
            # Resolve specialties
            resolved = await resolve_specialties(specialties, product_id)
            resolved_slugs = [r.get("slug", "") for r in resolved.get("resolved", [])]

            # Load intelligence fresh (fallback path)
            snapshot = await load_dual_intelligence(
                specialties=resolved_slugs,
                product_id=product_id,
                org_context=org_context,
                mode=mode,
                budget_multiplier=budget_multiplier,
                discipline=classification.get("discipline", ""),
            )

        # Notify caller about loaded intelligence
        insights = snapshot.get("insights", [])
        if event_callback:
            await event_callback(
                {"type": "intelligence", "spin": 0, "perspective": perspective, "count": len(insights)}
            )

        # Build prompt with intelligence context
        prompt = _build_spin_prompt(
            task=task_description,
            perspective=perspective,
            prior_handoff=prior_handoff,
            prior_questions=prior_questions,
        )

        # Append intelligence to prompt if available
        if insights:
            insight_lines = [
                f"- [{i.get('tier', '')}] {i.get('content', '')} (confidence: {i.get('confidence', 0)})"
                for i in insights[:10]
            ]
            prompt += "\n\n## Relevant Intelligence\n" + "\n".join(insight_lines)

        # Inject cognitive structure if present (depth 1-2 fusion mode).
        # framework_prompts are pre-fetched by executor and stored in snapshot["_framework_prompts"].
        composition = classification.get("cognitive_composition")
        if composition and composition.fusion_mode and composition.prompt_sections:
            try:
                from core.engine.cognition.fusion import PromptFusion

                fw_prompts = snapshot.get("_framework_prompts", {}) if snapshot else {}
                cognitive_section = PromptFusion().fuse(composition, framework_prompts=fw_prompts)
                if cognitive_section:
                    prompt += cognitive_section
            except Exception:
                pass  # non-fatal

        result = await llm.complete_structured(
            prompt,
            SpinOutput,
            model=settings.llm_model,
            max_tokens=max_tokens,
        )

        # Ensure perspective is set correctly
        result.perspective = perspective
        result.specialties_used = resolved_slugs

        return result

    except Exception as exc:
        logger.error("Spin failed for perspective=%s: %s", perspective, exc)
        return SpinOutput(
            content=f"[Spin failed: {exc}]",
            handoff="",
            confidence=0.0,
            open_questions=[],
            perspective=perspective,
            specialties_used=[],
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def execute_engagement(
    task_description: str,
    classification: dict,
    product_id: str,
    workspace_id: str = "workspace:default",
    event_callback: Callable[..., Awaitable[None]] | None = None,
    perspective_weights: dict[str, float] | None = None,
) -> EngagementResult:
    """Execute a multi-spin engagement.

    Orchestrates perspective spins in pipeline or adversarial mode based on
    the engagement plan from the classifier.

    Parameters
    ----------
    task_description:
        The user's task / question.
    classification:
        Full classification dict (from classify_task), including ``engagement``.
    product_id:
        SurrealDB org record ID.
    workspace_id:
        SurrealDB workspace record ID.
    event_callback:
        Optional async callback for streaming progress events.  When provided,
        called with ``{"type": ..., ...}`` dicts at each stage.

    Returns
    -------
    EngagementResult
        Contains all spins, merged output, and metadata.
    """
    engagement = classification.get("engagement", {})
    perspectives = engagement.get("perspectives", [classification.get("perspective", "practitioner")])
    adversarial_pair = engagement.get("adversarial_pair")
    rationale = engagement.get("rationale", "")
    # TALE per-spin token cap — derived from classification token_budget (set by classify_task).
    spin_max_tokens: int = classification.get("token_budget") or 8192
    _spin_max_tokens_kwargs = {"max_tokens": spin_max_tokens}

    total_spins = len(perspectives)
    is_multi = total_spins > 1

    spins: list[SpinOutput] = []
    adversarial_resolution: str | None = None
    adversarial_diversity: float | None = None
    synthesis_skipped = False

    # Load context snapshot ONCE for all spins so every spin sees the same
    # frozen intelligence state — no race conditions, no redundant DB queries,
    # no asymmetric information in adversarial debates.
    from core.engine.orchestrator.executor import _load_snapshot

    discipline = classification.get("discipline", "")
    mode = classification.get("mode", "reactive")
    shared_snapshot = await _load_snapshot(classification, discipline, product_id, mode)

    # Helper: only fire callback for multi-spin engagements
    async def _emit(event: dict) -> None:
        if event_callback and is_multi:
            await event_callback(event)

    spin_number = 0
    i = 0
    while i < len(perspectives):
        perspective = perspectives[i]

        # Check if this + next form an adversarial pair
        if (
            adversarial_pair
            and i + 1 < len(perspectives)
            and perspective == adversarial_pair[0]
            and perspectives[i + 1] == adversarial_pair[1]
        ):
            # Adversarial: run both in parallel
            prior_handoff = spins[-1].handoff if spins else None
            prior_questions = spins[-1].open_questions if spins else None

            spin_number += 1
            await _emit(
                {"type": "spin_started", "spin": spin_number, "total": total_spins, "perspective": adversarial_pair[0]}
            )
            spin_number_b = spin_number + 1
            await _emit(
                {
                    "type": "spin_started",
                    "spin": spin_number_b,
                    "total": total_spins,
                    "perspective": adversarial_pair[1],
                }
            )

            # Classify both spins
            cls_a = await classify_spin(task_description, adversarial_pair[0], prior_handoff, product_id)
            cls_b = await classify_spin(task_description, adversarial_pair[1], prior_handoff, product_id)

            # Build per-spin callbacks that tag the intelligence event with the correct spin number
            async def _cb_a(event: dict) -> None:
                if event.get("type") == "intelligence":
                    event["spin"] = spin_number
                if event_callback:
                    await event_callback(event)

            async def _cb_b(event: dict) -> None:
                if event.get("type") == "intelligence":
                    event["spin"] = spin_number_b
                if event_callback:
                    await event_callback(event)

            weight_a = (perspective_weights or {}).get(adversarial_pair[0], 1.0)
            weight_b = (perspective_weights or {}).get(adversarial_pair[1], 1.0)
            spin_a, spin_b = await asyncio.gather(
                _execute_single_spin(
                    task_description,
                    adversarial_pair[0],
                    prior_handoff,
                    prior_questions,
                    cls_a,
                    product_id,
                    event_callback=_cb_a if event_callback else None,
                    snapshot=shared_snapshot,
                    budget_multiplier=weight_a,
                    **_spin_max_tokens_kwargs,
                ),
                _execute_single_spin(
                    task_description,
                    adversarial_pair[1],
                    prior_handoff,
                    prior_questions,
                    cls_b,
                    product_id,
                    event_callback=_cb_b if event_callback else None,
                    snapshot=shared_snapshot,
                    budget_multiplier=weight_b,
                    **_spin_max_tokens_kwargs,
                ),
            )

            spins.extend([spin_a, spin_b])

            await _emit(
                {
                    "type": "spin_completed",
                    "spin": spin_number,
                    "perspective": adversarial_pair[0],
                    "handoff": spin_a.handoff,
                    "confidence": spin_a.confidence,
                }
            )
            await _emit(
                {
                    "type": "spin_completed",
                    "spin": spin_number_b,
                    "perspective": adversarial_pair[1],
                    "handoff": spin_b.handoff,
                    "confidence": spin_b.confidence,
                }
            )

            spin_number = spin_number_b

            # Adaptive termination: if spins substantially agree, skip synthesis
            adversarial_diversity = compute_spin_diversity(spin_a, spin_b)
            if should_skip_synthesis(spin_a, spin_b):
                logger.info(
                    "Adversarial spins agree (diversity=%.2f) — skipping synthesis",
                    adversarial_diversity,
                )
                synthesis_skipped = True
                adversarial_resolution = spin_a.content if spin_a.confidence >= spin_b.confidence else spin_b.content
            else:
                synthesis_prompt = _build_adversarial_synthesis_prompt(task_description, spin_a, spin_b)
                adversarial_resolution = await llm.complete(
                    synthesis_prompt, model=settings.llm_model, **_spin_max_tokens_kwargs
                )

            i += 2

        else:
            # Pipeline: sequential with handoff
            prior_handoff = spins[-1].handoff if spins else None
            prior_questions = spins[-1].open_questions if spins else None

            spin_number += 1

            await _emit({"type": "spin_started", "spin": spin_number, "total": total_spins, "perspective": perspective})

            # First spin uses global classification; subsequent spins get their own
            if i == 0:
                spin_classification = classification
            else:
                spin_classification = await classify_spin(
                    task_description,
                    perspective,
                    prior_handoff,
                    product_id,
                )
                # Carry over org_context and cognitive_composition from global classification
                spin_classification["org_context"] = classification.get("org_context", [])
                if "cognitive_composition" in classification:
                    spin_classification["cognitive_composition"] = classification["cognitive_composition"]

            # Build a per-spin callback that tags the intelligence event with the spin number
            _current_spin = spin_number

            async def _spin_cb(event: dict, *, _sn: int = _current_spin) -> None:
                if event.get("type") == "intelligence":
                    event["spin"] = _sn
                if event_callback:
                    await event_callback(event)

            weight = (perspective_weights or {}).get(perspective, 1.0)
            spin = await _execute_single_spin(
                task_description,
                perspective,
                prior_handoff,
                prior_questions,
                spin_classification,
                product_id,
                event_callback=_spin_cb if event_callback else None,
                snapshot=shared_snapshot,
                budget_multiplier=weight,
                **_spin_max_tokens_kwargs,
            )
            spins.append(spin)

            await _emit(
                {
                    "type": "spin_completed",
                    "spin": spin_number,
                    "perspective": perspective,
                    "handoff": spin.handoff,
                    "confidence": spin.confidence,
                }
            )

            i += 1

    # Final output
    if len(spins) == 1:
        merged_output = spins[0].content
    else:
        await _emit({"type": "synthesis_started", "perspectives": [s.perspective for s in spins]})
        merged_output = await synthesize_spins(spins, task_description)

    _gate = VerificationGate()
    _verification = await _gate.verify(task_description, merged_output)

    return EngagementResult(
        spins=spins,
        merged_output=merged_output,
        perspectives_used=[s.perspective for s in spins],
        adversarial_resolution=adversarial_resolution,
        adversarial_diversity=adversarial_diversity,
        synthesis_skipped=synthesis_skipped,
        engagement_rationale=rationale,
        verified=_verification.verified,
        verification_gaps=_verification.gaps,
        verification_verdict=_verification.verdict,
    )


# ---------------------------------------------------------------------------
# Archetype-based entry points
# ---------------------------------------------------------------------------


async def run_engagement_with_archetypes(
    task_description: str,
    archetypes: list[str],
    product_id: str,
    workspace_id: str = "workspace:default",
    event_callback: Callable[..., Awaitable[None]] | None = None,
    perspective_weights: dict[str, float] | None = None,
    adversarial_pair: list[str] | None = None,
    rationale: str = "",
) -> EngagementResult:
    """Execute a multi-spin engagement driven by archetype names.

    This is the canonical new entry point.  Accepts archetype names
    (analyst, creator, executor, researcher, advisor, sentinel) directly —
    no need to translate to legacy perspective vocabulary first.

    Parameters
    ----------
    task_description:
        The user's task / question.
    archetypes:
        Ordered list of archetype names to spin through.  Each name must be a
        key in ARCHETYPE_FRAMING (archetype or legacy perspective name).
    product_id:
        SurrealDB product record ID.
    workspace_id:
        SurrealDB workspace record ID.
    event_callback:
        Optional async callback for streaming progress events.
    perspective_weights:
        Optional per-archetype weighting for budget allocation.
    adversarial_pair:
        Optional two-element list of archetypes to run adversarially.
    rationale:
        Human-readable explanation of why this engagement plan was chosen.

    Returns
    -------
    EngagementResult
        Contains all spins, merged output, and metadata.
    """
    # Validate archetype names against the unified framing table
    valid = [a for a in archetypes if a in ARCHETYPE_FRAMING]
    if not valid:
        valid = ["executor"]

    # Validate adversarial pair
    resolved_pair: list[str] | None = None
    if adversarial_pair and len(adversarial_pair) == 2:
        if all(p in ARCHETYPE_FRAMING for p in adversarial_pair) and all(p in valid for p in adversarial_pair):
            resolved_pair = adversarial_pair

    classification = {
        "discipline": "architecture",
        "archetype": valid[0],
        "mode": "deliberative" if len(valid) > 1 else "reactive",
        "complexity": "complex" if len(valid) > 1 else "moderate",
        "perspective": valid[0],
        "specialties": [],
        "org_context": [],
        "engagement": {
            "perspectives": valid,
            "adversarial_pair": resolved_pair,
            "rationale": rationale,
        },
    }

    return await execute_engagement(
        task_description=task_description,
        classification=classification,
        product_id=product_id,
        workspace_id=workspace_id,
        event_callback=event_callback,
        perspective_weights=perspective_weights,
    )


async def run_engagement(
    task_description: str,
    perspectives: list[str],
    product_id: str,
    workspace_id: str = "workspace:default",
    event_callback: Callable[..., Awaitable[None]] | None = None,
    perspective_weights: dict[str, float] | None = None,
    adversarial_pair: list[str] | None = None,
    rationale: str = "",
) -> EngagementResult:
    """Execute a multi-spin engagement using perspective names.

    Backward-compatible entry point.  Accepts legacy perspective names
    (theorist, strategist, practitioner, operator) as well as archetype names
    — both are valid keys in ARCHETYPE_FRAMING.

    Prefer ``run_engagement_with_archetypes`` for new call sites.
    """
    return await run_engagement_with_archetypes(
        task_description=task_description,
        archetypes=perspectives,
        product_id=product_id,
        workspace_id=workspace_id,
        event_callback=event_callback,
        perspective_weights=perspective_weights,
        adversarial_pair=adversarial_pair,
        rationale=rationale,
    )
