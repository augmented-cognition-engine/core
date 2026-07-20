"""Tests for engine/core/llm_prompt_fragments.py — CGRS suppression."""

import pytest


@pytest.mark.unit
def test_cgrs_suppression_is_non_empty_string():
    from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION

    assert isinstance(CGRS_SUPPRESSION, str)
    assert len(CGRS_SUPPRESSION) > 0


@pytest.mark.unit
def test_cgrs_suppression_names_specific_trigger_words():
    """The fragment must call out the exact trigger words it suppresses."""
    from core.engine.core.llm_prompt_fragments import CGRS_SUPPRESSION

    low = CGRS_SUPPRESSION.lower()
    for word in ("wait", "alternatively", "hmm"):
        assert word in low, f"CGRS_SUPPRESSION must name {word!r}"


@pytest.mark.unit
def test_should_apply_cgrs_when_confident_and_simple():
    from core.engine.core.llm_prompt_fragments import should_apply_cgrs

    assert should_apply_cgrs({"mode_confidence": 0.9, "complexity": "simple"}) is True
    assert should_apply_cgrs({"mode_confidence": 0.7, "complexity": "moderate"}) is True


@pytest.mark.unit
def test_should_not_apply_cgrs_when_uncertain():
    from core.engine.core.llm_prompt_fragments import should_apply_cgrs

    assert should_apply_cgrs({"mode_confidence": 0.6, "complexity": "simple"}) is False


@pytest.mark.unit
def test_should_not_apply_cgrs_when_complex():
    from core.engine.core.llm_prompt_fragments import should_apply_cgrs

    assert should_apply_cgrs({"mode_confidence": 0.9, "complexity": "complex"}) is False


@pytest.mark.unit
def test_should_not_apply_cgrs_on_missing_fields():
    from core.engine.core.llm_prompt_fragments import should_apply_cgrs

    assert should_apply_cgrs({}) is False
