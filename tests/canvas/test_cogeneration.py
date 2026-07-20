# tests/canvas/test_cogeneration.py
import pytest

from core.engine.canvas import cogeneration


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, prompt, **kwargs):
        return self._payload


@pytest.mark.unit
async def test_generate_contribution_returns_above_floor(monkeypatch):
    monkeypatch.setattr(
        cogeneration,
        "get_llm",
        lambda: _FakeLLM({"contribution": "Have you considered read replicas?", "kind": "angle", "relevance": 0.8}),
    )
    c = await cogeneration.generate_contribution("scaling reads", ["we use one db"])
    assert c is not None
    assert c.text == "Have you considered read replicas?"
    assert c.kind == "angle"
    assert c.relevance == 0.8


@pytest.mark.unit
async def test_generate_contribution_suppressed_below_floor(monkeypatch):
    monkeypatch.setattr(
        cogeneration,
        "get_llm",
        lambda: _FakeLLM({"contribution": "meh", "kind": "angle", "relevance": 0.2}),
    )
    assert await cogeneration.generate_contribution("x", []) is None


@pytest.mark.unit
async def test_generate_contribution_suppressed_when_empty(monkeypatch):
    monkeypatch.setattr(
        cogeneration,
        "get_llm",
        lambda: _FakeLLM({"contribution": "  ", "kind": "angle", "relevance": 0.9}),
    )
    assert await cogeneration.generate_contribution("x", []) is None
