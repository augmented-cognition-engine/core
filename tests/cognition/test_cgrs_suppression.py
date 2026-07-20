"""CGRS_SUPPRESSION is prepended to system prompts when classifier is confident
and the problem is simple/moderate."""

import pytest


@pytest.mark.integration
async def test_cgrs_prepended_when_confident_and_simple(monkeypatch):
    """run_reasoning prepends CGRS_SUPPRESSION when conditions are met."""
    from core.engine.cognition import reasoning_run as rr
    from core.engine.cognition.models import CognitiveComposition
    from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION

    captured: dict = {}

    class _FakeLLM:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            captured["system"] = system
            return "ok"

    monkeypatch.setattr(rr, "get_llm", lambda: _FakeLLM())

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    await rr.run_reasoning(
        thought="hi",
        classification={"discipline": "x", "mode": "reactive", "complexity": "simple", "mode_confidence": 0.9},
        composition=comp,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert captured["system"] is not None
    assert CGRS_SUPPRESSION in captured["system"]


@pytest.mark.integration
async def test_cgrs_NOT_prepended_when_complex(monkeypatch):
    """Complex problems get full reflection — no CGRS suppression."""
    from core.engine.cognition import reasoning_run as rr
    from core.engine.cognition.models import CognitiveComposition
    from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION

    captured: dict = {}

    class _FakeLLM:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            captured["system"] = system
            return "ok"

    monkeypatch.setattr(rr, "get_llm", lambda: _FakeLLM())

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    await rr.run_reasoning(
        thought="hi",
        classification={"discipline": "x", "mode": "deliberative", "complexity": "complex", "mode_confidence": 0.9},
        composition=comp,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert CGRS_SUPPRESSION not in (captured.get("system") or "")


@pytest.mark.integration
async def test_cgrs_NOT_prepended_when_low_confidence(monkeypatch):
    """Low mode_confidence → leave reflection untouched."""
    from core.engine.cognition import reasoning_run as rr
    from core.engine.cognition.models import CognitiveComposition
    from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION

    captured: dict = {}

    class _FakeLLM:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            captured["system"] = system
            return "ok"

    monkeypatch.setattr(rr, "get_llm", lambda: _FakeLLM())

    comp = CognitiveComposition(
        meta_skills=["test"],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    await rr.run_reasoning(
        thought="hi",
        classification={"discipline": "x", "mode": "reactive", "complexity": "simple", "mode_confidence": 0.4},
        composition=comp,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert CGRS_SUPPRESSION not in (captured.get("system") or "")
