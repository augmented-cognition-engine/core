import pytest

from core.engine.canvas import canvas_engagement as ce
from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_END,
    EVENT_AGENT_PERSPECTIVE_START,
    EVENT_AGENT_PERSPECTIVE_STEP,
    EVENT_AGENT_PERSPECTIVE_TOKEN,
)
from core.engine.orchestrator.engagement_models import SpinOutput


@pytest.mark.asyncio
async def test_run_canvas_engagement_streams_tokens_not_step(monkeypatch):
    async def fake_stream_spin(task, perspective, classification, product_id, on_delta, max_tokens=2048):
        await on_delta("partial ")
        await on_delta("answer")
        return SpinOutput(
            content="partial answer",
            handoff="",
            confidence=0.0,
            open_questions=[],
            perspective=perspective,
            specialties_used=[],
        )

    monkeypatch.setattr(ce, "_stream_spin_content", fake_stream_spin)

    events = []

    async def on_canvas_event(event_type, payload):
        events.append((event_type, payload))

    out = await ce.run_canvas_engagement(
        task="t",
        classification={"engagement": {"perspectives": ["analyst"]}, "mode": "deliberative"},
        product_id="product:test",
        on_canvas_event=on_canvas_event,
    )

    types = [e for e, _ in events]
    assert EVENT_AGENT_PERSPECTIVE_START in types
    assert EVENT_AGENT_PERSPECTIVE_TOKEN in types  # streamed deltas emitted
    assert EVENT_AGENT_PERSPECTIVE_STEP not in types  # full-content step is NOT emitted when streaming
    assert EVENT_AGENT_PERSPECTIVE_END in types
    token_payloads = [p for e, p in events if e == EVENT_AGENT_PERSPECTIVE_TOKEN]
    assert "".join(p["delta"] for p in token_payloads) == "partial answer"
    assert out == "partial answer"  # single perspective → its content
