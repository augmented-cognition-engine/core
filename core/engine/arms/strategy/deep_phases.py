"""Shared deep phases — architect (greenfield: design the structure before generate) + foresight
(systemic: change-altitude consequence analysis grounded in the change's blast radius + Graph
Tensions + the committee). Domain-agnostic, non-fatal, ctx-accumulator. Seeded into every arm by
BrainHandArm so the depth layer's greenfield/systemic routing is fulfilled for code, design, data.

NOTE: this is CHANGE-altitude foresight (what does THIS change break). It deliberately does NOT use
the strategy-altitude product foresight subsystem (engine/foresight/), which forecasts product
trajectory from a product_id — a different question."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _architecture_framed(intent: str, domain: str) -> str:
    return (
        f"You are a senior {domain} architect. Design the STRUCTURE for the work below — "
        "modules/boundaries, interfaces/contracts, data flow, and the key decisions — concrete "
        "enough to implement directly. No code yet; produce the design an engineer builds to.\n\n"
        f"WORK: {intent}"
    )


def _consequence_framed(intent: str, domain: str, grounding) -> str:
    return (
        f"Foresight for this {domain} change. Identify (1) what BREAKS, (2) what is CONNECTED / "
        "affected, and (3) the systemic risks — specific and actionable, so the implementation "
        "addresses each. Ground the analysis in the blast radius + tensions below.\n\n"
        f"CHANGE: {intent}\n\nGRAPH GROUNDING: {grounding}"
    )


async def default_architect(intent: str, domain: str, ctx: dict, *, reasoner) -> str:
    """Greenfield: reason a structured design (modules/interfaces/data-flow). Non-fatal -> ''."""
    try:
        return (await reasoner(_architecture_framed(intent, domain), ctx)) or ""
    except Exception as exc:
        logger.warning("deep_phases.default_architect failed (non-fatal): %s", exc)
        return ""


async def _foresight_grounding(intent: str, product_id: str) -> dict:
    """Best-effort change-consequence grounding when ground_scan didn't run: ace_load (carries
    Graph Tensions in its snapshot) + ace_blast_radius. Each call non-fatal; graph-cold -> {}."""
    grounding: dict = {}
    try:
        from core.engine.mcp.tools import ace_load

        grounding = await ace_load(topic=intent, product_id=product_id) or {}
    except Exception as exc:
        logger.warning("deep_phases foresight ace_load failed (non-fatal): %s", exc)
    try:
        from core.engine.mcp.tools import ace_blast_radius

        grounding = {**grounding, "blast_radius": await ace_blast_radius(target=intent, product_id=product_id)}
    except Exception as exc:
        logger.warning("deep_phases foresight ace_blast_radius failed (non-fatal): %s", exc)
    return grounding


async def default_foresight(
    intent: str, domain: str, ctx: dict, *, reasoner, product_id: str = "product:platform"
) -> str:
    """Systemic: change-altitude consequence analysis grounded in the change's blast radius +
    Graph Tensions. Reuses ctx['scan'] (the ace_load snapshot) when ground_scan already loaded
    them; otherwise (e.g. systemic risk at nearby/none scope, where ground_scan is gated off)
    gathers its OWN best-effort grounding so foresight is never reasoned on an empty graph
    context — graph-grounded when warm, reasoned when cold. Non-fatal -> ''."""
    try:
        grounding = ctx.get("scan") or {}
        if not grounding:
            grounding = await _foresight_grounding(intent, product_id)
        return (await reasoner(_consequence_framed(intent, domain, grounding), ctx)) or ""
    except Exception as exc:
        logger.warning("deep_phases.default_foresight failed (non-fatal): %s", exc)
        return ""
