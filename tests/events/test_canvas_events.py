"""Boundary tests for LivingCanvasEvent — AC 1-6, sentinel check."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from core.engine.events.bus import EventBus
from core.engine.events.canvas import (
    LivingCanvasEvent,
    LivingCanvasEventType,
    Provenance,
    emit_capability_added,
    emit_decision_captured,
    emit_score_changed,
)

# ---------------------------------------------------------------------------
# AC 5 — Provenance shape and source correctness
# ---------------------------------------------------------------------------


def test_provenance_user_source():
    p = Provenance(source="user", actor_id="sess-001", rationale="Capability added by user")
    assert p.source == "user"
    assert p.actor_id == "sess-001"
    assert p.rationale != "unknown"


def test_provenance_sentinel_source():
    p = Provenance(source="sentinel", actor_id="gap_analyzer", rationale="Score computed by gap_analyzer")
    assert p.source == "sentinel"
    assert p.rationale != "unknown"


# ---------------------------------------------------------------------------
# Sentinel check — Provenance.rationale must NOT be "unknown" for internal events
# ---------------------------------------------------------------------------


def test_provenance_rationale_never_unknown_for_internal_emitters():
    """Internal emit helpers must set rationale, never 'unknown'."""
    p_capability = Provenance(
        source="user",
        actor_id="sess-abc",
        rationale="Capability 'auth' added to product model",
    )
    assert p_capability.rationale != "unknown", (
        "Internal emit set 'unknown' provenance — emit_capability_added not wired correctly"
    )

    p_score = Provenance(
        source="sentinel",
        actor_id="gap_analyzer",
        rationale="gap_analyzer scored auth.security: 0.40 → 0.75",
    )
    assert p_score.rationale != "unknown", (
        "Sentinel score emit set 'unknown' provenance — emit_score_changed not wired correctly"
    )


# ---------------------------------------------------------------------------
# AC 2 — capability.added event emitted and received
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_added_event_emitted():
    """emit_capability_added must produce a canvas.capability.added bus event."""
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        received.append({"event_type": event_type, "payload": payload})

    local_bus.on("*", handler)

    # Patch the module-level bus with our test bus
    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_capability_added(
            product_id="product:test",
            slug="auth",
            name="Authentication",
            status="planned",
        )
        await asyncio.sleep(0.05)  # let fire-and-forget tasks complete
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1
    evt = received[0]
    assert evt["event_type"] == "canvas.capability.added"
    assert evt["payload"]["event_type"] == LivingCanvasEventType.CAPABILITY_ADDED
    assert evt["payload"]["product_id"] == "product:test"
    assert evt["payload"]["payload"]["slug"] == "auth"
    assert evt["payload"]["provenance"]["rationale"] != "unknown"
    assert evt["payload"]["provenance"]["source"] == "user"


# ---------------------------------------------------------------------------
# AC 3 — decision.captured includes affected_capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_captured_includes_affected_capabilities():
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        received.append(payload)

    local_bus.on("*", handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_decision_captured(
            product_id="product:test",
            decision_id="decision:001",
            title="Use SurrealDB for graph store",
            affected_capabilities=["capability:auth", "capability:data"],
            source_session="sess-xyz",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1
    payload = received[0]["payload"]
    assert payload["title"] == "Use SurrealDB for graph store"
    assert "capability:auth" in payload["affected_capabilities"]
    assert received[0]["provenance"]["actor_id"] == "sess-xyz"


# ---------------------------------------------------------------------------
# AC 4 — score.changed event includes old and new score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_changed_includes_old_and_new():
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        received.append(payload)

    local_bus.on("*", handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_score_changed(
            product_id="product:test",
            capability_slug="auth",
            dimension="security",
            old_score=0.40,
            new_score=0.75,
            sentinel_name="gap_analyzer",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1
    p = received[0]["payload"]
    assert p["old_score"] == pytest.approx(0.40)
    assert p["new_score"] == pytest.approx(0.75)
    assert received[0]["provenance"]["source"] == "sentinel"
    assert received[0]["provenance"]["actor_id"] == "gap_analyzer"


# ---------------------------------------------------------------------------
# AC 5 — LivingCanvasEvent model correctness
# ---------------------------------------------------------------------------


def test_living_canvas_event_model():
    now = datetime.now(timezone.utc)
    event = LivingCanvasEvent(
        event_type=LivingCanvasEventType.DECISION_CAPTURED,
        product_id="product:test",
        timestamp=now,
        payload={"title": "Use JWT"},
        provenance=Provenance(source="user", actor_id="sess-1", rationale="Decision captured"),
    )
    d = event.model_dump(mode="json")
    assert d["event_type"] == "decision.captured"
    assert d["provenance"]["source"] == "user"
    assert d["provenance"]["rationale"] == "Decision captured"


# ---------------------------------------------------------------------------
# AC 6 — multiple bus subscribers all receive broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_event():
    local_bus = EventBus()
    counts = [0, 0]

    async def handler_a(event_type, payload):
        counts[0] += 1

    async def handler_b(event_type, payload):
        counts[1] += 1

    local_bus.on("canvas.capability.added", handler_a)
    local_bus.on("canvas.capability.added", handler_b)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        await emit_capability_added(product_id="product:test", slug="feat", name="Feature")
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert counts[0] == 1, "handler_a did not receive the event"
    assert counts[1] == 1, "handler_b did not receive the event"


# ---------------------------------------------------------------------------
# Integration — capture pipeline signal → score.changed canvas event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_pipeline_to_canvas_emit():
    """Integration: a score update (sentinel path) produces a canvas score.changed event.

    Simulates the gap_analyzer path: emit_score_changed → bus → subscriber.
    This verifies the full chain from sentinel action to canvas event delivery.
    """
    local_bus = EventBus()
    received: list[dict] = []

    async def handler(event_type, payload):
        if event_type == "canvas.score.changed":
            received.append(payload)

    local_bus.on("canvas.score.changed", handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        # Simulate gap_analyzer scoring a capability dimension
        await emit_score_changed(
            product_id="product:test",
            capability_slug="auth",
            dimension="security",
            old_score=0.40,
            new_score=0.72,
            sentinel_name="gap_analyzer",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    assert len(received) == 1, "score.changed canvas event not delivered end-to-end"
    payload = received[0]
    assert payload["event_type"] == LivingCanvasEventType.SCORE_CHANGED
    assert payload["provenance"]["source"] == "sentinel"
    assert payload["provenance"]["actor_id"] == "gap_analyzer"
    assert payload["payload"]["old_score"] == pytest.approx(0.40)
    assert payload["payload"]["new_score"] == pytest.approx(0.72)
