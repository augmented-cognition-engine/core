"""LivingCanvasEvent — typed events for the Living Canvas real-time channel.

Every mutation to the product model (capabilities, decisions, scores, edges)
emits a LivingCanvasEvent via the bus. The WebSocket endpoint in
engine/api/live_canvas.py fans them out to subscribed portal clients.

Emit points call emit_canvas_event() — fire-and-forget, never raises.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from core.engine.events.bus import bus


class LivingCanvasEventType(str, Enum):
    CAPABILITY_ADDED = "capability.added"
    CAPABILITY_UPDATED = "capability.updated"
    CAPABILITY_LIFECYCLE_CHANGED = "capability.lifecycle_changed"
    DECISION_CAPTURED = "decision.captured"
    EDGE_ADDED = "edge.added"
    SCORE_CHANGED = "score.changed"
    SENTINEL_FIRED = "sentinel.fired"
    BRIEFING_UPDATED = "briefing.updated"
    PROACTIVE_LINE_UPDATED = "proactive.line.updated"
    HANDOFF_STARTED = "handoff.started"
    HANDOFF_PROGRESS = "handoff.progress"
    HANDOFF_COMPLETED = "handoff.completed"
    DRIFT_CROSSED = "drift.crossed"
    RECOMMENDATION_SHIFTED = "recommendation.shifted"
    UNCERTAINTY_OPENED = "uncertainty.opened"
    UNCERTAINTY_ANSWERED = "uncertainty.answered"
    INTELLIGENCE_CLASSIFIED = "intelligence.classified"
    PATTERN_MATCHED = "pattern.matched"
    CODE_EDITED = "code.edited"
    THREAD_COMMITTED = "thread.committed"
    THREAD_RESOLVED = "thread.resolved"
    # L3 composition layer — emitted when the composer selects a meta-skill set
    # for a task. Renders on the canvas as "the orchestra" so the user (and AI
    # partners observing) can see which intelligences are weighing in.
    COMPOSITION_SELECTED = "composition.selected"


class Provenance(BaseModel):
    """Who or what triggered this canvas event."""

    source: Literal["user", "ace_classifier", "sentinel", "scanner", "agent_dispatch"]
    actor_id: str | None = None
    rationale: str | None = None

    model_config = {"frozen": True}


class LivingCanvasEvent(BaseModel):
    """Typed event emitted whenever the product model changes.

    All events carry Provenance so the portal can render "why this changed"
    alongside what changed — the basis of the Living Canvas's "breathing" quality.
    """

    event_type: LivingCanvasEventType
    product_id: str
    timestamp: datetime
    payload: dict
    provenance: Provenance

    model_config = {"frozen": True}


async def emit_canvas_event(
    event_type: LivingCanvasEventType,
    product_id: str,
    payload: dict,
    provenance: Provenance,
) -> None:
    """Emit a typed canvas event via the event bus.

    Fire-and-forget — never raises. The bus serializes and fans out to
    all WebSocket subscribers for this product_id.
    """
    event = LivingCanvasEvent(
        event_type=event_type,
        product_id=product_id,
        timestamp=datetime.now(timezone.utc),
        payload=payload,
        provenance=provenance,
    )
    await bus.emit(
        f"canvas.{event_type.value}",
        event.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Convenience emitters — called by engine modules at their write points
# ---------------------------------------------------------------------------


async def emit_capability_added(
    product_id: str,
    slug: str,
    name: str,
    status: str = "planned",
    actor_id: str | None = None,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.CAPABILITY_ADDED,
        product_id=product_id,
        payload={"slug": slug, "name": name, "status": status},
        provenance=Provenance(
            source="user",
            actor_id=actor_id,
            rationale=f"Capability '{name}' added to product model",
        ),
    )


async def emit_capability_updated(
    product_id: str,
    slug: str,
    name: str,
    status: str = "planned",
    actor_id: str | None = None,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.CAPABILITY_UPDATED,
        product_id=product_id,
        payload={"slug": slug, "name": name, "status": status},
        provenance=Provenance(
            source="user",
            actor_id=actor_id,
            rationale=f"Capability '{slug}' updated",
        ),
    )


async def emit_decision_captured(
    product_id: str,
    decision_id: str,
    title: str,
    affected_capabilities: list[str],
    source_session: str | None = None,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.DECISION_CAPTURED,
        product_id=product_id,
        payload={
            "decision_id": decision_id,
            "title": title,
            "affected_capabilities": affected_capabilities,
        },
        provenance=Provenance(
            source="user",
            actor_id=source_session,
            rationale=f"Decision captured: {title}",
        ),
    )


async def emit_composition_selected(
    product_id: str,
    meta_skills: list[str],
    depth: int,
    fusion_mode: bool,
    classification: dict | None = None,
) -> None:
    """Emit when the L3 composer selects a meta-skill set for a task.

    Makes the orchestra visible — the canvas can render which of the 22
    meta-intelligences are weighing in for the current task, why this
    composition emerged from the classification, and how deep the reasoning
    will go (depth 1-4, fusion vs multiphase).

    This is the "all layers seen and accessible" affordance for L3
    specifically. AI partners observing the substrate also receive this
    via the bus.
    """
    payload: dict = {
        "meta_skills": list(meta_skills or []),
        "depth": depth,
        "fusion_mode": fusion_mode,
    }
    if classification:
        # Keep the embedded classification compact — full classification has
        # confidence scores, sub-dimensions, engagement metadata that the
        # canvas doesn't need for the orchestra view.
        payload["classification"] = {
            "task_type": classification.get("task_type", ""),
            "discipline": classification.get("discipline", ""),
            "mode": classification.get("mode", ""),
            "archetype": classification.get("archetype", ""),
            "complexity": classification.get("complexity", ""),
        }
    rationale = f"Composer assembled {len(payload['meta_skills'])} meta-skill(s) at depth {depth}"
    await emit_canvas_event(
        LivingCanvasEventType.COMPOSITION_SELECTED,
        product_id=product_id,
        payload=payload,
        provenance=Provenance(
            source="ace_classifier",
            rationale=rationale,
        ),
    )


async def emit_edge_added(
    product_id: str,
    edge_type: str,
    from_id: str,
    to_id: str,
    actor_id: str | None = None,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.EDGE_ADDED,
        product_id=product_id,
        payload={"edge_type": edge_type, "from_id": from_id, "to_id": to_id},
        provenance=Provenance(
            source="ace_classifier",
            actor_id=actor_id,
            rationale=f"Edge '{edge_type}' created between {from_id} → {to_id}",
        ),
    )


async def emit_score_changed(
    product_id: str,
    capability_slug: str,
    dimension: str,
    old_score: float,
    new_score: float,
    sentinel_name: str,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.SCORE_CHANGED,
        product_id=product_id,
        payload={
            "capability_slug": capability_slug,
            "dimension": dimension,
            "old_score": old_score,
            "new_score": new_score,
        },
        provenance=Provenance(
            source="sentinel",
            actor_id=sentinel_name,
            rationale=f"{sentinel_name} scored {capability_slug}.{dimension}: {old_score:.2f} → {new_score:.2f}",
        ),
    )


async def emit_sentinel_fired(
    product_id: str,
    sentinel_name: str,
    summary: str,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.SENTINEL_FIRED,
        product_id=product_id,
        payload={"sentinel_name": sentinel_name, "summary": summary},
        provenance=Provenance(
            source="sentinel",
            actor_id=sentinel_name,
            rationale=summary,
        ),
    )


async def emit_briefing_updated(
    product_id: str,
    briefing_id: str,
    summary: str,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.BRIEFING_UPDATED,
        product_id=product_id,
        payload={"briefing_id": briefing_id, "summary": summary},
        provenance=Provenance(
            source="sentinel",
            actor_id="briefing_engine",
            rationale="Briefing updated",
        ),
    )


async def emit_proactive_line_updated(
    product_id: str,
    line: str,
    source: str,
    source_artifact_id: str,
    severity: float,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.PROACTIVE_LINE_UPDATED,
        product_id=product_id,
        payload={
            "line": line,
            "source": source,
            "source_artifact_id": source_artifact_id,
            "severity": severity,
        },
        provenance=Provenance(
            source="sentinel",
            actor_id="proactive_aggregator",
            rationale="Proactive line updated by aggregator",
        ),
    )


async def emit_handoff_started(
    product_id: str,
    handoff_id: str,
    spec_id: str,
    agent: str,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.HANDOFF_STARTED,
        product_id=product_id,
        payload={"handoff_id": handoff_id, "spec_id": spec_id, "agent": agent},
        provenance=Provenance(
            source="agent_dispatch",
            actor_id=agent,
            rationale=f"Hand-off {handoff_id} dispatched to {agent} for spec {spec_id}",
        ),
    )


async def emit_handoff_progress(
    product_id: str,
    handoff_id: str,
    plain_language: str,
    pct: int,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.HANDOFF_PROGRESS,
        product_id=product_id,
        payload={"handoff_id": handoff_id, "plain_language": plain_language, "pct": pct},
        provenance=Provenance(
            source="agent_dispatch",
            actor_id="handoff_dispatcher",
            rationale="Hand-off progress update",
        ),
    )


async def emit_handoff_completed(
    product_id: str,
    handoff_id: str,
    status: str,
    completion_summary: str,
) -> None:
    await emit_canvas_event(
        LivingCanvasEventType.HANDOFF_COMPLETED,
        product_id=product_id,
        payload={
            "handoff_id": handoff_id,
            "status": status,
            "completion_summary": completion_summary,
        },
        provenance=Provenance(
            source="agent_dispatch",
            actor_id="handoff_dispatcher",
            rationale=f"Hand-off {handoff_id} completed with status {status}",
        ),
    )


async def emit_thread_committed(
    product_id: str,
    thread_id: str,
    topic: str,
    action_id: str,
) -> None:
    """User committed to a thread — they're focusing on this. Closed-loop labels this as a positive partner outcome."""
    await emit_canvas_event(
        LivingCanvasEventType.THREAD_COMMITTED,
        product_id=product_id,
        payload={
            "thread_id": thread_id,
            "topic": topic,
            "product_id": product_id,
            "action_id": action_id,
        },
        provenance=Provenance(
            source="user",
            actor_id=action_id,
            rationale=f"Thread '{topic}' committed by user",
        ),
    )


async def emit_thread_resolved(
    product_id: str,
    thread_id: str,
    topic: str,
    action_id: str,
) -> None:
    """User marked a thread resolved — gap closed. Closed-loop labels this as a positive partner outcome."""
    await emit_canvas_event(
        LivingCanvasEventType.THREAD_RESOLVED,
        product_id=product_id,
        payload={
            "thread_id": thread_id,
            "topic": topic,
            "product_id": product_id,
            "action_id": action_id,
        },
        provenance=Provenance(
            source="user",
            actor_id=action_id,
            rationale=f"Thread '{topic}' resolved by user",
        ),
    )
