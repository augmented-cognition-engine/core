"""Provider-free deterministic AM6 Agent Memory evaluation-preparation fixture."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.contracts import canonical_hash
from ace.intelligence.agent_memory_evaluation import compare_memory_conditions
from ace.intelligence.contracts.agent_memory_evaluation import (
    BenefitDisposition,
    EvaluationCaseGate,
    MeasureAvailability,
    MeasureDirection,
    MeasureUnit,
    MemoryConditionAssignmentV1Alpha1,
    MemoryConditionPlanV1Alpha1,
    MemoryEvaluationCaseV1Alpha1,
    MemoryEvaluationCondition,
    MemoryEvaluationCorpusV1Alpha1,
    MemoryEvaluationProtocolV1Alpha1,
    MemoryMatchedCoordinatesV1Alpha1,
    MemoryMeasure,
    MemoryMeasureDefinitionV1Alpha1,
    MemoryMeasureObservationV1Alpha1,
    MemoryRunObservationV1Alpha1,
    memory_evaluation_reference,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "agent_memory_am6_evaluation_prep_v1.json"
BASE = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)

_BPS_LOWER = {
    MemoryMeasure.IDENTITY_ERROR_BPS,
    MemoryMeasure.UNRESOLVED_IDENTITY_BPS,
}
_COUNTS = {
    MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT,
    MemoryMeasure.STALE_INFLUENCE_COUNT,
    MemoryMeasure.SUPERSEDED_INFLUENCE_COUNT,
    MemoryMeasure.PROVIDER_CALLS,
    MemoryMeasure.CACHE_REUSE_COUNT,
}
_RESOURCE_UNITS = {
    MemoryMeasure.CONTEXT_TOKENS: MeasureUnit.TOKENS,
    MemoryMeasure.RESIDUAL_WINDOW_TOKENS: MeasureUnit.TOKENS,
    MemoryMeasure.LATENCY_MS: MeasureUnit.MILLISECONDS,
    MemoryMeasure.COST_MICROUNITS: MeasureUnit.MICROUNITS,
}


def _ref(key: str, contract: str) -> ExactArtifactReferenceV1Alpha1:
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=key,
        artifact_digest=f"sha256:{canonical_hash([key, contract])}",
        artifact_contract=contract,
    )


def _definition(measure: MemoryMeasure) -> MemoryMeasureDefinitionV1Alpha1:
    if measure is MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT:
        direction = MeasureDirection.ZERO_TOLERANCE
    elif measure in _BPS_LOWER or measure in {
        MemoryMeasure.STALE_INFLUENCE_COUNT,
        MemoryMeasure.SUPERSEDED_INFLUENCE_COUNT,
        MemoryMeasure.CONTEXT_TOKENS,
        MemoryMeasure.LATENCY_MS,
        MemoryMeasure.PROVIDER_CALLS,
        MemoryMeasure.COST_MICROUNITS,
    }:
        direction = MeasureDirection.LOWER_IS_BETTER
    elif measure in {MemoryMeasure.RESIDUAL_WINDOW_TOKENS, MemoryMeasure.CACHE_REUSE_COUNT}:
        direction = MeasureDirection.DESCRIPTIVE
    else:
        direction = MeasureDirection.HIGHER_IS_BETTER
    if measure in _RESOURCE_UNITS:
        unit = _RESOURCE_UNITS[measure]
    elif measure in _COUNTS:
        unit = MeasureUnit.COUNT
    else:
        unit = MeasureUnit.BASIS_POINTS
    return MemoryMeasureDefinitionV1Alpha1(measure=measure, unit=unit, direction=direction)


def _build_corpus(fixture: dict) -> MemoryEvaluationCorpusV1Alpha1:
    cases = []
    for raw in fixture["cases"]:
        gate = EvaluationCaseGate(raw.get("gate", EvaluationCaseGate.RUNNABLE_AM3.value))
        cases.append(
            MemoryEvaluationCaseV1Alpha1(
                case_id=raw["case_id"],
                title=raw["title"],
                coverage_tags=tuple(raw["coverage_tags"]),
                required_measures=tuple(MemoryMeasure(item) for item in raw["required_measures"]),
                gate=gate,
                future_required_coordinate=(
                    "future_accepted_am4_coordinate" if gate is EvaluationCaseGate.FUTURE_ACCEPTED_AM4 else None
                ),
            )
        )
    return MemoryEvaluationCorpusV1Alpha1(
        corpus_key="agent-memory-am6-evaluation-prep-v1",
        source_artifacts=tuple(_ref(key, contract) for key, contract in fixture["source_artifacts"]),
        cases=tuple(cases),
        frozen_at=BASE,
    )


def _build_protocol(fixture: dict, corpus: MemoryEvaluationCorpusV1Alpha1) -> MemoryEvaluationProtocolV1Alpha1:
    raw = fixture["protocol"]
    return MemoryEvaluationProtocolV1Alpha1(
        protocol_key="agent-memory-am6-measurement-v1",
        corpus=memory_evaluation_reference(corpus),
        conditions=tuple(MemoryEvaluationCondition),
        measure_definitions=tuple(_definition(item) for item in MemoryMeasure),
        minimum_beneficial_gain_bps=raw["minimum_beneficial_gain_bps"],
        maximum_full_context_correctness_gap_bps=raw["maximum_full_context_correctness_gap_bps"],
        preregistered_at=BASE + timedelta(seconds=1),
    )


def _matched_coordinates(fixture: dict, case_id: str) -> MemoryMatchedCoordinatesV1Alpha1:
    held = fixture["protocol"]["held_constants"]
    return MemoryMatchedCoordinatesV1Alpha1(
        task=_ref(f"task:{case_id}", "ace.evaluation.agent-memory-task/v1"),
        provider=_ref(*held["provider"]),
        model=_ref(*held["model"]),
        prompt_contract=_ref(*held["prompt_contract"]),
        decision_schema=_ref(*held["decision_schema"]),
        toolset=_ref(*held["toolset"]),
        configuration=_ref(*held["configuration"]),
    )


def _build_assignment(
    fixture: dict,
    corpus: MemoryEvaluationCorpusV1Alpha1,
    protocol: MemoryEvaluationProtocolV1Alpha1,
    raw_case: dict,
    *,
    assigned_at: datetime,
) -> MemoryConditionAssignmentV1Alpha1:
    modes = {
        MemoryEvaluationCondition.MEMORY: "authorized_selected",
        MemoryEvaluationCondition.NO_MEMORY: "disabled",
        MemoryEvaluationCondition.FULL_CONTEXT: "full_authorized_context",
    }
    return MemoryConditionAssignmentV1Alpha1(
        protocol=memory_evaluation_reference(protocol),
        corpus=memory_evaluation_reference(corpus),
        case_id=raw_case["case_id"],
        matched_coordinates=_matched_coordinates(fixture, raw_case["case_id"]),
        condition_plans=tuple(
            MemoryConditionPlanV1Alpha1(condition=condition, memory_mode=modes[condition])
            for condition in MemoryEvaluationCondition
        ),
        assigned_at=assigned_at,
    )


def _default_value(measure: MemoryMeasure, condition: MemoryEvaluationCondition, raw_case: dict) -> int:
    if measure is MemoryMeasure.TASK_CORRECTNESS_BPS:
        scores = raw_case.get("scores", {"memory": 10000, "no_memory": 5000, "full_context": 10000})
        return int(scores[condition.value])
    if measure in _BPS_LOWER or measure in {
        MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT,
        MemoryMeasure.STALE_INFLUENCE_COUNT,
        MemoryMeasure.SUPERSEDED_INFLUENCE_COUNT,
    }:
        return 0
    resources = {
        MemoryEvaluationCondition.MEMORY: {
            MemoryMeasure.CONTEXT_TOKENS: 120,
            MemoryMeasure.RESIDUAL_WINDOW_TOKENS: 3880,
            MemoryMeasure.LATENCY_MS: 10,
            MemoryMeasure.PROVIDER_CALLS: 0,
            MemoryMeasure.CACHE_REUSE_COUNT: 0,
            MemoryMeasure.COST_MICROUNITS: 0,
        },
        MemoryEvaluationCondition.NO_MEMORY: {
            MemoryMeasure.CONTEXT_TOKENS: 0,
            MemoryMeasure.RESIDUAL_WINDOW_TOKENS: 4000,
            MemoryMeasure.LATENCY_MS: 8,
            MemoryMeasure.PROVIDER_CALLS: 0,
            MemoryMeasure.CACHE_REUSE_COUNT: 0,
            MemoryMeasure.COST_MICROUNITS: 0,
        },
        MemoryEvaluationCondition.FULL_CONTEXT: {
            MemoryMeasure.CONTEXT_TOKENS: 1000,
            MemoryMeasure.RESIDUAL_WINDOW_TOKENS: 3000,
            MemoryMeasure.LATENCY_MS: 12,
            MemoryMeasure.PROVIDER_CALLS: 0,
            MemoryMeasure.CACHE_REUSE_COUNT: 0,
            MemoryMeasure.COST_MICROUNITS: 0,
        },
    }
    if measure in resources[condition]:
        return resources[condition][measure]
    if measure in {
        MemoryMeasure.SELECTED_RATE_BPS,
        MemoryMeasure.INJECTED_RATE_BPS,
        MemoryMeasure.REFLECTED_RATE_BPS,
        MemoryMeasure.DECISION_MATERIAL_RATE_BPS,
    }:
        return 0 if condition is MemoryEvaluationCondition.NO_MEMORY else 10_000
    return 10_000


def _decision_digest(raw_case: dict, condition: MemoryEvaluationCondition) -> str:
    if raw_case.get("decision_mode") == "same":
        material = [raw_case["case_id"], "same-decision"]
    elif raw_case["case_id"] == "am3_harmful_influence_probe":
        material = [raw_case["case_id"], "bad" if condition is MemoryEvaluationCondition.MEMORY else "good"]
    else:
        material = [
            raw_case["case_id"],
            "bounded-alpha" if condition is not MemoryEvaluationCondition.NO_MEMORY else "bounded-beta",
        ]
    return f"sha256:{canonical_hash(material)}"


def _build_observation(
    corpus: MemoryEvaluationCorpusV1Alpha1,
    protocol: MemoryEvaluationProtocolV1Alpha1,
    assignment: MemoryConditionAssignmentV1Alpha1,
    raw_case: dict,
    condition: MemoryEvaluationCondition,
    *,
    observed_at: datetime,
) -> MemoryRunObservationV1Alpha1:
    del corpus
    gate = raw_case.get("gate") == EvaluationCaseGate.FUTURE_ACCEPTED_AM4.value
    unavailable = raw_case.get("unavailable", {}).get(condition.value, {})
    overrides = raw_case.get("overrides", {}).get(condition.value, {})
    measurements = []
    for measure in MemoryMeasure:
        if gate:
            measurements.append(
                MemoryMeasureObservationV1Alpha1(
                    measure=measure,
                    availability=MeasureAvailability.UNAVAILABLE,
                    unavailable_reason="future_accepted_am4_coordinate_required",
                )
            )
        elif measure.value in unavailable:
            measurements.append(
                MemoryMeasureObservationV1Alpha1(
                    measure=measure,
                    availability=MeasureAvailability.UNAVAILABLE,
                    unavailable_reason=unavailable[measure.value],
                )
            )
        else:
            measurements.append(
                MemoryMeasureObservationV1Alpha1(
                    measure=measure,
                    availability=MeasureAvailability.AVAILABLE,
                    value=int(overrides.get(measure.value, _default_value(measure, condition, raw_case))),
                )
            )
    if raw_case["case_id"] == "am2_family_extraction_and_spans":
        for family in (
            "identity",
            "learned_fact",
            "active_context",
            "preference",
            "instruction_policy_proposal",
            "uncertainty",
            "correction",
        ):
            for measure in (
                MemoryMeasure.EXTRACTION_PRECISION_BPS,
                MemoryMeasure.EXTRACTION_RECALL_BPS,
                MemoryMeasure.SOURCE_SPAN_ACCURACY_BPS,
            ):
                measurements.append(
                    MemoryMeasureObservationV1Alpha1(
                        measure=measure,
                        availability=MeasureAvailability.AVAILABLE,
                        value=10_000 if condition is not MemoryEvaluationCondition.NO_MEMORY else 0,
                        stratum=f"family:{family}",
                    )
                )
    if gate:
        route_ref = "route:gated-future-am4"
        tier_ref = "tier:unavailable"
        evidence = ()
    elif condition is MemoryEvaluationCondition.NO_MEMORY:
        route_ref = "route:no-memory-control"
        tier_ref = "tier:disabled"
        evidence = (_ref(f"assignment:{raw_case['case_id']}:no-memory", "ace.evaluation.condition/v1"),)
    elif condition is MemoryEvaluationCondition.FULL_CONTEXT:
        route_ref = "route:full-context-control"
        tier_ref = "tier:full-context"
        evidence = (_ref(f"context:{raw_case['case_id']}:full", "ace.context.manifest/v1"),)
    else:
        route_ref = "route:structured-or-fused-am3"
        tier_ref = "tier:structured_or_fused"
        evidence = (
            _ref(f"recall:{raw_case['case_id']}", "ace.intelligence.memory-recall-receipt/v1alpha1"),
            _ref(f"manifest:{raw_case['case_id']}", "ace.context.manifest/v1"),
            _ref(f"use:{raw_case['case_id']}", "intelligence-use-receipt-v1"),
        )
    return MemoryRunObservationV1Alpha1(
        protocol=memory_evaluation_reference(protocol),
        assignment=memory_evaluation_reference(assignment),
        case_id=raw_case["case_id"],
        condition=condition,
        decision_digest=_decision_digest(raw_case, condition),
        route_ref=route_ref,
        tier_ref=tier_ref,
        evidence_artifacts=evidence,
        measurements=tuple(measurements),
        observed_at=observed_at,
    )


def run_provider_free_fixture() -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text())
    corpus = _build_corpus(fixture)
    protocol = _build_protocol(fixture, corpus)
    results = []
    route_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    for index, raw_case in enumerate(fixture["cases"], start=1):
        assigned_at = protocol.preregistered_at + timedelta(minutes=index)
        assignment = _build_assignment(fixture, corpus, protocol, raw_case, assigned_at=assigned_at)
        observations = tuple(
            _build_observation(
                corpus,
                protocol,
                assignment,
                raw_case,
                condition,
                observed_at=assigned_at + timedelta(seconds=condition_index + 1),
            )
            for condition_index, condition in enumerate(MemoryEvaluationCondition)
        )
        comparison = compare_memory_conditions(
            corpus=corpus,
            protocol=protocol,
            assignment=assignment,
            observations=observations,
            compared_at=assigned_at + timedelta(seconds=10),
        )
        expected = BenefitDisposition(raw_case["expected"])
        assert comparison.benefit is expected
        route_counts.update(item.route_ref for item in observations)
        tier_counts.update(item.tier_ref for item in observations)
        outcome_counts.update((comparison.benefit.value,))
        results.append(
            {
                "case_id": raw_case["case_id"],
                "gate": raw_case.get("gate", EvaluationCaseGate.RUNNABLE_AM3.value),
                "assignment_id": assignment.assignment_id,
                "assignment_digest": assignment.assignment_digest,
                "observation_ids": [item.observation_id for item in observations],
                "comparison_id": comparison.comparison_id,
                "comparison_digest": comparison.comparison_digest,
                "paired_and_controlled": comparison.paired_and_controlled,
                "material_influence": comparison.material_influence.value,
                "benefit_disposition": comparison.benefit.value,
                "correctness": comparison.correctness.value,
                "causality": comparison.causality.value,
                "missing_measurements": list(comparison.missing_measurements),
            }
        )
    rerun_corpus = _build_corpus(fixture)
    rerun_protocol = _build_protocol(fixture, rerun_corpus)
    return {
        "fixture_contract": fixture["contract"],
        "exact_base": fixture["exact_base"],
        "corpus_id": corpus.corpus_id,
        "corpus_digest": corpus.corpus_digest,
        "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest,
        "case_count": len(results),
        "condition_count": len(MemoryEvaluationCondition),
        "observation_count": len(results) * len(MemoryEvaluationCondition),
        "measure_count": len(MemoryMeasure),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "route_frequency": dict(sorted(route_counts.items())),
        "tier_frequency": dict(sorted(tier_counts.items())),
        "am3_runnable_cases": sum(item.gate is EvaluationCaseGate.RUNNABLE_AM3 for item in corpus.cases),
        "am4_gated_placeholders": sum(item.gate is EvaluationCaseGate.FUTURE_ACCEPTED_AM4 for item in corpus.cases),
        "restart_reconstruction_identical": (
            memory_evaluation_reference(rerun_corpus) == memory_evaluation_reference(corpus)
            and memory_evaluation_reference(rerun_protocol) == memory_evaluation_reference(protocol)
        ),
        "network_used": False,
        "provider_credentials_used": False,
        "policy_changes_emitted": 0,
        "results": results,
    }


__all__ = [
    "BASE",
    "FIXTURE_PATH",
    "_build_assignment",
    "_build_corpus",
    "_build_observation",
    "_build_protocol",
    "_ref",
    "run_provider_free_fixture",
]
