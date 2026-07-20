"""Ephemeral streaming event types for the ACE Runtime.

These types exist during streaming and are never persisted to transcripts
or conversation history. Separate from models.py (durable message types).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThinkingDelta:
    """Partial thinking block content yielded during streaming.

    Yielded by ClaudeAdapter.stream_model() when the model emits a
    thinking_delta event. Never stored in self._messages or JSONL transcripts.
    """

    content: str
