"""Deterministic policy tests for the shadow adaptive-reasoning planner."""

from __future__ import annotations

from types import SimpleNamespace

from core.engine.api.tasks import _execution_coverage
from core.engine.orchestration.adaptive_reasoning import (
    build_advisory_stage_plan,
    evaluate_advisory_stage_plan,
)
from core.engine.orchestration.request import OrchestrationRequest


def _request(description: str, **overrides) -> OrchestrationRequest:
    return OrchestrationRequest(
        description=description,
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:test",
        **overrides,
    )


def _selected(plan: dict) -> set[str]:
    return {stage["stage"] for stage in plan["stages"] if stage["selected"]}


def test_routine_bounded_work_stays_lean_without_claiming_quality_measurement():
    plan = build_advisory_stage_plan(
        _request("Return exactly three bullets"),
        {
            "mode": "reactive",
            "complexity": "simple",
            "routing_governance": {"route": "bounded_interactive"},
            "engagement": {"perspectives": ["bounded_interactive"]},
        },
    )

    assert plan["priority"] == "routine"
    assert plan["advisory_only"] is True
    assert "divergent_perspectives" not in _selected(plan)
    assert plan["measurement"]["novelty_outcome"] == "not_measured"


def test_novel_design_work_has_a_divergence_and_synthesis_floor():
    plan = build_advisory_stage_plan(
        _request("Invent a novel product strategy and explore alternatives"),
        {"mode": "exploratory", "complexity": "complex", "engagement": {"perspectives": ["strategist"]}},
    )

    assert plan["priority"] == "novelty"
    assert {"divergent_perspectives", "synthesis", "refinement"} <= _selected(plan)
    assert plan["quality_floors"] == {
        "novelty_floor_active": True,
        "minimum_materially_distinct_views": 2,
        "semantic_verification_required": True,
    }
    assert plan["priority_order"][-1] == "latency"


def test_high_risk_work_prioritizes_assurance_and_verification():
    plan = build_advisory_stage_plan(
        _request("Design a production authentication migration"),
        {
            "mode": "deliberative",
            "complexity": "complex",
            "risk_context": {"blast_radius": "systemic", "seam_gaps": ["rollback"]},
            "engagement": {"perspectives": ["architect"]},
        },
    )

    assert plan["priority"] == "assurance"
    assert "verification" in _selected(plan)
    assert plan["priority_order"][0] == "assurance"


def test_explicit_deep_request_preserves_novelty_floor_even_when_classified_simple():
    plan = build_advisory_stage_plan(
        _request("Consider this decision", force_frameworks=True),
        {"mode": "reactive", "complexity": "simple", "engagement": {"perspectives": ["executor"]}},
    )

    assert plan["signals"]["explicit_deep"] is True
    assert plan["quality_floors"]["novelty_floor_active"] is True
    assert {"divergent_perspectives", "synthesis"} <= _selected(plan)


def test_conflicting_prior_decisions_force_assurance_and_multiple_views():
    plan = build_advisory_stage_plan(
        _request("Recommend the next release step"),
        {
            "mode": "procedural",
            "complexity": "simple",
            "recent_decisions_contradictions": [("decision:a", "decision:b", "release")],
            "engagement": {"perspectives": ["operator"]},
        },
    )

    assert plan["priority"] == "assurance"
    assert {"divergent_perspectives", "synthesis", "verification"} <= _selected(plan)


def test_public_execution_receipt_exposes_shadow_plan_separately_from_actual_plan():
    actual = {"planner": "dynamic_stage_policy_v1", "route": "bounded_interactive"}
    advisory = {"planner": "adaptive_reasoning_shadow_v1", "advisory_only": True}
    result = SimpleNamespace(
        pattern_result=None,
        output="usable",
        snapshot={},
        classification={"routing_governance": {"stage_plan": actual, "adaptive_stage_plan": advisory}},
    )

    execution = _execution_coverage(result)

    assert execution["stage_plan"] == actual
    assert execution["adaptive_stage_plan"] == advisory


def test_evidence_compares_only_observable_stages_and_preserves_unknowns():
    plan = build_advisory_stage_plan(
        _request("Invent a novel product strategy"),
        {"mode": "exploratory", "complexity": "complex", "engagement": {"perspectives": ["strategist"]}},
    )
    evidence = evaluate_advisory_stage_plan(
        plan,
        snapshot={
            "perspectives_used": ["strategist", "skeptic"],
            "spin_count": 2,
            "verified": True,
            "verification_verdict": "clean",
        },
        token_usage={
            "llm_calls": [
                {"stage": "classification"},
                {"stage": "engagement"},
                {"stage": "engagement"},
            ],
            "latency": {"retry_count": 0, "stages": {"classification": {}, "engagement": {}}},
            "total_tokens": 900,
        },
        execution={"usable_output": True},
        actual_calls=3,
        duration_ms=4_500,
        status="completed",
    )

    stages = {item["stage"]: item for item in evidence["comparison"]["stages"]}
    assert stages["semantic_classification"]["actual"] == "observed"
    assert stages["divergent_perspectives"]["agreement"] is True
    assert stages["synthesis"]["agreement"] is True
    assert stages["verification"]["agreement"] is True
    assert stages["refinement"]["actual"] == "unknown"
    assert evidence["actual"] == {
        "raw_model_stages": ["classification", "engagement"],
        "model_calls": 3,
        "retry_count": 0,
        "task_wall_ms": 4_500,
        "status": "completed",
        "output_complete": True,
        "total_tokens": 900,
    }
    assert evidence["quality_evidence"]["novelty_outcome"] == "not_measured"


def test_bounded_evidence_records_bypassed_semantics_and_unclaimed_verification():
    plan = build_advisory_stage_plan(
        _request("Return exactly three bullets"),
        {
            "mode": "reactive",
            "complexity": "simple",
            "routing_governance": {"route": "bounded_interactive"},
            "engagement": {"perspectives": ["bounded_interactive"]},
        },
    )
    evidence = evaluate_advisory_stage_plan(
        plan,
        snapshot={
            "spin_count": 1,
            "bounded_interactive": {
                "selected": True,
                "validation": "deterministic_shape",
                "semantic_verification": "not_claimed",
                "stage_plan": {"intelligence": {"retrieved": 0}},
            },
        },
        token_usage={
            "llm_calls": [{"stage": "bounded_interactive"}],
            "latency": {"retry_count": 0, "stages": {"bounded_interactive": {}}},
            "total_tokens": 100,
        },
        execution={"usable_output": True},
        actual_calls=1,
        duration_ms=1_200,
        status="completed",
    )

    stages = {item["stage"]: item for item in evidence["comparison"]["stages"]}
    assert stages["semantic_classification"]["agreement"] is True
    assert stages["divergent_perspectives"]["agreement"] is True
    assert stages["verification"]["agreement"] is True
    assert evidence["quality_evidence"]["contract_validation"] == "deterministic_shape"
