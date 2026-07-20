# tests/test_orchestration_events.py
"""Unit tests for the orchestration EventBus and event types."""

import asyncio

import pytest

from core.engine.orchestration.events import (
    AgentCompleted,
    AgentSpawned,
    ClassificationComplete,
    EventBus,
    TaskCompleted,
    TaskFailed,
    TaskReceived,
)


@pytest.mark.asyncio
async def test_event_bus_emit_and_collect():
    """Events emitted are stored and retrievable."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="test", source="direct"))
    assert len(bus.events()) == 1
    assert bus.events()[0].event_type == "task_received"


@pytest.mark.asyncio
async def test_event_bus_subscriber_receives_events():
    """Subscriber receives events via async iteration."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    received = []

    async def collect():
        iterator = await bus.subscribe()
        async for event in iterator:
            received.append(event)
            if len(received) >= 2:
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.01)
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="a", source="direct"))
    await bus.emit(
        AgentSpawned(run_id="test_run", product_id="product:test", agent_id="a1", role="exec", pattern_position="0")
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(received) == 2


@pytest.mark.asyncio
async def test_event_bus_filtered_subscribe():
    """Filtered subscriber only receives matching event types."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    received = []

    async def collect():
        iterator = await bus.subscribe(event_types=["agent_spawned"])
        async for event in iterator:
            received.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.01)
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="a", source="direct"))
    await bus.emit(
        AgentSpawned(run_id="test_run", product_id="product:test", agent_id="a1", role="exec", pattern_position="0")
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(received) == 1
    assert received[0].event_type == "agent_spawned"


def test_event_types_are_frozen():
    """Event instances are immutable."""
    event = TaskReceived(run_id="r", product_id="o", description="d", source="s")
    with pytest.raises(AttributeError):
        event.description = "changed"


def test_event_ids_are_unique():
    """Each event gets a unique ID."""
    e1 = TaskReceived(run_id="r", product_id="o", description="d", source="s")
    e2 = TaskReceived(run_id="r", product_id="o", description="d", source="s")
    assert e1.event_id != e2.event_id


@pytest.mark.asyncio
async def test_event_bus_events_returns_copy():
    """events() returns a copy, not the internal list."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="a", source="direct"))
    events = bus.events()
    events.clear()
    assert len(bus.events()) == 1


@pytest.mark.asyncio
async def test_event_bus_close_signals_subscribers():
    """Closing the bus causes subscribers to stop iteration."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    received = []

    async def collect():
        iterator = await bus.subscribe()
        async for event in iterator:
            received.append(event)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.01)
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="a", source="direct"))
    await bus.close()
    # Wait for the task to finish naturally via the None sentinel
    await asyncio.sleep(0.05)
    assert task.done() or task.cancelled()
    assert len(received) == 1


@pytest.mark.asyncio
async def test_event_bus_multiple_events():
    """Multiple event types can be emitted and all are recorded."""
    bus = EventBus(run_id="test_run", product_id="product:test")
    await bus.emit(TaskReceived(run_id="test_run", product_id="product:test", description="a", source="direct"))
    await bus.emit(
        ClassificationComplete(
            run_id="test_run", product_id="product:test", domain_path="d", archetype="a", mode="m", complexity="c"
        )
    )
    await bus.emit(TaskCompleted(run_id="test_run", product_id="product:test", task_id="t1", output_summary="done"))
    assert len(bus.events()) == 3
    types = [e.event_type for e in bus.events()]
    assert types == ["task_received", "classification_complete", "task_completed"]


def test_task_failed_event():
    """TaskFailed event can be constructed."""
    event = TaskFailed(run_id="r", product_id="o", error="boom", phase="execution")
    assert event.event_type == "task_failed"
    assert event.error == "boom"
    assert event.phase == "execution"


def test_agent_completed_event():
    """AgentCompleted event can be constructed."""
    event = AgentCompleted(
        run_id="r", product_id="o", agent_id="a1", role="exec", output_summary="done", duration_ms=100
    )
    assert event.event_type == "agent_completed"
    assert event.duration_ms == 100
