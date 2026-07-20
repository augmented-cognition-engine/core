# engine/orchestration/events.py
"""Orchestrator event types and EventBus.

Every orchestrate() call emits a stream of typed events that flow through
the EventBus. Subscribers (UI, capture, tests) consume them via async
iteration. All events are frozen dataclasses grouped by a shared run_id.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrchestratorEvent:
    """Base class for all orchestration events."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = ""
    product_id: str = ""
    event_type: str = ""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    seq: int = 0  # monotonic per-run sequence, assigned by EventBus.emit (0 = unsequenced)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for WS transport and DB persistence."""
        import dataclasses

        d = dataclasses.asdict(self)
        d["type"] = d.pop("event_type")
        d["ts"] = self.timestamp.isoformat()
        d.pop("timestamp", None)
        d.pop("event_id", None)
        return d


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskReceived(OrchestratorEvent):
    event_type: str = field(default="task_received", init=False)
    description: str = ""
    source: str = ""


@dataclass(frozen=True)
class ClassificationComplete(OrchestratorEvent):
    event_type: str = field(default="classification_complete", init=False)
    domain_path: str = ""
    archetype: str = ""
    mode: str = ""
    complexity: str = ""


@dataclass(frozen=True)
class IntelligenceLoaded(OrchestratorEvent):
    event_type: str = field(default="intelligence_loaded", init=False)
    insights_count: int = 0
    cross_domain_count: int = 0


@dataclass(frozen=True)
class PlanCreated(OrchestratorEvent):
    event_type: str = field(default="plan_created", init=False)
    pattern: str = ""
    agent_count: int = 0
    steps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskCompleted(OrchestratorEvent):
    event_type: str = field(default="task_completed", init=False)
    task_id: str = ""
    output_summary: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class TaskFailed(OrchestratorEvent):
    event_type: str = field(default="task_failed", init=False)
    error: str = ""
    phase: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentSpawned(OrchestratorEvent):
    event_type: str = field(default="agent_spawned", init=False)
    agent_id: str = ""
    role: str = ""
    pattern_position: str = ""


@dataclass(frozen=True)
class AgentToken(OrchestratorEvent):
    event_type: str = field(default="agent_token", init=False)
    agent_id: str = ""
    text: str = ""


@dataclass(frozen=True)
class AgentCompleted(OrchestratorEvent):
    event_type: str = field(default="agent_completed", init=False)
    agent_id: str = ""
    role: str = ""
    output_summary: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class AgentFailed(OrchestratorEvent):
    event_type: str = field(default="agent_failed", init=False)
    agent_id: str = ""
    role: str = ""
    error: str = ""


# Multi-spin engagement events


@dataclass(frozen=True)
class SpinStarted(OrchestratorEvent):
    event_type: str = field(default="spin_started", init=False)
    spin: int = 0
    total: int = 0
    perspective: str = ""


@dataclass(frozen=True)
class SpinCompleted(OrchestratorEvent):
    event_type: str = field(default="spin_completed", init=False)
    spin: int = 0
    perspective: str = ""
    handoff: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class SynthesisStarted(OrchestratorEvent):
    event_type: str = field(default="synthesis_started", init=False)
    perspectives: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Coordination events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Discovery(OrchestratorEvent):
    event_type: str = field(default="discovery", init=False)
    agent_id: str = ""
    content: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class Blocker(OrchestratorEvent):
    event_type: str = field(default="blocker", init=False)
    agent_id: str = ""
    content: str = ""
    severity: str = ""


@dataclass(frozen=True)
class Handoff(OrchestratorEvent):
    event_type: str = field(default="handoff", init=False)
    from_agent: str = ""
    to_agent: str = ""
    context_summary: str = ""


@dataclass(frozen=True)
class Message(OrchestratorEvent):
    event_type: str = field(default="message", init=False)
    from_agent: str = ""
    to_agent_or_topic: str = ""
    content: str = ""


@dataclass(frozen=True)
class Replan(OrchestratorEvent):
    event_type: str = field(default="replan", init=False)
    reason: str = ""
    old_plan_summary: str = ""
    new_plan_summary: str = ""


# ---------------------------------------------------------------------------
# Hook events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HookStarted(OrchestratorEvent):
    event_type: str = field(default="hook_started", init=False)
    hook_name: str = ""


@dataclass(frozen=True)
class HookCompleted(OrchestratorEvent):
    event_type: str = field(default="hook_completed", init=False)
    hook_name: str = ""
    result_summary: str = ""


