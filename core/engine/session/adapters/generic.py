"""GenericAdapter — passthrough adapter for unrecognized or future sources.

Acts as the registry fallback so adding a new tool never crashes the pipeline —
it degrades gracefully until a purpose-built adapter ships.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.engine.session.models import SessionEvent, SessionTurn


class GenericAdapter:
    """Passthrough adapter for unknown source strings.

    Normalizes any dict or object with an 'event_type' and 'content' field
    into a SessionEvent. Returns empty turns list — no turn reconstruction.
    """

    def ingest(self, raw_event: object) -> SessionEvent:
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
        return []
