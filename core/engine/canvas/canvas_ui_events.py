"""Bridge canvas reasoning events into the orchestration-WS UI protocol.

`render_via_orchestration` emits rich, semantic events through its
`on_canvas_event` channel — `agent.perspective.start/step/end`,
`synthesis.start/step/end`, `pipeline.classify/orchestrate`. The canvas
frontend's reducer (`orchestrationProtocol.ts` / `useOrchestrationSession`)
speaks a different, narrower vocabulary: `classification`,
`engagement_start`, `token`, `engagement_done`.

This module is the one-way bridge. `translate_canvas_event` maps a single
canvas event to the UI event the WS should forward, or `None` when the
canvas event has no UI projection. The WS layer emits the result on the
per-run EventBus so it serializes with the rest of the run's frames.

Field notes (why the shapes are what they are):
  - Tracks in the frontend are keyed by `task_id`; we mint a stable id per
    perspective index (and one for synthesis) so `token`/`engagement_done`
    land on the track `engagement_start` opened.
  - `agent.perspective.step` carries the *full* spin content in a single
    emission (not deltas), so mapping it to one `token` is correct —
    `appendToken` on an empty track yields the whole contribution.
  - Optional classification fields default to `None`; the frontend merges
    with `?? prev`, so `None` means "leave the prior value" rather than
    clobbering discipline/depth to empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_END,
    EVENT_AGENT_PERSPECTIVE_START,
    EVENT_AGENT_PERSPECTIVE_STEP,
    EVENT_AGENT_PERSPECTIVE_TOKEN,
    EVENT_PIPELINE_CLASSIFY,
    EVENT_PIPELINE_ORCHESTRATE,
    EVENT_SYNTHESIS_END,
    EVENT_SYNTHESIS_START,
    EVENT_SYNTHESIS_STEP,
)
from core.engine.orchestration.events import OrchestratorEvent

_SYNTHESIS_TASK_ID = "canvas-synthesis"


def _perspective_task_id(index: int) -> str:
    return f"canvas-perspective-{index}"


@dataclass(frozen=True)
class UIClassification(OrchestratorEvent):
    event_type: str = field(default="classification", init=False)
    discipline: str | None = None
    archetypes: list[str] = field(default_factory=list)
    depth: int | None = None


@dataclass(frozen=True)
class UIEngagementStart(OrchestratorEvent):
    event_type: str = field(default="engagement_start", init=False)
    pattern: str = ""
    archetypes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UIToken(OrchestratorEvent):
    event_type: str = field(default="token", init=False)
    content: str = ""


@dataclass(frozen=True)
class UIEngagementDone(OrchestratorEvent):
    event_type: str = field(default="engagement_done", init=False)


def translate_canvas_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    run_id: str,
    product_id: str,
) -> OrchestratorEvent | None:
    """Map one canvas event to the UI-protocol event to forward, or None."""
    if event_type == EVENT_PIPELINE_CLASSIFY:
        archetype = payload.get("archetype") or ""
        return UIClassification(
            run_id=run_id,
            product_id=product_id,
            discipline=payload.get("discipline") or None,
            archetypes=[archetype] if archetype else [],
            depth=2,
        )

    if event_type == EVENT_PIPELINE_ORCHESTRATE:
        perspectives = list(payload.get("perspectives") or [])
        if not perspectives:
            return None
        # archetypes only — discipline/depth left None so the prior value holds.
        return UIClassification(run_id=run_id, product_id=product_id, archetypes=perspectives)

    if event_type == EVENT_AGENT_PERSPECTIVE_START:
        idx = int(payload.get("perspective_index", 0))
        archetype = payload.get("archetype") or ""
        return UIEngagementStart(
            run_id=run_id,
            product_id=product_id,
            task_id=_perspective_task_id(idx),
            pattern=payload.get("mode") or "",
            archetypes=[archetype] if archetype else [],
        )

    if event_type == EVENT_AGENT_PERSPECTIVE_STEP:
        idx = int(payload.get("perspective_index", 0))
        return UIToken(
            run_id=run_id,
            product_id=product_id,
            task_id=_perspective_task_id(idx),
            content=payload.get("content") or "",
        )

    if event_type == EVENT_AGENT_PERSPECTIVE_TOKEN:
        idx = int(payload.get("perspective_index", 0))
        return UIToken(
            run_id=run_id,
            product_id=product_id,
            task_id=_perspective_task_id(idx),
            content=payload.get("delta") or "",
        )

    if event_type == EVENT_AGENT_PERSPECTIVE_END:
        idx = int(payload.get("perspective_index", 0))
        return UIEngagementDone(run_id=run_id, product_id=product_id, task_id=_perspective_task_id(idx))

    if event_type == EVENT_SYNTHESIS_START:
        return UIEngagementStart(
            run_id=run_id,
            product_id=product_id,
            task_id=_SYNTHESIS_TASK_ID,
            pattern="synthesis",
            archetypes=["synthesis"],
        )

    if event_type == EVENT_SYNTHESIS_STEP:
        return UIToken(
            run_id=run_id,
            product_id=product_id,
            task_id=_SYNTHESIS_TASK_ID,
            content=payload.get("content") or "",
        )

    if event_type == EVENT_SYNTHESIS_END:
        return UIEngagementDone(run_id=run_id, product_id=product_id, task_id=_SYNTHESIS_TASK_ID)

    return None
