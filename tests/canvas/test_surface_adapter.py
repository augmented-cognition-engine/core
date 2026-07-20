# tests/canvas/test_surface_adapter.py
import pytest

from core.engine.canvas.event_protocol import (
    EVENT_ARTIFACT_PLACED,
    ArtifactPlacedPayload,
)
from core.engine.canvas.surface_adapter import CanvasSurfaceAdapter, SurfaceAdapter


@pytest.mark.asyncio
async def test_canvas_adapter_emits_with_surface_field():
    """The adapter must stamp surface='canvas' on every event it emits."""
    captured = []

    async def fake_consumer(event):
        captured.append(event)

    adapter = CanvasSurfaceAdapter(consumer=fake_consumer)
    payload = ArtifactPlacedPayload(
        shape_kind="sticky",
        payload={"text": "Postgres or Dynamo?"},
        author="human",
        tldraw_shape_id="shape:abc",
        x=100,
        y=200,
    )
    await adapter.emit(
        session_id="canvas_session:s1",
        event_type=EVENT_ARTIFACT_PLACED,
        payload=payload,
    )
    assert len(captured) == 1
    assert captured[0]["surface"] == "canvas"
    assert captured[0]["event_type"] == EVENT_ARTIFACT_PLACED


@pytest.mark.asyncio
async def test_canvas_adapter_does_not_import_claude_code_hooks():
    """v∞ invariant: canvas adapter MUST NOT depend on hook lifecycle."""
    import core.engine.canvas.surface_adapter as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "core.engine.capture.observer" not in src
    assert ".claude/hooks" not in src
    assert "claude_code" not in src.lower()


def test_surface_adapter_is_abstract():
    """SurfaceAdapter cannot be instantiated directly — abstract guard, not arity guard."""
    with pytest.raises(TypeError):
        SurfaceAdapter(consumer=lambda e: None)  # type: ignore
