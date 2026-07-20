# engine/orchestration/__init__.py
"""ACE Orchestration Layer -- Event-driven agent execution spine.

Every ACE component goes through this layer:
  - Chat: orchestration.stream(OrchestrationRequest.from_chat(...))
  - Runner: orchestration.orchestrate(OrchestrationRequest.from_runner(...))
  - Evolution: orchestration.orchestrate(OrchestrationRequest.from_evolution(...))
  - Direct API: orchestration.orchestrate(OrchestrationRequest(...))

Agent creation is private to this layer. The layer is model-agnostic.
"""

from __future__ import annotations

from typing import AsyncIterator

from core.engine.orchestration.events import OrchestratorEvent
from core.engine.orchestration.executor import OrchestrationResult, run
from core.engine.orchestration.request import OrchestrationRequest


async def orchestrate(request: OrchestrationRequest) -> OrchestrationResult:
    """Execute task through orchestration layer. Returns final result."""
    return await run(request)


async def stream(request: OrchestrationRequest) -> AsyncIterator[OrchestratorEvent]:
    """Execute task, yielding events as they occur. For SSE streaming.

    Starts the orchestration in a background task, yields events from
    the EventBus as they arrive. When the run completes, yields the
    final TaskCompleted or TaskFailed event and stops.
    """
    import asyncio
    import uuid

    from core.engine.orchestration.events import EventBus

    # Create a shared EventBus that both the run and the consumer use.
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    bus = EventBus(run_id=run_id, product_id=request.product_id)

    # Subscribe BEFORE starting the run so no events are lost.
    event_iter = await bus.subscribe()

    async def _run_with_shared_bus() -> None:
        await run(request, event_bus=bus)
        # Signal the bus to close so the subscriber iterator terminates
        # after it has drained all queued events.
        await bus.close()

    # Start run in background
    task = asyncio.create_task(_run_with_shared_bus())

    # Yield events as they arrive
    try:
        async for event in event_iter:
            yield event
            # Also stop after terminal events as a safety net
            if event.event_type in ("task_completed", "task_failed"):
                break
    finally:
        # Ensure the background task completes even if the consumer stops early
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
