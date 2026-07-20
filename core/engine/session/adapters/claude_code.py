"""ClaudeCodeAdapter — normalizes Claude Code StreamEvents into the Session model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.engine.session.models import SessionEvent, SessionTurn


class ClaudeCodeAdapter:
    """Adapter for Claude Code transcript events.

    Wraps the current SessionImportWatcher / StreamEvent semantics without
    leaking tool-specific field names into the normalized Session shape.
    """

    def ingest(self, raw_event: object) -> SessionEvent:
        """Convert a StreamEvent from engine.capture.watchers into a SessionEvent.

        The output shape is intentionally source-agnostic — 'event_type' maps
        directly, 'content' maps directly, and no Claude-specific field names
        appear in the serialized result.
        """
        # Accept both StreamEvent dataclass and plain dict (for test convenience)
        if hasattr(raw_event, "event_type"):
            event_type = raw_event.event_type  # type: ignore[union-attr]
            content = raw_event.content  # type: ignore[union-attr]
            session_id = getattr(raw_event, "session_id", None) or str(uuid.uuid4())
            timestamp = getattr(raw_event, "timestamp", None) or datetime.now(timezone.utc)
            metadata = getattr(raw_event, "metadata", None)
        else:
            raw = raw_event  # type: ignore[assignment]
            event_type = raw.get("event_type", "text")  # type: ignore[union-attr]
            content = raw.get("content", "")  # type: ignore[union-attr]
            session_id = raw.get("session_id") or str(uuid.uuid4())  # type: ignore[union-attr]
            timestamp = raw.get("timestamp") or datetime.now(timezone.utc)  # type: ignore[union-attr]
            metadata = raw.get("metadata")  # type: ignore[union-attr]

        return SessionEvent(
            id=str(uuid.uuid4()),
            session_id=session_id,
            event_type=event_type,
            content=content,
            timestamp=timestamp,
            metadata=metadata,
        )

    def enumerate_turns(self, session_id: str) -> list[SessionTurn]:
        """Turn enumeration not yet implemented for Claude Code sessions."""
        return []
