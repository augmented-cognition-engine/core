# engine/capture/watchers.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class StreamEvent:
    """A single event from an LLM session stream."""

    timestamp: datetime
    event_type: str  # text | tool_use | tool_result | error | status
    content: str
    session_id: str | None = None
    metadata: dict | None = None


@dataclass
class Chunk:
    """A meaningful unit of work assembled from stream events."""

    content: str
    chunk_type: str  # reasoning | action | error
    events: list[StreamEvent]
    start_time: datetime
    end_time: datetime
    token_count: int


@runtime_checkable
class StreamWatcher(Protocol):
    """Protocol for all capture sources."""

    async def watch(self) -> AsyncIterator[StreamEvent]: ...


class SessionImportWatcher:
    """Parses a transcript string into synthetic StreamEvents."""

    def __init__(self, transcript: str, session_id: str | None = None):
        self.transcript = transcript
        self.session_id = session_id or str(uuid.uuid4())

    async def watch(self) -> AsyncIterator[StreamEvent]:
        # Split transcript into paragraphs as synthetic events
        paragraphs = [p.strip() for p in self.transcript.split("\n\n") if p.strip()]
        for i, paragraph in enumerate(paragraphs):
            yield StreamEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="text",
                content=paragraph,
                session_id=self.session_id,
                metadata={"source": "session_import", "index": i},
            )
