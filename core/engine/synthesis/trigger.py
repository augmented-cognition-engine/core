# engine/synthesis/trigger.py
"""SynthesisTrigger — auto-fires the Synthesizer on key events.

Subscribes to the event bus and triggers cross-discipline synthesis
whenever significant state changes occur, without being asked.

Triggered events:
  spec.created       — synthesize spec intent + cross-discipline implications
  spec.verified      — synthesize what was delivered
  commit.detected    — synthesize code change implications
  observation.created — synthesize decision/pattern/correction implications

Signals are stored via SignalStore for retrieval by the briefing engine.
Non-fatal: synthesis failure never propagates to the caller.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Map observation_type → discipline for context inference
_OBSERVATION_DISCIPLINE_MAP = {
    "decision": "architecture",
    "pattern": "architecture",
    "correction": "error_handling",
    "learning": "architecture",
    "preference": "ux",
    "error": "error_handling",
}

# Map event_type → discipline fallback
_EVENT_DISCIPLINE_MAP = {
    "spec.created": "architecture",
    "spec.verified": "architecture",
    "commit.detected": "code_conventions",
    "observation.created": "architecture",
}

TRIGGER_EVENTS = [
    "spec.created",
    "spec.verified",
    "commit.detected",
    "observation.created",
]


def build_task_context(event_type: str, payload: dict) -> dict:
    """Build a synthesizer-compatible task context from an event payload.

    The synthesizer expects: discipline, output, intelligence_loaded, status.
    We build this from the event payload without an LLM call.
    """
    discipline = _infer_discipline(event_type, payload)
    output = _build_output_text(event_type, payload)

    return {
        "id": f"event:{event_type}",
        "discipline": discipline,
        "output": output,
        "intelligence_loaded": {},
        "status": "completed",
    }


def _infer_discipline(event_type: str, payload: dict) -> str:
    """Infer the most relevant discipline from the event payload."""
    if event_type == "observation.created":
        obs_type = payload.get("observation_type", "")
        return _OBSERVATION_DISCIPLINE_MAP.get(obs_type, "architecture")
    if event_type == "spec.created" and payload.get("discipline"):
        return payload["discipline"]
    return _EVENT_DISCIPLINE_MAP.get(event_type, "architecture")


def _build_output_text(event_type: str, payload: dict) -> str:
    """Build a description string the synthesizer can reason over."""
    if event_type == "spec.created":
        objective = payload.get("objective", payload.get("description", ""))
        spec_id = payload.get("spec_id", "")
        return f"Spec created: {objective}\nSpec ID: {spec_id}"

    if event_type == "spec.verified":
        objective = payload.get("objective", payload.get("description", ""))
        spec_id = payload.get("spec_id", "")
        return f"Spec verified (acceptance criteria passed): {objective}\nSpec ID: {spec_id}"

    if event_type == "commit.detected":
        message = payload.get("message", "")
        files = payload.get("files_changed", [])
        files_str = ", ".join(files[:10]) if files else "unknown"
        return f"Commit detected: {message}\nFiles changed: {files_str}"

    if event_type == "observation.created":
        content = payload.get("content", payload.get("summary", ""))
        obs_type = payload.get("observation_type", "")
        return f"Observation captured ({obs_type}): {content}"

    # Fallback: serialize whatever payload we have
    return f"Event {event_type}: {payload}"


def _build_summary(synthesis_result: Any) -> str:
    """Build a human-readable summary from synthesis result."""
    leverage_points = synthesis_result.leverage_points
    if not leverage_points:
        return "Synthesis completed — no significant cross-discipline signals detected."
    top = leverage_points[0]
    others = len(leverage_points) - 1
    summary = f"[{top.discipline}] {top.intervention}"
    if others > 0:
        summary += f" (+{others} more leverage point{'s' if others > 1 else ''})"
    return summary


class SynthesisTrigger:
    """Auto-fires the Synthesizer on key system events.

    Usage::

        trigger = SynthesisTrigger(bus=bus)
        trigger.register()  # subscribes to all TRIGGER_EVENTS
    """

    def __init__(
        self,
        bus: Any,
        synthesizer: Any | None = None,
        signal_store: Any | None = None,
    ) -> None:
        self._bus = bus
        self._synthesizer = synthesizer
        self._signal_store = signal_store

    def _get_synthesizer(self) -> Any:
        if self._synthesizer is not None:
            return self._synthesizer
        from core.engine.orchestrator.synthesizer import Synthesizer

        return Synthesizer()

    def _get_signal_store(self) -> Any:
        if self._signal_store is not None:
            return self._signal_store
        from core.engine.synthesis.signal_store import SurrealSignalStore

        return SurrealSignalStore()

    def register(self) -> None:
        """Register handlers on the event bus for all trigger events."""
        for event_type in TRIGGER_EVENTS:
            self._bus.on(event_type, self._make_handler(event_type))
        logger.info("SynthesisTrigger registered for %d events", len(TRIGGER_EVENTS))

    def _make_handler(self, event_type: str):
        """Create a named event handler for a specific event type."""

        async def handler(evt: str, payload: dict) -> None:
            await self.handle_event(evt, payload)

        handler.__name__ = f"synthesis_trigger_{event_type.replace('.', '_')}"
        return handler

    async def handle_event(self, event_type: str, payload: dict) -> None:
        """Handle a triggering event — synthesize and store signal if warranted.

        Non-fatal: any failure is logged and swallowed.
        """
        product_id = payload.get("product_id", "")
        if not product_id:
            logger.debug("SynthesisTrigger skipping event with no product_id: %s", event_type)
            return

        try:
            synth = self._get_synthesizer()
            task_ctx = build_task_context(event_type, payload)
            result = await synth.synthesize(task_ctx)

            if not result.leverage_points:
                logger.debug(
                    "SynthesisTrigger: no leverage points for %s — skipping signal storage",
                    event_type,
                )
                return

            from core.engine.synthesis.signal_store import ProactiveSignal

            signal = ProactiveSignal(
                product_id=product_id,
                event_type=event_type,
                leverage_points=[lp.to_dict() for lp in result.leverage_points],
                summary=_build_summary(result),
                status="new",
            )

            store = self._get_signal_store()
            await store.store(signal)

            logger.info(
                "SynthesisTrigger stored signal for %s [%s]: %s",
                event_type,
                product_id,
                signal.summary,
            )

        except Exception as exc:
            logger.warning(
                "SynthesisTrigger.handle_event failed (non-fatal) for %s: %s",
                event_type,
                exc,
            )
