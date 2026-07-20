from unittest.mock import AsyncMock, patch

import pytest


def _make_spin(perspective: str, content: str = "analysis", confidence: float = 0.8):
    from core.engine.orchestrator.engagement_models import SpinOutput

    return SpinOutput(
        content=content,
        handoff=f"handoff from {perspective}",
        confidence=confidence,
        open_questions=[],
        perspective=perspective,
    )


async def _fake_stream_spin_factory(spin):
    """Return a _stream_spin_content stub that emits the spin content as one delta."""

    async def _fake(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        await on_delta(spin.content)
        return spin

    return _fake


@pytest.mark.asyncio
async def test_single_perspective_emits_start_token_end():
    """Streaming path: start → token delta(s) → end (no step event)."""
    events = []

    async def on_event(event_type, payload):
        events.append((event_type, payload))

    classification = {
        "mode": "deliberative",
        "engagement": {"perspectives": ["analyst"], "adversarial_pair": None},
        "specialties": [],
    }

    spin = _make_spin("analyst", "my analysis")

    async def fake_stream_spin(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        await on_delta(spin.content)
        return spin

    with patch("core.engine.canvas.canvas_engagement._stream_spin_content", new=fake_stream_spin):
        from core.engine.canvas.canvas_engagement import run_canvas_engagement

        result = await run_canvas_engagement(
            task="Should we use Redis or Memcached?",
            classification=classification,
            product_id="product:test",
            on_canvas_event=on_event,
        )

    event_types = [e[0] for e in events]
    assert event_types == [
        "agent.perspective.start",
        "agent.perspective.token",
        "agent.perspective.end",
    ], f"Expected ordered sequence, got: {event_types}"
    assert result == "my analysis"
    assert "synthesis.start" not in event_types
    assert "agent.perspective.step" not in event_types


@pytest.mark.asyncio
async def test_two_perspectives_emits_synthesis():
    events = []

    async def on_event(event_type, payload):
        events.append((event_type, payload))

    classification = {
        "mode": "deliberative",
        "engagement": {"perspectives": ["analyst", "sentinel"], "adversarial_pair": None},
        "specialties": [],
    }

    spin_a = _make_spin("analyst")
    spin_b = _make_spin("sentinel")
    spin_map = {"analyst": spin_a, "sentinel": spin_b}

    async def fake_stream_spin_multi(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        spin = spin_map[perspective]
        await on_delta(spin.content)
        return spin

    with (
        patch("core.engine.canvas.canvas_engagement._stream_spin_content", new=fake_stream_spin_multi),
        patch("core.engine.canvas.canvas_engagement.synthesize_spins", new=AsyncMock(return_value="synthesized")),
    ):
        from core.engine.canvas.canvas_engagement import run_canvas_engagement

        result = await run_canvas_engagement(
            task="Architecture question",
            classification=classification,
            product_id="product:test",
            on_canvas_event=on_event,
        )

    event_types = [e[0] for e in events]
    assert event_types.count("agent.perspective.start") == 2
    assert event_types.count("agent.perspective.token") >= 2  # streamed deltas, one+ per perspective
    assert "synthesis.start" in event_types
    assert "synthesis.step" in event_types
    assert "synthesis.end" in event_types
    assert result == "synthesized"
    # Verify synthesis events are ordered correctly after all perspective events
    synthesis_start_idx = event_types.index("synthesis.start")
    synthesis_step_idx = event_types.index("synthesis.step")
    synthesis_end_idx = event_types.index("synthesis.end")
    assert synthesis_start_idx < synthesis_step_idx < synthesis_end_idx


@pytest.mark.asyncio
async def test_perspective_index_in_payloads():
    events = []

    async def on_event(event_type, payload):
        events.append((event_type, payload))

    classification = {
        "mode": "deliberative",
        "engagement": {"perspectives": ["analyst", "creator"], "adversarial_pair": None},
        "specialties": [],
    }

    spin_map_idx = {"analyst": _make_spin("analyst"), "creator": _make_spin("creator")}

    async def fake_stream_spin_idx(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        spin = spin_map_idx[perspective]
        await on_delta(spin.content)
        return spin

    with (
        patch("core.engine.canvas.canvas_engagement._stream_spin_content", new=fake_stream_spin_idx),
        patch("core.engine.canvas.canvas_engagement.synthesize_spins", new=AsyncMock(return_value="done")),
    ):
        from core.engine.canvas.canvas_engagement import run_canvas_engagement

        await run_canvas_engagement("Q", classification, "product:test", on_event)

    start_events = [(t, p) for t, p in events if t == "agent.perspective.start"]
    assert start_events[0][1]["perspective_index"] == 0
    assert start_events[1][1]["perspective_index"] == 1
    assert start_events[0][1]["total_perspectives"] == 2
    # Token events carry the right perspective_index (proves streaming wired per index)
    token_events = [(t, p) for t, p in events if t == "agent.perspective.token"]
    assert token_events[0][1]["perspective_index"] == 0
    assert token_events[1][1]["perspective_index"] == 1


@pytest.mark.asyncio
async def test_defaults_to_executor_when_no_perspectives():
    events = []

    async def on_event(event_type, payload):
        events.append((event_type, payload))

    classification = {
        "mode": "deliberative",
        # No "engagement" key at all
        "specialties": [],
    }

    spin = _make_spin("executor", "fallback analysis")

    async def fake_stream_spin(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        await on_delta(spin.content)
        return spin

    with patch("core.engine.canvas.canvas_engagement._stream_spin_content", new=fake_stream_spin):
        from core.engine.canvas.canvas_engagement import run_canvas_engagement

        result = await run_canvas_engagement(
            task="What should we build?",
            classification=classification,
            product_id="product:test",
            on_canvas_event=on_event,
        )

    start_events = [e for e in events if e[0] == "agent.perspective.start"]
    assert len(start_events) == 1
    assert start_events[0][1]["archetype"] == "executor"
    assert result == "fallback analysis"
