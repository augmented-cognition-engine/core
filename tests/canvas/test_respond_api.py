"""Tests for POST /canvas/sessions/{id}/respond.

Monkeypatches module-level names on engine.api.canvas so no real DB/LLM is needed.
"""

from __future__ import annotations

import pytest

from core.engine.api import canvas as canvas_api
from core.engine.canvas.event_protocol import EVENT_AGENT_PHASE_END, EVENT_ARTIFACT_PLACED
from core.engine.canvas.intent_router import ResponseType
from core.engine.cognition.models import (
    CognitiveComposition,
    InstrumentSpec,
    RecipePhase,
)
from core.engine.cognition.reasoning_run import ReasoningResult

# ---------------------------------------------------------------------------
# Shared stubs / helpers
# ---------------------------------------------------------------------------


def _make_deep_composition() -> CognitiveComposition:
    """A real CognitiveComposition that run_reasoning treats as deep (multi-phase)."""
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="strategic_intelligence")],
        min_depth=1,
        output_schema="x",
    )
    return CognitiveComposition(
        meta_skills=["strategic_intelligence"],
        depth=3,
        active_phases=[phase],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
    )


class _ArtifactStub:
    """Minimal artifact stub — endpoint only calls .model_dump() on it indirectly
    (via persistence.upsert_artifact return value); the real endpoint ignores the
    return value after upsert, but having a safe stub avoids AttributeError."""

    def model_dump(self) -> dict:
        return {"id": "canvas_artifact:fake", "payload": {}}


async def _async_artifact(**_kwargs):  # noqa: ANN001
    return _ArtifactStub()


class _FakeAdapter:
    """Records every event_type that passes through .emit()."""

    def __init__(self, *_a, **_kw) -> None:
        self._events: list[str] = []

    async def emit(self, *, session_id: str, event_type: str, payload) -> None:  # noqa: ANN001
        self._events.append(event_type)


# ---------------------------------------------------------------------------
# Test: 404 when session is missing
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_respond_404_when_session_missing(monkeypatch):
    async def _get_session_raise(sid):
        raise ValueError(f"Session {sid!r} not found")

    monkeypatch.setattr(canvas_api.persistence, "get_session", _get_session_raise)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await canvas_api.respond(
            "canvas_session:missing",
            canvas_api.RespondIn(thought="hello"),
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: reasoning path — phase events + artifact placed
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_respond_reasoning_emits_phase_events_and_places_artifact(monkeypatch):
    # --- session stub ---
    class _FakeSession:
        project_id = "product:platform"
        title = "Playground"

    async def _fake_get_session(sid):
        return _FakeSession()

    # --- classify_task stub ---
    async def _fake_classify(description, product_id=""):
        return {
            "complexity": "complex",
            "task_type": "strategic",
            "discipline": "strategy",
            "specialties": [],
        }

    # --- composer stub ---
    class _FakeComposer:
        async def compose(self, classification, product_id):
            return _make_deep_composition()

    # --- run_reasoning stub — calls on_phase once then returns a result ---
    async def _fake_run_reasoning(**kwargs):
        on_phase = kwargs.get("on_phase")
        if on_phase is not None:
            await on_phase(0, 1, "frame", "f", 0.7, [])
        return ReasoningResult(
            conclusion="done",
            phases=[{"cognitive_function": "frame", "output": "f", "confidence": 0.7}],
        )

    # --- adapter capturing events ---
    adapter_instance = _FakeAdapter()

    class _FakeAdapterFactory:
        def __init__(self, *_a, **_kw) -> None:
            pass

        async def emit(self, *, session_id, event_type, payload):
            await adapter_instance.emit(session_id=session_id, event_type=event_type, payload=payload)

    # Wire monkeypatches
    monkeypatch.setattr(canvas_api.persistence, "get_session", _fake_get_session)
    monkeypatch.setattr(canvas_api.persistence, "upsert_artifact", _async_artifact)
    monkeypatch.setattr(canvas_api, "classify_task", _fake_classify)
    monkeypatch.setattr(canvas_api, "route", lambda _c: ResponseType.REASONING)
    monkeypatch.setattr(canvas_api, "CognitiveComposer", _FakeComposer)
    monkeypatch.setattr(canvas_api, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(canvas_api, "CanvasSurfaceAdapter", _FakeAdapterFactory)

    out = await canvas_api.respond(
        "canvas_session:1",
        canvas_api.RespondIn(thought="strategy?"),
    )

    assert out.response_type == "reasoning"
    assert out.read  # non-empty read string
    assert EVENT_AGENT_PHASE_END in adapter_instance._events
    assert EVENT_ARTIFACT_PLACED in adapter_instance._events


# ---------------------------------------------------------------------------
# Test: degrade path — classify_task raises → response_type == "sticky"
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_respond_degrades_to_sticky_on_classify_failure(monkeypatch):
    class _FakeSession:
        project_id = "product:platform"
        title = "Playground"

    async def _fake_get_session(sid):
        return _FakeSession()

    async def _failing_classify(description, product_id=""):
        raise RuntimeError("LLM unavailable")

    adapter_instance = _FakeAdapter()

    class _FakeAdapterFactory:
        def __init__(self, *_a, **_kw) -> None:
            pass

        async def emit(self, *, session_id, event_type, payload):
            await adapter_instance.emit(session_id=session_id, event_type=event_type, payload=payload)

    monkeypatch.setattr(canvas_api.persistence, "get_session", _fake_get_session)
    monkeypatch.setattr(canvas_api.persistence, "upsert_artifact", _async_artifact)
    monkeypatch.setattr(canvas_api, "classify_task", _failing_classify)
    monkeypatch.setattr(canvas_api, "CanvasSurfaceAdapter", _FakeAdapterFactory)

    out = await canvas_api.respond(
        "canvas_session:1",
        canvas_api.RespondIn(thought="should not crash"),
    )

    assert out.response_type == "sticky"
    # No exception propagated to caller
