"""Tests for the event bus and automation handlers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


def test_bus_register_and_emit():
    from core.engine.events.bus import EventBus

    bus = EventBus()
    received = []

    async def handler(event_type, payload):
        received.append((event_type, payload))

    bus.on("test.event", handler)
    assert "test.event" in bus.list_handlers()
    assert "handler" in bus.list_handlers()["test.event"]


def test_bus_off_removes_handler():
    from core.engine.events.bus import EventBus

    bus = EventBus()

    async def handler(event_type, payload):
        pass

    bus.on("test.event", handler)
    assert len(bus._handlers["test.event"]) == 1
    bus.off("test.event", handler)
    assert len(bus._handlers["test.event"]) == 0


@pytest.mark.asyncio
async def test_bus_emit_calls_handlers():
    from core.engine.events.bus import EventBus

    bus = EventBus()
    received = []

    async def handler(event_type, payload):
        received.append(payload)

    bus.on("test.event", handler)
    await bus.emit("test.event", {"key": "value"})
    # Give the background task time to run
    await asyncio.sleep(0.1)
    assert len(received) == 1
    assert received[0]["key"] == "value"


@pytest.mark.asyncio
async def test_bus_emit_handles_handler_failure():
    from core.engine.events.bus import EventBus

    bus = EventBus()

    async def bad_handler(event_type, payload):
        raise RuntimeError("boom")

    async def good_handler(event_type, payload):
        pass  # Should still run

    bus.on("test.event", bad_handler)
    bus.on("test.event", good_handler)

    # Should not raise
    await bus.emit("test.event", {})
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_bus_emit_no_handlers_is_noop():
    from core.engine.events.bus import EventBus

    bus = EventBus()
    # Should not raise
    await bus.emit("nonexistent.event", {"data": 1})


def test_register_builtin_handlers():
    from core.engine.events.bus import bus

    # Clear any existing handlers
    bus._handlers.clear()

    from core.engine.events.automations import register_builtin_handlers

    register_builtin_handlers()

    handlers = bus.list_handlers()
    assert "idea.state_changed" in handlers
    assert "maturation.phase_changed" in handlers
    assert "insight.conflict" in handlers
    assert "specialty.emerged" in handlers

    # Clean up
    bus._handlers.clear()


@pytest.mark.asyncio
async def test_on_idea_ready_sends_notification(monkeypatch):
    mock_dispatch = AsyncMock(return_value={})

    import core.engine.notifications.dispatcher as disp_module

    monkeypatch.setattr(disp_module, "dispatch", mock_dispatch)

    from core.engine.events.automations import on_idea_ready

    await on_idea_ready(
        "idea.state_changed",
        {
            "new_state": "ready",
            "product_id": "product:default",
            "idea_id": "idea:123",
            "title": "Build webhook system",
        },
    )
    assert mock_dispatch.called
    assert "ready" in mock_dispatch.call_args.kwargs.get("title", "")


@pytest.mark.asyncio
async def test_on_idea_ready_ignores_other_states():
    from core.engine.events.automations import on_idea_ready

    # Should not raise or do anything
    await on_idea_ready(
        "idea.state_changed",
        {
            "new_state": "qualifying",
            "product_id": "product:default",
        },
    )
