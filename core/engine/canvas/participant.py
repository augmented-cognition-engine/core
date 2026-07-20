"""Persistent AI presence on a Decision Canvas (plan §A3).

A CanvasParticipant is bound to one canvas_session. It consumes the surface-
agnostic event stream and emits its own events (artifacts, state changes).
It does NOT run a long polling loop in v1 — it's invoked synchronously by
the surface adapter on each incoming event. Real live-streaming presence
ships in v1.1 once tldraw multiplayer is wired.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from core.engine.canvas.event_protocol import (
    EVENT_FRAMEWORK_COMPLETED,
    EVENT_FRAMEWORK_REQUESTED,
    EVENT_PARTICIPANT_STATE_CHANGED,
    EVENT_SESSION_OPENED,
    FrameworkCompletedPayload,
    ParticipantStateChangedPayload,
)
from core.engine.canvas.models import ParticipantState
from core.engine.canvas.orchestrated_renderer import render_via_orchestration

EmitFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class CanvasParticipant:
    def __init__(self, session_id: str, emit: EmitFn, participant_id: Optional[str] = None):
        self.session_id = session_id
        self.participant_id = participant_id or f"canvas_participant:ai_{session_id}"
        self._emit = emit
        self.state = ParticipantState.IDLE

    async def handle_event(self, event: dict[str, Any]) -> None:
        et = event.get("event_type")
        if et == EVENT_SESSION_OPENED:
            await self._transition(ParticipantState.WATCHING)
        elif et == EVENT_FRAMEWORK_REQUESTED:
            await self._render_framework(event["payload"])
        # Other event types: stay in current state for v1.

    async def _render_framework(self, payload: dict[str, Any]) -> None:
        await self._transition(ParticipantState.DRAFTING)
        # Resolve cited_artifact_ids → cited text via the persistence layer.
        # The protocol payload (FrameworkRequestedPayload) carries IDs only —
        # the participant is responsible for hydration before invoking the
        # renderer. If we left this to the caller, the participant would
        # silently render frameworks with empty citations.
        cited_text = await self._resolve_cited_text(payload.get("cited_artifact_ids", []))
        framework_kind = payload["framework_kind"]
        tldraw_shape_id = f"shape:fw_{uuid4().hex[:10]}"
        product_id = payload.get("project_id", "product:default")
        prior_decisions = await _get_prior_decisions(self.session_id)

        async def on_canvas_event(event_type: str, event_payload: dict[str, Any]) -> None:
            await self._emit(self.session_id, event_type, event_payload)

        spec = await render_via_orchestration(
            kind=framework_kind,
            prompt=payload["prompt"],
            cited_text=cited_text,
            prior_decisions=prior_decisions,
            product_id=product_id,
            on_canvas_event=on_canvas_event,
        )
        await self._emit(
            self.session_id,
            EVENT_FRAMEWORK_COMPLETED,
            FrameworkCompletedPayload(
                tldraw_shape_id=tldraw_shape_id,
                shape_kind=spec.shape_kind,
                framework_kind=framework_kind,
                payload=spec.payload,
            ).model_dump(),
        )
        await self._transition(ParticipantState.WATCHING)

    async def _resolve_cited_text(self, cited_artifact_ids: list[str]) -> list[str]:
        """Look up artifacts by ID, return their `payload.text` (sticky text)
        in citation order. Missing artifacts are skipped silently — they may
        have been deleted between citation and framework invocation."""
        if not cited_artifact_ids:
            return []
        from core.engine.canvas.persistence import list_artifacts

        artifacts = await list_artifacts(self.session_id)
        index = {a.id: a for a in artifacts}
        out: list[str] = []
        for aid in cited_artifact_ids:
            a = index.get(aid)
            if a is None:
                continue
            text = a.payload.get("text", "") if isinstance(a.payload, dict) else ""
            if text:
                out.append(text)
        return out

    async def _transition(self, new_state: ParticipantState) -> None:
        if new_state == self.state:
            return
        self.state = new_state
        await self._emit(
            self.session_id,
            EVENT_PARTICIPANT_STATE_CHANGED,
            ParticipantStateChangedPayload(
                participant_id=self.participant_id,
                new_state=new_state.value,
            ).model_dump(),
        )


async def _get_prior_decisions(session_id: str) -> list[str]:
    """Load prior decisions for this session as formatted strings. Best-effort."""
    try:
        from core.engine.canvas.persistence import list_artifacts

        artifacts = await list_artifacts(session_id)
        decisions = []
        for a in artifacts:
            if a.shape_kind.value == "decision_sticky" and isinstance(a.payload, dict):
                title = a.payload.get("title", "")
                rationale = a.payload.get("rationale", "")
                if title:
                    decisions.append(f"{title}: {rationale}" if rationale else title)
        return decisions[:10]
    except Exception:
        return []
