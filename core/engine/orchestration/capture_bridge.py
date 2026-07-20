# engine/orchestration/capture_bridge.py
"""Bridges orchestration bus messages to the CaptureService singleton.

Converts BusMessages into StreamEvents and emits them into the always-on
capture service rather than managing a per-run pipeline lifecycle.
"""

from __future__ import annotations

import logging

from core.engine.orchestration.bus import BusMessage, MessageType

logger = logging.getLogger(__name__)

_EVENT_TYPE_MAP = {
    MessageType.DISCOVERY: "text",
    MessageType.PARTIAL_RESULT: "text",
    MessageType.FINAL_RESULT: "text",
    MessageType.HANDOFF: "status",
    MessageType.AGENT_SPAWNED: "status",
    MessageType.AGENT_COMPLETED: "status",
    MessageType.AGENT_FAILED: "error",
    MessageType.POSITION_SUBMITTED: "text",
    MessageType.CHALLENGE_ISSUED: "text",
    MessageType.BROADCAST: "text",
}

# Only emit message types that carry real intelligence signal
_SIGNAL_TYPES = frozenset(
    {
        MessageType.DISCOVERY,
        MessageType.FINAL_RESULT,
        MessageType.POSITION_SUBMITTED,
        MessageType.CHALLENGE_ISSUED,
    }
)


class OrchestrationCaptureWatcher:
    """Bridges orchestration bus messages to the CaptureService singleton.

    Kept for backward compatibility — callers that instantiate this class
    still work. handle_message() now emits directly to capture_service
    instead of maintaining a local queue.
    """

    def __init__(self, run_id: str, product_id: str = "", workspace_id: str | None = None) -> None:
        self.run_id = run_id
        self.product_id = product_id
        self.workspace_id = workspace_id

    async def handle_message(self, message: BusMessage) -> None:
        """Convert a high-signal BusMessage to a StreamEvent and emit to CaptureService."""
        # Only capture messages that carry real intelligence content
        if message.type not in _SIGNAL_TYPES:
            return

        content = message.payload.get("content", "")
        if not content and message.payload.get("summary"):
            content = message.payload["summary"]
        if not content:
            return  # No content worth capturing

        from datetime import datetime, timezone

        from core.engine.capture.watchers import StreamEvent

        event = StreamEvent(
            timestamp=message.timestamp or datetime.now(timezone.utc),
            event_type=_EVENT_TYPE_MAP.get(message.type, "text"),
            content=f"[{message.type.value}] {content}",
            session_id=message.run_id,
            metadata={
                "product_id": self.product_id,
                "workspace_id": self.workspace_id,
                "run_id": self.run_id,
                "source": "orchestration_bus",
            },
        )

        try:
            from core.engine.capture.service import capture_service

            await capture_service.emit(event)
        except Exception as exc:
            logger.debug("OrchestrationCaptureWatcher emit failed: %s", exc)

    def stop(self) -> None:
        """No-op — lifecycle is now managed by CaptureService."""
        pass