# ---------------------------------------------------------------------------
# A.7 — Orchestration channel events (canvas pipeline transparency)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunStart(OrchestratorEvent):
    event_type: str = field(default="run_start", init=False)
    session_id: str = ""
    user_message: str = ""


@dataclass(frozen=True)
class RunDone(OrchestratorEvent):
    event_type: str = field(default="run_done", init=False)
    duration_ms: int = 0


@dataclass(frozen=True)
class RunError(OrchestratorEvent):
    event_type: str = field(default="run_error", init=False)
    error: str = ""
    recovery_hint: str = ""


@dataclass(frozen=True)
class RunCancelled(OrchestratorEvent):
    event_type: str = field(default="run_cancelled", init=False)


@dataclass(frozen=True)
class BlockStart(OrchestratorEvent):
    event_type: str = field(default="block_start", init=False)
    block_name: str = ""
    layer: int = 0


@dataclass(frozen=True)
class BlockDone(OrchestratorEvent):
    event_type: str = field(default="block_done", init=False)
    block_name: str = ""
    duration_ms: int = 0
    summary: str = ""


@dataclass(frozen=True)
class ClaudeCallStart(OrchestratorEvent):
    event_type: str = field(default="claude_call_start", init=False)
    purpose: str = ""
    model: str = ""
    prompt_tokens_estimate: int = 0


@dataclass(frozen=True)
class ClaudeCallDone(OrchestratorEvent):
    event_type: str = field(default="claude_call_done", init=False)
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    duration_ms: int = 0


@dataclass(frozen=True)
class Token(OrchestratorEvent):
    event_type: str = field(default="token", init=False)
    content: str = ""


@dataclass(frozen=True)
class Classification(OrchestratorEvent):
    event_type: str = field(default="classification", init=False)
    discipline: str = ""
    archetypes: tuple[str, ...] = ()
    depth: int = 1
    mode: str = ""
    complexity: str = ""


@dataclass(frozen=True)
class EngagementStart(OrchestratorEvent):
    event_type: str = field(default="engagement_start", init=False)
    pattern: str = ""
    archetypes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngagementDone(OrchestratorEvent):
    event_type: str = field(default="engagement_done", init=False)


@dataclass(frozen=True)
class AgentLoopStart(OrchestratorEvent):
    event_type: str = field(default="agent_loop_start", init=False)
    agent_archetype: str = ""
    tools_allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentLoopDone(OrchestratorEvent):
    event_type: str = field(default="agent_loop_done", init=False)
    outcome: str = ""
    tool_call_count: int = 0


@dataclass(frozen=True)
class ToolCallEvent(OrchestratorEvent):
    event_type: str = field(default="tool_call", init=False)
    tool: str = ""
    input_summary: str = ""


@dataclass(frozen=True)
class ToolResultEvent(OrchestratorEvent):
    event_type: str = field(default="tool_result", init=False)
    tool: str = ""
    summary: str = ""


@dataclass(frozen=True)
class AtcLock(OrchestratorEvent):
    event_type: str = field(default="atc_lock", init=False)
    capabilities: tuple[str, ...] = ()
    flight_id: str = ""


@dataclass(frozen=True)
class AtcBlocked(OrchestratorEvent):
    event_type: str = field(default="atc_blocked", init=False)
    capabilities: tuple[str, ...] = ()
    held_by_flight_id: str = ""
    est_release_ms: int = 0


@dataclass(frozen=True)
class AtcRelease(OrchestratorEvent):
    event_type: str = field(default="atc_release", init=False)
    flight_id: str = ""


@dataclass(frozen=True)
class DecisionCaptured(OrchestratorEvent):
    event_type: str = field(default="decision_captured", init=False)
    decision_id: str = ""


@dataclass(frozen=True)
class PredictionAttached(OrchestratorEvent):
    event_type: str = field(default="prediction_attached", init=False)
    prediction_id: str = ""
    horizon_days: int = 0
    falsification_condition: str = ""


@dataclass(frozen=True)
class SentinelEvent(OrchestratorEvent):
    event_type: str = field(default="sentinel_event", init=False)
    engine: str = ""
    severity: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# EventBus persistence helper
# ---------------------------------------------------------------------------


