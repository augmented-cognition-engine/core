"""Tests for thread.committed + thread.resolved canvas events."""

from __future__ import annotations

import asyncio

import pytest

from core.engine.events.bus import EventBus
from core.engine.events.canvas import (
    LivingCanvasEventType,
    emit_thread_committed,
    emit_thread_resolved,
)


def test_thread_committed_enum_value():
    assert LivingCanvasEventType.THREAD_COMMITTED.value == "thread.committed"


def test_thread_resolved_enum_value():
    assert LivingCanvasEventType.THREAD_RESOLVED.value == "thread.resolved"


@pytest.mark.asyncio
async def test_emit_thread_committed_fires_on_bus():
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        received.append(payload)

    local_bus.on("canvas.thread.committed", handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_thread_committed(
            product_id="product:test",
            thread_id="voice_thread:abc",
            topic="ux",
            action_id="voice_thread_action:xyz",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1
    payload = received[0]["payload"]
    assert payload["thread_id"] == "voice_thread:abc"
    assert payload["topic"] == "ux"
    assert payload["product_id"] == "product:test"
    assert payload["action_id"] == "voice_thread_action:xyz"


@pytest.mark.asyncio
async def test_emit_thread_resolved_fires_on_bus():
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        received.append(payload)

    local_bus.on("canvas.thread.resolved", handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_thread_resolved(
            product_id="product:test",
            thread_id="voice_thread:abc",
            topic="ux",
            action_id="voice_thread_action:xyz",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1
    payload = received[0]["payload"]
    assert payload["thread_id"] == "voice_thread:abc"
    assert payload["topic"] == "ux"
    assert payload["product_id"] == "product:test"
    assert payload["action_id"] == "voice_thread_action:xyz"
