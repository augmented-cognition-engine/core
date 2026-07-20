"""Session — source-agnostic session model.

Session is the first-class entity the capture pipeline and orchestrator
operate against. All tool-specific shapes (Claude Code transcripts, Cursor
events, etc.) normalize into these dataclasses via SessionAdapter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SessionEvent:
    """A single normalized event, source-agnostic."""

    id: str
    session_id: str
    event_type: str  # text | tool_use | tool_result | error | status
    content: str
    timestamp: datetime
    metadata: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class SessionTurn:
    """A complete exchange: one human message + one assistant response."""

    turn_index: int
    human: str
    assistant: str
    events: list[SessionEvent]
    started_at: datetime
    ended_at: datetime

    def to_dict(self) -> dict:
        return {
            "turn_index": self.turn_index,
            "human": self.human,
            "assistant": self.assistant,
            "events": [e.to_dict() for e in self.events],
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
        }


@dataclass
class Session:
    """First-class session entity, source-agnostic.

    ``source`` identifies the originating tool ("claude_code", "cursor", etc.)
    and determines which SessionAdapter the registry returns.
    """

    id: str
    product_id: str
    source: str  # "claude_code" | "cursor" | "generic" | ...
    started_at: datetime
    turns: list[SessionTurn] = field(default_factory=list)
    events: list[SessionEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "source": self.source,
            "started_at": self.started_at.isoformat(),
            "turns": [t.to_dict() for t in self.turns],
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_raw_claude_event(cls, raw_event: dict, product_id: str = "") -> "Session":
        """Construct a Session from a raw Claude Code transcript event dict.

        Used for testing the sentinel check — confirms normalization erases
        tool-specific field names from the serialized form.
        """
        from core.engine.capture.watchers import StreamEvent
        from core.engine.session.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        stream_event = StreamEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=raw_event.get("event_type", "text"),
            content=raw_event.get("content", ""),
            session_id=raw_event.get("session_id"),
            metadata=raw_event.get("metadata"),
        )
        session_event = adapter.ingest(stream_event)
        return cls(
            id=session_event.session_id,
            product_id=product_id,
            source="claude_code",
            started_at=datetime.now(timezone.utc),
            events=[session_event],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
