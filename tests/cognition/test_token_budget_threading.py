"""Integration: token_budget flows classification → composition → LLM call."""

import pytest


@pytest.mark.unit
def test_classify_task_default_emits_token_budget():
    """classifier._DEFAULT carries a token_budget."""
    from core.engine.orchestrator.classifier import _DEFAULT

    # Default is moderate complexity, deliberative mode → 2048
    assert _DEFAULT.get("token_budget") == 2048


@pytest.mark.unit
def test_composition_carries_max_tokens_per_phase():
    """CognitiveComposition has an optional max_tokens_per_phase field."""
    from core.engine.cognition.models import CognitiveComposition

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
        max_tokens_per_phase=1024,
    )
    assert comp.max_tokens_per_phase == 1024


@pytest.mark.unit
def test_composition_default_max_tokens_is_none():
    """Backward compat: when not set, max_tokens_per_phase defaults to None."""
    from core.engine.cognition.models import CognitiveComposition

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
    )
    assert comp.max_tokens_per_phase is None


@pytest.mark.integration
async def test_run_reasoning_honors_max_tokens_per_phase(monkeypatch):
    """When composition.max_tokens_per_phase is set, run_reasoning passes it
    to get_llm().complete() as max_tokens."""
    from core.engine.cognition import reasoning_run as rr
    from core.engine.cognition.models import CognitiveComposition

    captured: dict = {}

    class _FakeLLM:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            captured["max_tokens"] = max_tokens
            return "ok"

    monkeypatch.setattr(rr, "get_llm", lambda: _FakeLLM())

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
        max_tokens_per_phase=1024,
    )
    await rr.run_reasoning(
        thought="hi",
        classification={"discipline": "x", "mode": "reactive", "complexity": "simple"},
        composition=comp,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert captured["max_tokens"] == 1024
