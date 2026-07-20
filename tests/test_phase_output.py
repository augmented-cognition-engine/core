"""Tests for PhaseOutput typed inter-phase contract."""

import pytest
from pydantic import ValidationError

from core.engine.cognition.models import InstrumentSpec, RecipePhase
from core.engine.cognition.phase_output import PhaseOutput


def test_phase_output_requires_output_and_confidence():
    p = PhaseOutput(output="analysis result", confidence=0.85)
    assert p.output == "analysis result"
    assert p.confidence == 0.85
    assert p.evidence == []
    assert p.gaps == []


def test_phase_output_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        PhaseOutput(output="x", confidence=1.5)
    with pytest.raises(ValidationError):
        PhaseOutput(output="x", confidence=-0.1)


def test_phase_output_schema_string():
    schema = PhaseOutput.schema_prompt()
    assert "confidence" in schema
    assert "evidence" in schema
    assert "gaps" in schema


def test_recipe_phase_accepts_must_not_and_must_verify():
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="first-principles")],
        min_depth=1,
        output_schema="constraints",
        must_not=["propose solutions before identifying constraints"],
        must_verify=["hot path is actually hot"],
    )
    assert len(phase.must_not) == 1
    assert len(phase.must_verify) == 1


def test_recipe_phase_defaults_to_empty_constraints():
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(fallback_slug="first-principles")],
        min_depth=1,
        output_schema="constraints",
    )
    assert phase.must_not == []
    assert phase.must_verify == []
