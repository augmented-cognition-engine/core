"""Orchestrated framework rendering — classify → engage → extract artifact.

Replaces the direct LLM call in framework_renderer.py with the full ACE
orchestration pipeline: task classification, N-perspective engagement with
canvas event streaming, then structured artifact extraction from synthesis.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from core.engine.canvas.canvas_engagement import OnCanvasEvent, run_canvas_engagement
from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_END,
    EVENT_AGENT_PERSPECTIVE_START,
    EVENT_AGENT_PERSPECTIVE_STEP,
    EVENT_PIPELINE_CLASSIFY,
    EVENT_PIPELINE_COMPOSE,
    EVENT_PIPELINE_ORCHESTRATE,
    EVENT_SYNTHESIS_END,
    EVENT_SYNTHESIS_STEP,
    PipelineClassifyPayload,
    PipelineComposePayload,
    PipelineOrchestratePayload,
)
from core.engine.canvas.framework_renderer import ArtifactSpec
from core.engine.cognition.composer import CognitiveComposer
from core.engine.core.llm import get_llm

_log = logging.getLogger(__name__)

# Per-kind JSON schemas injected into the extraction prompt.
_SCHEMAS: dict[str, str] = {
    "trade_off_matrix": """\
<json>
{
  "title": "<short matrix title>",
  "question": "<the question being decided>",
  "options": [
    {"name": "<Option A>", "scores": {"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}, "note": "<one-line rationale>"},
    {"name": "<Option B>", "scores": {"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}, "note": "<one-line rationale>"}
  ],
  "axes": [
    {"name": "<axis 1>", "weight": <0-1 float>},
    {"name": "<axis 2>", "weight": <0-1 float>}
  ],
  "recommendation": "<which option and why in one sentence>"
}
</json>""",
    "design_options": """\
<json>
{
  "title": "<short title>",
  "question": "<the design question>",
  "options": [
    {"name": "<Option A>", "scores": {"<axis 1>": <0-10 int>}, "note": "<rationale>"},
    {"name": "<Option B>", "scores": {"<axis 1>": <0-10 int>}, "note": "<rationale>"}
  ],
  "axes": [
    {"name": "<axis 1>", "weight": <0-1 float>}
  ],
  "recommendation": "<recommended option and why>"
}
</json>""",
    "code_architecture": """\
<json>
{
  "title": "<module title>",
  "module": "<module or system name>",
  "nodes": [
    {"id": "n1", "label": "<name>", "type": "core"},
    {"id": "n2", "label": "<name>", "type": "consumer"}
  ],
  "edges": [
    {"from": "n2", "to": "n1", "label": "<relationship>"}
  ],
  "blast_radius": {
    "score": <0.0-1.0 float>,
    "affected_files": <int>,
    "risk": "low|medium|high"
  },
  "recommendation": "<architectural recommendation in one sentence>"
}
</json>""",
    "strategy": """\
<json>
{
  "title": "<short title for the decision>",
  "question": "<the strategic question being decided>",
  "options": [
    {"name": "<Option A>", "case_for": "<strongest argument for>", "case_against": "<strongest argument against>"},
    {"name": "<Option B>", "case_for": "<strongest argument for>", "case_against": "<strongest argument against>"}
  ],
  "key_considerations": ["<consideration the committee surfaced>", "<another>"],
  "recommendation": "<the recommended direction and the one reason that decides it>",
  "confidence": "low|medium|high"
}
</json>""",
}


def _build_task(
    kind: str,
    prompt: str,
    cited_text: list[str],
    prior_decisions: Optional[list[str]],
) -> str:
    parts = [f"Framework type: {kind}", f"Question: {prompt}"]
    if cited_text:
        parts.append("Canvas context:\n" + "\n".join(f"- {c}" for c in cited_text))
    if prior_decisions:
        parts.append("Prior decisions:\n" + "\n".join(f"- {d}" for d in prior_decisions))
    return "\n\n".join(parts)


def _extract_json_block(raw: str) -> dict[str, Any]:
    match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return json.loads(raw)


def _validate_trade_off_matrix(payload: dict[str, Any]) -> None:
    if not (isinstance(payload.get("options"), list) and len(payload["options"]) >= 2):
        raise ValueError("trade_off_matrix requires at least 2 options")
    if not (isinstance(payload.get("axes"), list) and len(payload["axes"]) >= 2):
        raise ValueError("trade_off_matrix requires at least 2 axes")
    axis_names = {a["name"] for a in payload["axes"] if "name" in a}
    for opt in payload["options"]:
        scores = opt.get("scores", {})
        missing = axis_names - set(scores.keys())
        if missing:
            raise ValueError(f"Option {opt.get('name')!r} missing scores: {missing}")


def _validate_design_options(payload: dict[str, Any]) -> None:
    if not (isinstance(payload.get("options"), list) and len(payload["options"]) >= 2):
        raise ValueError("design_options requires at least 2 options")
    if not (isinstance(payload.get("axes"), list) and len(payload["axes"]) >= 1):
        raise ValueError("design_options requires at least 1 axis")


def _validate_code_architecture(payload: dict[str, Any]) -> None:
    if not (isinstance(payload.get("nodes"), list) and len(payload["nodes"]) >= 2):
        raise ValueError("code_architecture requires at least 2 nodes")
    br = payload.get("blast_radius", {})
    if br.get("risk") not in ("low", "medium", "high"):
        raise ValueError("blast_radius.risk must be low|medium|high")


_VALIDATORS = {
    "trade_off_matrix": _validate_trade_off_matrix,
    "design_options": _validate_design_options,
    "code_architecture": _validate_code_architecture,
}


async def _extract_artifact(
    kind: str,
    prompt: str,
    analysis: str,
    cited_text: list[str],
    prior_decisions: Optional[list[str]],
) -> ArtifactSpec:
    schema = _SCHEMAS.get(kind)
    if not schema:
        raise NotImplementedError(f"Framework kind '{kind}' has no extraction schema")

    cited = "\n".join(f"- {c}" for c in cited_text) or "(none)"
    prior = "\n".join(f"- {d}" for d in prior_decisions) if prior_decisions else "(none)"

    extraction_prompt = (
        f"You are ACE, synthesizing a structured reasoning artifact.\n\n"
        f"Original question: {prompt}\n\n"
        f"Canvas context:\n{cited}\n\n"
        f"Prior decisions:\n{prior}\n\n"
        f"Multi-agent analysis:\n{analysis}\n\n"
        f"Produce a structured {kind} artifact based on this analysis.\n"
        f"Output ONLY the <json> block below — no other prose.\n\n"
        f"{schema}"
    )

    llm = get_llm()
    raw = await llm.complete(extraction_prompt)
    try:
        payload = _extract_json_block(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned unparseable JSON for framework kind '{kind}': {exc}\nRaw output: {raw[:500]}"
        ) from exc

    validator = _VALIDATORS.get(kind)
    if validator:
        validator(payload)

    return ArtifactSpec(
        shape_kind="framework_artifact",
        payload={"framework_kind": kind, **payload},
    )


async def _noop_canvas_event(event_type: str, payload: dict[str, Any]) -> None:
    pass


async def render_via_orchestration(
    kind: str,
    prompt: str,
    cited_text: list[str],
    prior_decisions: Optional[list[str]],
    product_id: str,
    on_canvas_event: Optional[OnCanvasEvent] = None,
    event_bus: Optional[Any] = None,
    calibration_weights: Optional[dict[str, float]] = None,
) -> ArtifactSpec:
    """Classify → engage → extract. Replaces render_framework for canvas.

    Emits agent.perspective.* and synthesis.* events via on_canvas_event.
    If event_bus is provided, emits BlockStart/BlockDone for each pipeline phase.
    Returns ArtifactSpec with same payload structure as non-orchestrated renderer.
    """
    import time

    _forward = on_canvas_event or _noop_canvas_event
    trace_data: dict[str, Any] = {}

    async def _emit(event_type: str, event_payload: dict[str, Any]) -> None:
        await _forward(event_type, event_payload)
        if event_type == EVENT_PIPELINE_CLASSIFY:
            trace_data["classify"] = event_payload
        elif event_type == EVENT_PIPELINE_COMPOSE:
            trace_data["compose"] = event_payload
        elif event_type == EVENT_PIPELINE_ORCHESTRATE:
            trace_data["orchestrate"] = event_payload
            trace_data.setdefault("perspectives", [])
        elif event_type == EVENT_AGENT_PERSPECTIVE_START:
            trace_data.setdefault("perspectives", []).append(
                {
                    "archetype": event_payload["archetype"],
                    "mode": event_payload["mode"],
                    "index": event_payload["perspective_index"],
                    "content": "",
                    "handoff": "",
                    "confidence": 0.0,
                    "complete": False,
                }
            )
        elif event_type == EVENT_AGENT_PERSPECTIVE_STEP:
            for p in trace_data.get("perspectives", []):
                if p["index"] == event_payload["perspective_index"]:
                    p["content"] = event_payload["content"]
        elif event_type == EVENT_AGENT_PERSPECTIVE_END:
            for p in trace_data.get("perspectives", []):
                if p["index"] == event_payload["perspective_index"]:
                    p["confidence"] = event_payload["confidence"]
                    p["handoff"] = event_payload["handoff"]
                    p["complete"] = True
        elif event_type == EVENT_SYNTHESIS_STEP:
            trace_data["synthesis"] = {"content": event_payload["content"], "complete": False}
        elif event_type == EVENT_SYNTHESIS_END:
            if "synthesis" in trace_data:
                trace_data["synthesis"]["complete"] = True

    async def _block_start(name: str, layer: int) -> str:
        if event_bus is None:
            return ""
        from core.engine.orchestration.events import BlockStart

        e = BlockStart(run_id=event_bus.run_id, product_id=product_id, block_name=name, layer=layer)
        await event_bus.emit(e)
        return e.task_id

    async def _block_done(name: str, task_id: str, t0: float) -> None:
        if event_bus is None:
            return
        from core.engine.orchestration.events import BlockDone

        await event_bus.emit(
            BlockDone(
                run_id=event_bus.run_id,
                product_id=product_id,
                task_id=task_id,
                block_name=name,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )

    task = _build_task(kind, prompt, cited_text, prior_decisions)

    # Block 1: canvas skips LLM classify — mode is always deliberative,
    # perspectives always ["analyst", "advisor"]. Use hardcoded defaults to
    # save one full subprocess spawn (~10-15s under CLIProvider).
    t0 = time.monotonic()
    tid = await _block_start("classify", 1)
    classification = {
        "discipline": "architecture",
        "archetype": "analyst",
        "mode": "deliberative",
        "engagement": {"perspectives": ["analyst", "advisor"], "adversarial_pair": None, "rationale": "canvas"},
        "specialties": [],
        "org_context": [],
    }
    await _block_done("classify", tid, t0)

    # Re-sort perspectives by calibration score: better-calibrated archetypes lead.
    # Graceful fallback: unknown archetypes get score 0.5 (mid-point, preserve order).
    if calibration_weights:
        eng = classification.setdefault("engagement", {})
        perspectives = eng.get("perspectives") or []
        if perspectives:
            eng["perspectives"] = sorted(
                perspectives,
                key=lambda p: calibration_weights.get(p, 0.5),
                reverse=True,
            )

    await _emit(
        EVENT_PIPELINE_CLASSIFY,
        PipelineClassifyPayload(
            discipline=classification.get("discipline", "architecture"),
            archetype=classification.get("archetype", "executor"),
            mode=classification.get("mode", "deliberative"),
            specialties=classification.get("specialties") or [],
        ).model_dump(),
    )

    # Block 2: compose (cognitive composition)
    t0 = time.monotonic()
    tid = await _block_start("compose", 2)
    try:
        composition = await CognitiveComposer().compose(classification, product_id)
        functions = [s["cognitive_function"] for s in composition.prompt_sections if "cognitive_function" in s]
        await _emit(
            EVENT_PIPELINE_COMPOSE,
            PipelineComposePayload(
                meta_skills=composition.meta_skills,
                depth=composition.depth,
                fusion_mode=composition.fusion_mode,
                phase_count=len(composition.active_phases),
                top_functions=functions[:3],
            ).model_dump(),
        )
    except Exception:
        _log.warning("pipeline.compose failed — continuing without composition data", exc_info=True)
    await _block_done("compose", tid, t0)

    perspectives = (classification.get("engagement") or {}).get("perspectives") or []
    await _emit(
        EVENT_PIPELINE_ORCHESTRATE,
        PipelineOrchestratePayload(
            perspectives=perspectives,
            total=len(perspectives),
        ).model_dump(),
    )

    # Block 3: engage (multi-perspective spins)
    t0 = time.monotonic()
    tid = await _block_start("engage", 3)
    analysis = await run_canvas_engagement(task, classification, product_id, _emit)
    await _block_done("engage", tid, t0)

    # Block 4: extract artifact
    t0 = time.monotonic()
    tid = await _block_start("extract", 4)
    result = await _extract_artifact(kind, prompt, analysis, cited_text, prior_decisions)
    await _block_done("extract", tid, t0)
    result.reasoning_trace = trace_data or None
    return result
