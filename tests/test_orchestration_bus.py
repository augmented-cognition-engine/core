# tests/test_orchestration_bus.py
"""Unit tests for the OrchestrationBus inter-agent message bus."""

import asyncio

import pytest

from core.engine.orchestration.bus import BusMessage, MessageType, OrchestrationBus


@pytest.mark.asyncio
async def test_bus_targeted_message():
    """Targeted messages go to the right subscriber only."""
    bus = OrchestrationBus()
    received_a, received_b = [], []

    async def handler_a(msg):
        received_a.append(msg)

    async def handler_b(msg):
        received_b.append(msg)

    bus.subscribe("agent_a", handler_a)
    bus.subscribe("agent_b", handler_b)

    await bus.publish(
        BusMessage(
            type=MessageType.DISCOVERY,
            source_agent_id="agent_a",
            target_agent_id="agent_b",
            run_id="run1",
            payload={"content": "found something"},
        )
    )
    await asyncio.sleep(0.05)

    assert len(received_b) == 1
    assert len(received_a) == 0


@pytest.mark.asyncio
async def test_bus_broadcast_excludes_sender():
    """Broadcast reaches all except the sender."""
    bus = OrchestrationBus()
    received_a, received_b = [], []

    async def handler_a(msg):
        received_a.append(msg)

    async def handler_b(msg):
        received_b.append(msg)

    bus.subscribe("agent_a", handler_a)
    bus.subscribe("agent_b", handler_b)

    await bus.publish(
        BusMessage(
            type=MessageType.BROADCAST,
            source_agent_id="agent_a",
            run_id="run1",
            payload={"content": "status update"},
        )
    )
    await asyncio.sleep(0.05)

    assert len(received_b) == 1
    assert len(received_a) == 0


@pytest.mark.asyncio
async def test_bus_global_subscriber():
    """Global subscriber sees all messages."""
    bus = OrchestrationBus()
    all_msgs = []

    async def global_handler(msg):
        all_msgs.append(msg)

    bus.subscribe_global(global_handler)

    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a1", run_id="r1"))
    await bus.publish(BusMessage(type=MessageType.HANDOFF, source_agent_id="a2", run_id="r1"))
    await asyncio.sleep(0.05)

    assert len(all_msgs) == 2


@pytest.mark.asyncio
async def test_bus_capture_callback():
    """Capture callback receives all published messages."""
    captured = []

    async def capture(msg):
        captured.append(msg)

    bus = OrchestrationBus(capture_callback=capture)
    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a1", run_id="r1"))

    assert len(captured) == 1


@pytest.mark.asyncio
async def test_bus_message_log_query():
    """Message log is queryable by run_id and type."""
    bus = OrchestrationBus()
    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a1", run_id="run1"))
    await bus.publish(BusMessage(type=MessageType.HANDOFF, source_agent_id="a2", run_id="run1"))
    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a3", run_id="run2"))

    run1_msgs = bus.get_messages("run1")
    assert len(run1_msgs) == 2

    discoveries = bus.get_messages("run1", message_type=MessageType.DISCOVERY)
    assert len(discoveries) == 1


@pytest.mark.asyncio
async def test_bus_unsubscribe():
    """Unsubscribed agents don't receive messages."""
    bus = OrchestrationBus()
    received = []

    async def handler(msg):
        received.append(msg)

    bus.subscribe("agent_a", handler)
    bus.unsubscribe("agent_a")

    await bus.publish(BusMessage(type=MessageType.BROADCAST, source_agent_id="b", run_id="r"))
    await asyncio.sleep(0.05)
    assert len(received) == 0


@pytest.mark.asyncio
async def test_bus_clear_run():
    """clear_run removes messages for the specified run_id only."""
    bus = OrchestrationBus()
    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a1", run_id="run1"))
    await bus.publish(BusMessage(type=MessageType.DISCOVERY, source_agent_id="a2", run_id="run2"))

    bus.clear_run("run1")
    assert len(bus.get_messages("run1")) == 0
    assert len(bus.get_messages("run2")) == 1


@pytest.mark.asyncio
async def test_bus_broadcast_with_no_target():
    """A message with no target_agent_id is treated as broadcast."""
    bus = OrchestrationBus()
    received_a, received_b = [], []

    async def handler_a(msg):
        received_a.append(msg)

    async def handler_b(msg):
        received_b.append(msg)

    bus.subscribe("agent_a", handler_a)
    bus.subscribe("agent_b", handler_b)

    await bus.publish(
        BusMessage(
            type=MessageType.DISCOVERY,
            source_agent_id="agent_c",
            run_id="run1",
        )
    )
    await asyncio.sleep(0.05)

    # Both receive because sender is a different agent
    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_bus_message_frozen():
    """BusMessage instances are immutable (frozen dataclass)."""
    msg = BusMessage(type=MessageType.DISCOVERY, source_agent_id="a1", run_id="r1")
    with pytest.raises(AttributeError):
        msg.run_id = "changed"


@pytest.mark.asyncio
async def test_bus_global_plus_targeted():
    """Global subscriber sees targeted messages too."""
    bus = OrchestrationBus()
    global_msgs = []
    target_msgs = []

    async def global_handler(msg):
        global_msgs.append(msg)

    async def target_handler(msg):
        target_msgs.append(msg)

    bus.subscribe_global(global_handler)
    bus.subscribe("agent_b", target_handler)

    await bus.publish(
        BusMessage(
            type=MessageType.DISCOVERY,
            source_agent_id="agent_a",
            target_agent_id="agent_b",
            run_id="r1",
        )
    )
    await asyncio.sleep(0.05)

    assert len(global_msgs) == 1
    assert len(target_msgs) == 1
