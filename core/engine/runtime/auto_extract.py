"""Auto-extraction — delegates to ACE's capture pipeline via events.

Instead of reimplementing the Observer's LLM evaluation and DB writes,
emits turn data as events. The existing capture pipeline (Observer +
Synthesizer) handles evaluation, dedup, conflict detection, and graph writes.

Fire-and-forget: never blocks the next user turn.
"""

from __future__ import annotations

import asyncio
import logging

from core.engine.runtime.models import AssistantMessage, Message, UserMessage

try:
    from core.engine.events.bus import bus as event_bus
except ImportError:
    event_bus = None

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 100


class AutoExtractor:
    """Emits turn data for the capture pipeline to process."""

    def __init__(self, product_id: str = "product:platform") -> None:
        self._org_id = product_id
        self._pending: asyncio.Task | None = None

    async def extract(self, messages: list[Message]) -> list[dict]:
        """Emit turn data as an event for the capture pipeline."""
        relevant = [m for m in messages if isinstance(m, (UserMessage, AssistantMessage))]
        if not relevant:
            return []

        total_content = sum(len(m.content) for m in relevant)
        if total_content < MIN_CONTENT_LENGTH:
            return []

        # Build turn text for the capture pipeline
        turn_text = "\n".join(
            f"{'User' if isinstance(m, UserMessage) else 'Assistant'}: {m.content[:2000]}" for m in relevant[-6:]
        )

        # Emit event — the capture pipeline's Observer handles evaluation,
        # the Synthesizer handles graph writes with dedup/conflict logic
        if event_bus:
            await event_bus.emit(
                "runtime.turn_for_capture",
                {
                    "product_id": self._org_id,
                    "turn_text": turn_text,
                    "message_count": len(relevant),
                    "source": "runtime_auto_extract",
                },
            )

        # Also emit the existing observations_captured event for backward compat
        if event_bus:
            await event_bus.emit(
                "runtime.observations_captured",
                {
                    "count": 0,  # actual count determined by capture pipeline
                    "source": "event_delegation",
                },
            )

        return []  # capture pipeline handles the actual observations

    def fire_and_forget(self, messages: list[Message]) -> None:
        """Extract without blocking."""
        try:
            loop = asyncio.get_running_loop()
            if self._pending and not self._pending.done():
                self._pending.cancel()
            self._pending = loop.create_task(self.extract(messages))
        except RuntimeError:
            logger.debug("No event loop for fire_and_forget extraction")
