# tests/canvas/test_participant.py
import pytest

from core.engine.canvas.event_protocol import (
    EVENT_FRAMEWORK_COMPLETED,
    EVENT_FRAMEWORK_REQUESTED,
    EVENT_SESSION_OPENED,
)
from core.engine.canvas.models import ParticipantState
from core.engine.canvas.participant import CanvasParticipant


@pytest.mark.asyncio
async def test_participant_starts_idle_then_watches_after_session_open():
    captured_emit = []

    async def emit(session_id, event_type, payload):
        captured_emit.append((event_type, payload))

    p = CanvasParticipant(session_id="canvas_session:s1", emit=emit)
    assert p.state == ParticipantState.IDLE
    await p.handle_event(
        {
            "event_type": EVENT_SESSION_OPENED,
            "surface": "canvas",
            "payload": {"title": "t", "project_id": "p1", "opener_kind": "human"},
            "session_id": "canvas_session:s1",
        }
    )
    assert p.state == ParticipantState.WATCHING


@pytest.mark.asyncio
async def test_participant_drafts_on_framework_requested():
    """Participant routes framework.requested through render_via_orchestration
    and emits framework.completed with the expected fields."""
    from unittest.mock import AsyncMock, MagicMock, patch

    captured = []

    async def emit(session_id, event_type, payload):
        captured.append((event_type, payload))

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {
        "framework_kind": "trade_off_matrix",
        "title": "Postgres vs DynamoDB",
        "recommendation": "Postgres",
    }

    p = CanvasParticipant(session_id="canvas_session:s1", emit=emit)
    p.state = ParticipantState.WATCHING

    with (
        patch("core.engine.canvas.participant.render_via_orchestration", new=AsyncMock(return_value=fake_spec)),
        patch("core.engine.canvas.participant._get_prior_decisions", new=AsyncMock(return_value=[])),
    ):
        await p.handle_event(
            {
                "event_type": EVENT_FRAMEWORK_REQUESTED,
                "surface": "canvas",
                "payload": {
                    "framework_kind": "trade_off_matrix",
                    "prompt": "Postgres or Dynamo?",
                    "cited_artifact_ids": [],
                },
                "session_id": "canvas_session:s1",
            }
        )

    # Participant transitioned through DRAFTING and emitted a framework.completed event
    states_emitted = [c[1].get("new_state") for c in captured if c[0] == "participant.state_changed"]
    assert "drafting" in states_emitted
    assert any(c[0] == EVENT_FRAMEWORK_COMPLETED for c in captured)
    # The completed event carries the expected fields
    completed = next(c[1] for c in captured if c[0] == EVENT_FRAMEWORK_COMPLETED)
    assert completed.get("tldraw_shape_id", "").startswith("shape:fw_")
    assert completed.get("framework_kind") == "trade_off_matrix"
    # Settled back to watching
    assert p.state == ParticipantState.WATCHING


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_participant_resolves_cited_artifact_ids_to_text(db_pool):
    """Participant MUST hydrate cited_artifact_ids → cited_text via persistence
    before invoking render_via_orchestration. Without this, citations are silently lost.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.canvas.models import ParticipantKind, ShapeKind
    from core.engine.canvas.persistence import create_session, upsert_artifact

    sess = await create_session(project_id="product:p1", title="t")
    a1 = await upsert_artifact(
        session_id=sess.id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id="shape:s1",
        payload={"text": "Need ACID for billing"},
        x=0,
        y=0,
        author=ParticipantKind.HUMAN,
    )

    captured_render_call = {}

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {"framework_kind": "trade_off_matrix", "recommendation": "Postgres"}

    async def spy_render(**kwargs):
        captured_render_call.update(kwargs)
        return fake_spec

    async def emit(session_id, event_type, payload):
        pass

    p = CanvasParticipant(session_id=sess.id, emit=emit)
    p.state = ParticipantState.WATCHING

    with (
        patch("core.engine.canvas.participant.render_via_orchestration", side_effect=spy_render),
        patch("core.engine.canvas.participant._get_prior_decisions", new=AsyncMock(return_value=[])),
    ):
        await p.handle_event(
            {
                "event_type": EVENT_FRAMEWORK_REQUESTED,
                "surface": "canvas",
                "payload": {
                    "framework_kind": "trade_off_matrix",
                    "prompt": "Postgres or Dynamo?",
                    "cited_artifact_ids": [a1.id],
                },
                "session_id": sess.id,
            }
        )

    # The participant MUST have resolved a1.id → its sticky text and passed it through.
    assert captured_render_call.get("cited_text") == ["Need ACID for billing"], (
        "Participant did not hydrate cited_artifact_ids — citations would be silently lost"
    )


@pytest.mark.asyncio
async def test_render_framework_calls_orchestrated_renderer():
    """participant._render_framework must use render_via_orchestration, not render_framework."""
    from unittest.mock import AsyncMock, MagicMock, patch

    emitted = []

    async def emit(session_id, event_type, payload):
        emitted.append(event_type)

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {"framework_kind": "trade_off_matrix", "title": "T", "recommendation": "A"}

    participant = CanvasParticipant(session_id="canvas_session:test", emit=emit)

    with (
        patch(
            "core.engine.canvas.participant.render_via_orchestration", new=AsyncMock(return_value=fake_spec)
        ) as mock_render,
        patch.object(participant, "_resolve_cited_text", new=AsyncMock(return_value=[])),
        patch("core.engine.canvas.participant._get_prior_decisions", new=AsyncMock(return_value=[])),
    ):
        await participant._render_framework(
            {
                "framework_kind": "trade_off_matrix",
                "prompt": "A vs B?",
                "cited_artifact_ids": [],
            }
        )

    mock_render.assert_called_once()
    call_kwargs = mock_render.call_args
    assert call_kwargs.kwargs.get("kind") == "trade_off_matrix" or call_kwargs.args[0] == "trade_off_matrix"
    assert "framework.completed" in emitted


@pytest.mark.asyncio
async def test_agent_events_forwarded_over_websocket():
    """on_canvas_event callback passed to render_via_orchestration must emit via self._emit."""
    from unittest.mock import AsyncMock, MagicMock, patch

    emitted_events = []

    async def emit(session_id, event_type, payload):
        emitted_events.append(event_type)

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {"framework_kind": "trade_off_matrix"}

    participant = CanvasParticipant(session_id="canvas_session:x", emit=emit)

    async def fake_render(kind, prompt, cited_text, prior_decisions, product_id, on_canvas_event):
        # Simulate agent events fired by orchestrated_renderer
        await on_canvas_event("agent.perspective.start", {"archetype": "analyst"})
        await on_canvas_event("agent.perspective.step", {"archetype": "analyst", "content": "..."})
        await on_canvas_event("agent.perspective.end", {"archetype": "analyst", "confidence": 0.9})
        return fake_spec

    with (
        patch("core.engine.canvas.participant.render_via_orchestration", side_effect=fake_render),
        patch.object(participant, "_resolve_cited_text", new=AsyncMock(return_value=[])),
        patch("core.engine.canvas.participant._get_prior_decisions", new=AsyncMock(return_value=[])),
    ):
        await participant._render_framework(
            {
                "framework_kind": "trade_off_matrix",
                "prompt": "Q?",
                "cited_artifact_ids": [],
                "project_id": "product:test",
            }
        )

    assert "agent.perspective.start" in emitted_events
    assert "agent.perspective.step" in emitted_events
    assert "agent.perspective.end" in emitted_events
    assert "framework.completed" in emitted_events
