# engine/capture/chunker.py
"""Chunker — accumulates stream events into meaningful chunks.

Writes each emitted chunk to the memory table and yields (Chunk, memory_id).
The memory_id is passed to the Observer for provenance tracking.
memory_id is None until DB write is wired in Task 11.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, AsyncIterator

from core.engine.capture.watchers import Chunk, StreamEvent

# Simple token estimation: ~4 chars per token
_CHARS_PER_TOKEN = 4
_TOKEN_THRESHOLD = 500
_TOPIC_SHIFT_PHRASES = [
    "now let's",
    "moving on",
    "next step",
    "the next thing",
    "switching to",
    "let me now",
    "turning to",
    "on to",
    "that's done",
    "now i'll",
    "with that complete",
]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class Chunker:
    """Accumulates stream events and emits chunks on boundary signals."""

    def __init__(self) -> None:
        self._buffer: list[StreamEvent] = []
        self._token_count: int = 0
        self._lock = asyncio.Lock()
        self._db_pool = None  # Set via pipeline after construction
        self._org_id = None  # Set via pipeline after construction

    async def _write_memory(self, chunk: Chunk) -> str | None:
        """Write chunk to memory table, return native SurrealDB record ID."""
        if not self._db_pool:
            return None
        async with self._db_pool.connection() as db:
            result = await db.query(
                """
                CREATE memory SET
                    product = <record>$product,
                    content = $content,
                    memory_type = 'chunk',
                    source = 'capture_pipeline',
                    session_id = $session_id,
                    processed = false,
                    created_at = time::now()
                """,
                {
                    "product": self._org_id,
                    "content": chunk.content[:5000],
                    "session_id": chunk.events[0].session_id if chunk.events else None,
                },
            )
            from core.engine.core.db import parse_one

            row = parse_one(result)
            return row.get("id") if row else None

    async def process(self, events: AsyncIterator[StreamEvent]) -> AsyncGenerator[tuple[Chunk, str | None], None]:
        """Yield (Chunk, memory_id) tuples. memory_id is the SurrealDB record ID or None."""
        async for event in events:
            chunk = None
            async with self._lock:
                self._buffer.append(event)
                self._token_count += _estimate_tokens(event.content)

                if self._should_emit(event):
                    chunk = self._create_chunk()
                    self._buffer = []
                    self._token_count = 0
            if chunk:
                memory_id = await self._write_memory(chunk)
                yield (chunk, memory_id)

    def _should_emit(self, latest: StreamEvent) -> bool:
        if latest.event_type == "tool_result":
            return True
        if latest.event_type == "status":
            return True
        if latest.event_type == "error":
            return True
        if self._token_count > _TOKEN_THRESHOLD:
            return True
        if self._detects_topic_shift(latest.content):
            return True
        return False

    def _detects_topic_shift(self, text: str) -> bool:
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in _TOPIC_SHIFT_PHRASES)

    def _create_chunk(self) -> Chunk:
        if not self._buffer:
            raise RuntimeError("_create_chunk called with empty buffer")
        combined = "".join(e.content for e in self._buffer if e.content)
        event_types = {e.event_type for e in self._buffer}

        if "error" in event_types:
            chunk_type = "error"
        elif "tool_use" in event_types or "tool_result" in event_types:
            chunk_type = "action"
        else:
            chunk_type = "reasoning"

        return Chunk(
            content=combined,
            chunk_type=chunk_type,
            events=list(self._buffer),
            start_time=self._buffer[0].timestamp,
            end_time=self._buffer[-1].timestamp,
            token_count=self._token_count,
        )
