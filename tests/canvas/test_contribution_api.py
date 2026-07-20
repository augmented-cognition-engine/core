# tests/canvas/test_contribution_api.py
import pytest

from core.engine.api import canvas as canvas_api
from core.engine.canvas import cogeneration


async def _fake_get_session(session_id):
    class _S:
        id = session_id
        project_id = "product:platform"

    return _S()


@pytest.mark.integration
async def test_contribution_endpoint_emits_and_returns_when_placed(monkeypatch):
    monkeypatch.setattr(canvas_api.persistence, "get_session", _fake_get_session)

    async def _fake_gen(thought, recent, **kw):
        return cogeneration.Contribution(text="read replicas?", kind="angle", relevance=0.9)

    emitted = {}

    class _FakeAdapter:
        def __init__(self, *a, **k): ...
        async def emit(self, *, session_id, event_type, payload):
            emitted["event_type"] = event_type
            emitted["payload"] = payload

    async def _fake_upsert(**kwargs):
        emitted["upsert"] = kwargs

        class _A:
            def model_dump(self):
                return {}

        return _A()

    monkeypatch.setattr(canvas_api, "generate_contribution", _fake_gen, raising=False)
    monkeypatch.setattr(canvas_api, "CanvasSurfaceAdapter", _FakeAdapter)
    monkeypatch.setattr(canvas_api.persistence, "upsert_artifact", _fake_upsert)

    out = await canvas_api.request_contribution(
        "canvas_session:1",
        canvas_api.ContributionIn(originating_thought="scaling", recent_texts=["one db"]),
    )
    assert out.placed is True
    assert out.tldraw_shape_id and out.tldraw_shape_id.startswith("shape:cg_")
    assert out.text == "read replicas?"
    assert emitted["event_type"] == canvas_api.EVENT_ARTIFACT_PLACED


@pytest.mark.integration
async def test_contribution_endpoint_returns_unplaced_when_suppressed(monkeypatch):
    monkeypatch.setattr(canvas_api.persistence, "get_session", _fake_get_session)

    async def _fake_gen(thought, recent, **kw):
        return None

    monkeypatch.setattr(canvas_api, "generate_contribution", _fake_gen, raising=False)

    out = await canvas_api.request_contribution(
        "canvas_session:1",
        canvas_api.ContributionIn(originating_thought="x", recent_texts=[]),
    )
    assert out.placed is False
    assert out.tldraw_shape_id is None


@pytest.mark.integration
async def test_contribution_endpoint_degrades_when_generation_raises(monkeypatch):
    monkeypatch.setattr(canvas_api.persistence, "get_session", _fake_get_session)

    async def _raising_gen(thought, recent, **kw):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(canvas_api, "generate_contribution", _raising_gen, raising=False)

    out = await canvas_api.request_contribution(
        "canvas_session:1",
        canvas_api.ContributionIn(originating_thought="x", recent_texts=[]),
    )
    assert out.placed is False
    assert out.tldraw_shape_id is None


@pytest.mark.integration
async def test_contribution_endpoint_404_when_session_missing(monkeypatch):
    from fastapi import HTTPException

    async def _missing(session_id):
        raise ValueError(f"Session {session_id!r} not found")

    monkeypatch.setattr(canvas_api.persistence, "get_session", _missing)

    with pytest.raises(HTTPException) as exc:
        await canvas_api.request_contribution(
            "canvas_session:gone",
            canvas_api.ContributionIn(originating_thought="x", recent_texts=[]),
        )
    assert exc.value.status_code == 404