async def _persist_event(event_dict: dict) -> None:
    """Write a single event dict to the run_event table. Patchable in tests."""
    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            await db.query(
                """CREATE run_event SET
                    run_id = $run_id,
                    task_id = $task_id,
                    parent_id = $parent_id,
                    seq = $seq,
                    ts = time::now(),
                    type = $type,
                    payload = $payload
                """,
                {
                    "run_id": event_dict.get("run_id"),
                    "task_id": event_dict.get("task_id"),
                    "parent_id": event_dict.get("parent_id"),
                    "seq": int(event_dict.get("seq") or 0),
                    "type": event_dict.get("type"),
                    "payload": {
                        k: v
                        for k, v in event_dict.items()
                        if k not in ("run_id", "task_id", "parent_id", "seq", "type", "ts")
                    },
                },
            )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("run_event persist failed", exc_info=True)


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class _Subscription:
    """Internal: wraps an asyncio.Queue with optional type filtering."""

    __slots__ = ("queue", "event_types")

    def __init__(self, event_types: list[str] | None = None) -> None:
        self.queue: asyncio.Queue[OrchestratorEvent | None] = asyncio.Queue()
        self.event_types = set(event_types) if event_types else None

    def accepts(self, event: OrchestratorEvent) -> bool:
        if self.event_types is None:
            return True
        return event.event_type in self.event_types


class EventBus:
    """Async pub/sub for orchestrator lifecycle events.

    Each ``subscribe()`` call returns an ``AsyncIterator`` backed by its
    own ``asyncio.Queue`` so multiple consumers can read independently.

    Persistence runs on a background drain task: ``emit()`` never awaits the
    database. A single worker consumes the queue in order, so ``run_event``
    rows land in ``seq`` order even when individual writes vary in latency.
    """

    def __init__(self, run_id: str, product_id: str, persist_events: bool = False) -> None:
        self.run_id = run_id
        self.product_id = product_id
        self.persist_events = persist_events
        self._log: list[OrchestratorEvent] = []
        self._subscriptions: list[_Subscription] = []
        self._seq = 0
        self._persist_queue: asyncio.Queue[dict | None] | None = None
        self._persist_task: asyncio.Task[None] | None = None

    def _ensure_persist_worker(self) -> None:
        """Lazily start the drain task on first persisted emit."""
        if not self.persist_events or self._persist_task is not None:
            return
        self._persist_queue = asyncio.Queue()
        self._persist_task = asyncio.create_task(self._persist_worker())

    async def _persist_worker(self) -> None:
        """Drain the persist queue in FIFO order until the sentinel arrives."""
        queue = self._persist_queue
        assert queue is not None
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                await _persist_event(item)
            finally:
                queue.task_done()

    async def emit(self, event: OrchestratorEvent) -> None:
        """Assign seq, deliver to subscribers, enqueue for persistence."""
        self._seq += 1
        object.__setattr__(event, "seq", self._seq)  # frozen dataclass — bypass setattr guard
        self._log.append(event)
        for sub in self._subscriptions:
            if sub.accepts(event):
                sub.queue.put_nowait(event)
        if self.persist_events:
            self._ensure_persist_worker()
            assert self._persist_queue is not None
            self._persist_queue.put_nowait(event.to_dict())

    async def drain(self) -> None:
        """Block until every enqueued event has been persisted."""
        if self._persist_queue is not None:
            await self._persist_queue.join()

    async def subscribe(self, event_types: list[str] | None = None) -> AsyncIterator[OrchestratorEvent]:
        """Return an async iterator that yields events as they arrive.

        If *event_types* is provided only matching events are delivered.
        Send ``None`` into the subscription queue to signal completion.
        """
        sub = _Subscription(event_types)
        self._subscriptions.append(sub)

        async def _iterate() -> AsyncIterator[OrchestratorEvent]:
            try:
                while True:
                    event = await sub.queue.get()
                    if event is None:
                        break
                    yield event
            finally:
                if sub in self._subscriptions:
                    self._subscriptions.remove(sub)

        return _iterate()

    async def close(self) -> None:
        """Drain persistence, stop the worker, then signal all subscribers."""
        if self._persist_task is not None:
            await self.drain()
            assert self._persist_queue is not None
            self._persist_queue.put_nowait(None)
            await self._persist_task
            self._persist_task = None
            self._persist_queue = None
        for sub in self._subscriptions:
            sub.queue.put_nowait(None)

    def events(self) -> list[OrchestratorEvent]:
        """Return a copy of all events emitted so far."""
        return list(self._log)
