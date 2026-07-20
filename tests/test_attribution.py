"""Tests for the attribution module."""

import pytest

from core.engine.intelligence.attribution import (
    AttributionResult,
    attribute_structural,
    should_run_llm_attribution,
    weight_attributions,
)


def _insight(id_str, content, insight_type="pattern"):
    return {"id": id_str, "content": content, "insight_type": insight_type}


def test_structural_finds_explicit_marker():
    result = attribute_structural(
        output="I'll use parse_rows() as noted in [I-1] for result extraction.",
        marker_map={"[I-1]": "insight:1", "[I-2]": "insight:2"},
        injected_insights=[_insight("insight:1", "Use parse_rows()"), _insight("insight:2", "Always cast record IDs")],
    )
    assert "insight:1" in result.attributed_ids
    assert "insight:2" not in result.attributed_ids
    assert result.method == "structural"


def test_structural_finds_keyword_match():
    result = attribute_structural(
        output="The schema uses SCHEMALESS tables for nested object storage.",
        marker_map={"[I-1]": "insight:1"},
        injected_insights=[_insight("insight:1", "SCHEMALESS tables needed for nested objects")],
    )
    assert "insight:1" in result.attributed_ids


def test_structural_no_match_returns_empty():
    result = attribute_structural(
        output="This is a completely unrelated response.",
        marker_map={"[I-1]": "insight:1"},
        injected_insights=[_insight("insight:1", "SurrealDB record casts")],
    )
    assert result.attributed_ids == []


def test_structural_empty_output():
    result = attribute_structural(
        output="", marker_map={"[I-1]": "insight:1"}, injected_insights=[_insight("insight:1", "content")]
    )
    assert result.attributed_ids == []


def test_should_run_llm_when_zero_structural_and_insights_were_injected():
    assert should_run_llm_attribution(structural_attributed=[], injected_count=5, context_ratio=0.15) is True


def test_should_not_run_llm_when_structural_found_matches():
    assert (
        should_run_llm_attribution(structural_attributed=["insight:1"], injected_count=5, context_ratio=0.15) is False
    )


def test_should_not_run_llm_when_no_insights_injected():
    assert should_run_llm_attribution(structural_attributed=[], injected_count=0, context_ratio=0.0) is False


def test_should_not_run_llm_when_context_ratio_too_low():
    assert should_run_llm_attribution(structural_attributed=[], injected_count=3, context_ratio=0.03) is False


def test_weight_mistake_prevented():
    insights = [_insight("insight:1", "Don't do X", insight_type="correction")]
    weights = weight_attributions(attributed_ids=["insight:1"], injected_insights=insights, output="I avoided doing X")
    assert weights["insight:1"] == 5


def test_weight_convention_applied():
    insights = [_insight("insight:2", "Use parse_rows()", insight_type="pattern")]
    weights = weight_attributions(
        attributed_ids=["insight:2"], injected_insights=insights, output="Using parse_rows() for extraction"
    )
    assert weights["insight:2"] == 2


def test_weight_unattributed_is_zero():
    insights = [_insight("insight:3", "Some fact", insight_type="fact")]
    weights = weight_attributions(attributed_ids=[], injected_insights=insights, output="unrelated output")
    assert weights.get("insight:3", 0) == 0


def test_attribution_result_utilization_rate():
    result = AttributionResult(
        attributed_ids=["insight:1", "insight:2"],
        method="structural",
        injected_count=8,
        weights={"insight:1": 2, "insight:2": 5},
    )
    assert result.utilization_rate == pytest.approx(0.25)
    assert result.weighted_score == 7
