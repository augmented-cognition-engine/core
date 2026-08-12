"""Deterministic comparison of preregistered Agent Memory conditions."""

from __future__ import annotations

from ace.intelligence.contracts.agent_memory_evaluation import (
    BenefitDisposition,
    CorrectnessDisposition,
    EvaluationCaseGate,
    MaterialInfluenceDisposition,
    MeasureAvailability,
    MemoryConditionAssignmentV1Alpha1,
    MemoryEvaluationCondition,
    MemoryEvaluationCorpusV1Alpha1,
    MemoryEvaluationProtocolV1Alpha1,
    MemoryMatchedComparisonV1Alpha1,
    MemoryMeasure,
    MemoryRunObservationV1Alpha1,
    memory_evaluation_reference,
)


def _measurement(
    observation: MemoryRunObservationV1Alpha1,
    measure: MemoryMeasure,
):
    values = [item for item in observation.measurements if item.measure is measure and item.stratum is None]
    if len(values) != 1:
        return None
    return values[0]


def _available_value(observation: MemoryRunObservationV1Alpha1, measure: MemoryMeasure) -> int | None:
    item = _measurement(observation, measure)
    if item is None or item.availability is not MeasureAvailability.AVAILABLE:
        return None
    return item.value


def compare_memory_conditions(
    *,
    corpus: MemoryEvaluationCorpusV1Alpha1,
    protocol: MemoryEvaluationProtocolV1Alpha1,
    assignment: MemoryConditionAssignmentV1Alpha1,
    observations: tuple[MemoryRunObservationV1Alpha1, ...],
    compared_at,
) -> MemoryMatchedComparisonV1Alpha1:
    """Close one exact matched trio without proposing or applying a policy change."""

    corpus_ref = memory_evaluation_reference(corpus)
    protocol_ref = memory_evaluation_reference(protocol)
    assignment_ref = memory_evaluation_reference(assignment)
    if protocol.corpus != corpus_ref:
        raise ValueError("protocol does not bind the exact frozen corpus")
    if assignment.protocol != protocol_ref or assignment.corpus != corpus_ref:
        raise ValueError("assignment crossed the exact protocol or corpus coordinate")
    if assignment.assigned_at < protocol.preregistered_at or protocol.preregistered_at < corpus.frozen_at:
        raise ValueError("corpus, preregistration, and assignment time order is invalid")
    case = next((item for item in corpus.cases if item.case_id == assignment.case_id), None)
    if case is None:
        raise ValueError("assignment names a case outside the frozen corpus")
    if len(observations) != 3 or {item.condition for item in observations} != set(MemoryEvaluationCondition):
        raise ValueError("comparison requires exactly one memory, no-memory, and full-context observation")
    ordered = tuple(sorted(observations, key=lambda item: item.condition.value))
    if compared_at < max(item.observed_at for item in ordered):
        raise ValueError("comparison cannot predate an observation")
    for item in ordered:
        if (
            item.protocol != protocol_ref
            or item.assignment != assignment_ref
            or item.case_id != case.case_id
            or item.observed_at < assignment.assigned_at
        ):
            raise ValueError("observation crossed exact protocol, assignment, case, or time closure")

    by_condition = {item.condition: item for item in ordered}
    memory = by_condition[MemoryEvaluationCondition.MEMORY]
    no_memory = by_condition[MemoryEvaluationCondition.NO_MEMORY]
    full_context = by_condition[MemoryEvaluationCondition.FULL_CONTEXT]
    reasons: set[str] = set()
    limitations = {
        "fixture_outcome_labels_validate_the_evaluator_and_are_not_agent_memory_benefit_evidence",
        "material_influence_benefit_correctness_and_causality_are_separate_dispositions",
        "no_rank_retention_consolidation_promotion_roster_authority_delivery_or_effect_policy_changes",
        "causality_is_not_established_by_this_provider_free_preparation_fixture",
    }

    missing: set[str] = set()
    for observation in ordered:
        for measure in case.required_measures:
            item = _measurement(observation, measure)
            if item is None or item.availability is not MeasureAvailability.AVAILABLE:
                condition = observation.condition.value
                reason = item.unavailable_reason if item is not None else "not_observed"
                missing.add(f"{condition}:{measure.value}:{reason}")

    if case.gate is EvaluationCaseGate.FUTURE_ACCEPTED_AM4:
        missing.add("future_accepted_am4_coordinate:required")
        limitations.add("am4_runtime_semantics_are_not_invented_or_executed_by_this_am3_runnable_suite")

    unauthorized = tuple(_available_value(item, MemoryMeasure.UNAUTHORIZED_RETRIEVAL_COUNT) for item in ordered)
    stale = _available_value(memory, MemoryMeasure.STALE_INFLUENCE_COUNT)
    superseded = _available_value(memory, MemoryMeasure.SUPERSEDED_INFLUENCE_COUNT)
    memory_correctness = _available_value(memory, MemoryMeasure.TASK_CORRECTNESS_BPS)
    no_memory_correctness = _available_value(no_memory, MemoryMeasure.TASK_CORRECTNESS_BPS)
    full_context_correctness = _available_value(full_context, MemoryMeasure.TASK_CORRECTNESS_BPS)

    if missing:
        material = MaterialInfluenceDisposition.UNDERPOWERED
        benefit = BenefitDisposition.UNDERPOWERED
        correctness = CorrectnessDisposition.UNDERPOWERED
        paired = False
        reasons.add("required_measurement_or_future_am4_coordinate_is_unavailable")
    else:
        paired = True
        material = (
            MaterialInfluenceDisposition.OBSERVED
            if memory.decision_digest != no_memory.decision_digest
            else MaterialInfluenceDisposition.NOT_OBSERVED
        )
        if any(value is not None and value > 0 for value in unauthorized):
            benefit = BenefitDisposition.HARMFUL
            correctness = CorrectnessDisposition.INCORRECT
            reasons.add("zero_tolerance_unauthorized_retrieval_was_observed")
        elif (stale or 0) > 0 or (superseded or 0) > 0:
            benefit = BenefitDisposition.HARMFUL
            correctness = CorrectnessDisposition.INCORRECT
            reasons.add("stale_or_superseded_memory_materially_influenced_the_task")
        else:
            assert memory_correctness is not None
            assert no_memory_correctness is not None
            assert full_context_correctness is not None
            if memory_correctness == 10_000:
                correctness = CorrectnessDisposition.CORRECT
            elif memory_correctness == 0:
                correctness = CorrectnessDisposition.INCORRECT
            else:
                correctness = CorrectnessDisposition.MIXED
            gain = memory_correctness - no_memory_correctness
            full_gap = full_context_correctness - memory_correctness
            if (
                material is MaterialInfluenceDisposition.OBSERVED
                and gain >= protocol.minimum_beneficial_gain_bps
                and full_gap <= protocol.maximum_full_context_correctness_gap_bps
            ):
                benefit = BenefitDisposition.BENEFICIAL
                reasons.add("synthetic_bounded_outcome_cleared_the_preregistered_matched_rule")
            elif gain < 0:
                benefit = BenefitDisposition.HARMFUL
                reasons.add("memory_condition_reduced_the_preregistered_bounded_task_score")
            else:
                benefit = BenefitDisposition.NEUTRAL
                reasons.add("memory_condition_did_not_change_the_preregistered_bounded_task_score")

    if material is MaterialInfluenceDisposition.OBSERVED:
        reasons.add("memory_and_no_memory_decision_digests_differed_under_held_constants")
    elif material is MaterialInfluenceDisposition.NOT_OBSERVED:
        reasons.add("memory_and_no_memory_decision_digests_were_identical_under_held_constants")

    return MemoryMatchedComparisonV1Alpha1(
        protocol=protocol_ref,
        assignment=assignment_ref,
        case_id=case.case_id,
        observations=tuple(memory_evaluation_reference(item) for item in ordered),
        paired_and_controlled=paired,
        material_influence=material,
        benefit=benefit,
        correctness=correctness,
        missing_measurements=tuple(sorted(missing)),
        reasons=tuple(sorted(reasons)),
        limitations=tuple(sorted(limitations)),
        compared_at=compared_at,
    )


__all__ = ["compare_memory_conditions"]
