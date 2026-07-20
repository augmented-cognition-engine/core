# engine/orchestration/bus.py
"""OrchestrationBus — in-memory async pub/sub for inter-agent coordination.

Agents publish ``BusMessage`` instances; the bus routes them to targeted
agents or broadcasts to all except the sender.  A capture callback feeds
messages into the event/observation pipeline.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

# decision:znalk48vc0rluxl1ejdg — use logged_task so handler exceptions
# land in error_buffer + logs instead of being silently discarded by GC.
from core.engine.core.tasks import logged_task


class MessageType(Enum):
    """All message types that can flow through the bus."""

    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    DISCOVERY = "discovery"
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    HANDOFF = "handoff"
    POSITION_SUBMITTED = "position_submitted"
    CHALLENGE_ISSUED = "challenge_issued"
    PARTIAL_RESULT = "partial_result"
    FINAL_RESULT = "final_result"
    CANCEL = "cancel"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class BusMessage:
    """Single message on the orchestration bus."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.BROADCAST
    source_agent_id: str = ""
    target_agent_id: str | None = None  # None = broadcast
    run_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None  # links request/response pairs


MessageHandler = Callable[[BusMessage], Awaitable[None]]


class OrchestrationBus:
    """In-memory async pub/sub for inter-agent coordination.

    - **Targeted** messages go only to handlers registered for the target agent.
    - **Broadcast** messages go to all registered agents *except* the sender.
    - **Global** subscribers see every message unconditionally.
    """

    def __init__(self, capture_callback: MessageHandler | None = None) -> None:
        self._subscribers: dict[str, list[MessageHandler]] = {}
        self._global_subscribers: list[MessageHandler] = []
        self._message_log: list[BusMessage] = []
        self._capture_callback = capture_callback
        self._lock = asyncio.Lock()

    async def publish(self, message: BusMessage) -> None:
        """Publish *message*. Routes to target or broadcasts. Always feeds capture."""
        async with self._lock:
            self._message_log.append(message)

        if self._capture_callback:
            await self._capture_callback(message)

        # Targeted delivery
        if message.target_agent_id:
            handlers = self._subscribers.get(message.target_agent_id, [])
            for handler in handlers:
                logged_task(handler(message), label="orchestration.bus.targeted_handler")
        else:
            # Broadcast to all except sender
            for agent_id, handlers in self._subscribers.items():
                if agent_id != message.source_agent_id:
                    for handler in handlers:
                        logged_task(handler(message), label="orchestration.bus.broadcast_handler")

        # Global subscribers always receive
        for handler in self._global_subscribers:
            logged_task(handler(message), label="orchestration.bus.global_handler")

    def subscribe(self, agent_id: str, handler: MessageHandler) -> None:
        """Register *handler* to receive messages targeted at *agent_id*."""
        self._subscribers.setdefault(agent_id, []).append(handler)

    def subscribe_global(self, handler: MessageHandler) -> None:
        """Register *handler* to receive every message on the bus."""
        self._global_subscribers.append(handler)

    def unsubscribe(self, agent_id: str) -> None:
        """Remove all handlers for *agent_id*."""
        self._subscribers.pop(agent_id, None)

    def get_messages(
        self,
        run_id: str,
        since: datetime | None = None,
        message_type: MessageType | None = None,
    ) -> list[BusMessage]:
        """Return logged messages for *run_id*, optionally filtered."""
        msgs = [m for m in self._message_log if m.run_id == run_id]
        if since:
            msgs = [m for m in msgs if m.timestamp > since]
        if message_type:
            msgs = [m for m in msgs if m.type == message_type]
        return msgs

    def clear_run(self, run_id: str) -> None:
        """Discard all logged messages for *run_id*."""
        self._message_log = [m for m in self._message_log if m.run_id != run_id]
