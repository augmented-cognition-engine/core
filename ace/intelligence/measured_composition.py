"""Deterministic matched comparison for preregistered composition evidence."""

from __future__ import annotations

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.intelligence.contracts.measured_composition import (
    CompositionComparisonDisposition,
    CompositionConditionAssignmentV1Alpha1,
    CompositionConditionResultV1Alpha1,
    CompositionEvaluationCondition,
    CompositionEvaluationFailure,
    CompositionEvaluationProtocolV1Alpha1,
    CompositionMatchedComparisonV1Alpha1,
    CompositionPolicyChangeProposalV1Alpha1,
    CompositionRunObservationV1Alpha1,
    OutcomeAvailability,
    TelemetryAvailability,
    measured_composition_reference,
)


def _condition_result(observation: CompositionRunObservationV1Alpha1) -> CompositionConditionResultV1Alpha1:
    metrics = observation.metrics
    return CompositionConditionResultV1Alpha1(
        condition=observation.condition,
        observation=measured_composition_reference(observation),
        valid_completion=metrics.valid_completion,
        evidence_closure_bps=metrics.evidence_closure_bps,
        material_participant_count=metrics.material_participant_count,
        bounded_outcome_value=metrics.bounded_outcome_value,
        latency_ms=metrics.latency_ms,
        model_calls=metrics.model_calls,
        tool_calls=metrics.tool_calls,
        tokens=metrics.tokens,
        cost_microunits=metrics.cost_microunits,
        failures=metrics.failures,
    )


def _control_rank(observation: CompositionRunObservationV1Alpha1) -> tuple[int, int, int, int, int]:
    metrics = observation.metrics
    outcome = metrics.bounded_outcome_value if metrics.bounded_outcome_value is not None else -1
    cost = metrics.cost_microunits if metrics.cost_microunits is not None else 2**63 - 1
    return (int(metrics.valid_completion), metrics.evidence_closure_bps, outcome, -cost, -metrics.latency_ms)


def _telemetry_complete(observation: CompositionRunObservationV1Alpha1) -> bool:
    metrics = observation.metrics
    return (
        metrics.token_telemetry is TelemetryAvailability.AVAILABLE
        and metrics.cost_telemetry is TelemetryAvailability.AVAILABLE
        and metrics.tokens is not None
        and metrics.cost_microunits is not None
    )


def compare_measured_composition(
    protocol: CompositionEvaluationProtocolV1Alpha1,
    assignment: CompositionConditionAssignmentV1Alpha1,
    observations: tuple[CompositionRunObservationV1Alpha1, ...],
    *,
    current_policy: ExactArtifactReferenceV1Alpha1,
    proposed_policy_rule_ref: str,
    compared_at,
) -> tuple[CompositionMatchedComparisonV1Alpha1, CompositionPolicyChangeProposalV1Alpha1 | None]:
    """Compare one exact matched trio and emit an inert proposal only on a narrow pass."""

    protocol_ref = measured_composition_reference(protocol)
    assignment_ref = measured_composition_reference(assignment)
    if assignment.protocol != protocol_ref:
        raise ValueError("condition assignment does not bind the exact preregistered protocol")
    if assignment.product_id != protocol.product_id:
        raise ValueError("condition assignment crossed protocol product scope")
    if assignment.assigned_at < protocol.preregistered_at:
        raise ValueError("condition assignment predates protocol preregistration")
    if (
        assignment.task_inputs != protocol.task_inputs
        or assignment.evidence_inputs != protocol.evidence_inputs
        or assignment.context_inputs != protocol.context_inputs
        or assignment.held_constants != protocol.held_constants
    ):
        raise ValueError("condition assignment changed frozen task, evidence, context, or held constants")
    if len(observations) != 3 or {item.condition for item in observations} != set(CompositionEvaluationCondition):
        raise ValueError("matched comparison requires exactly one observation for each condition")
    ordered = tuple(sorted(observations, key=lambda item: item.condition.value))
    if compared_at < max(item.observed_at for item in ordered):
        raise ValueError("matched comparison cannot predate an assigned observation")
    for observation in ordered:
        if (
            observation.product_id != protocol.product_id
            or observation.protocol != protocol_ref
            or observation.assignment != assignment_ref
            or observation.pair_key != assignment.pair_key
            or observation.observed_at < assignment.assigned_at
        ):
            raise ValueError("observation crossed exact preregistration, assignment, pair, product, or time closure")
        plan = next(item for item in assignment.condition_plans if item.condition is observation.condition)
        participants = {item.participant_ref for item in observation.material_uses}
        if not participants.issubset(set(plan.participant_refs)):
            raise ValueError("observation attributed material use to a participant outside its assigned plan")

    by_condition = {item.condition: item for item in ordered}
    controls = (
        by_condition[CompositionEvaluationCondition.FIXED_MINIMAL],
        by_condition[CompositionEvaluationCondition.FIXED_MULTI],
    )
    selected_control = max(controls, key=_control_rank)
    dynamic = by_condition[CompositionEvaluationCondition.DYNAMIC]
    thresholds = protocol.thresholds
    deviations = tuple(
        sorted(f"{item.condition.value}:{deviation.code}" for item in ordered for deviation in item.deviations)
    )
    disqualifying_deviation = any(deviation.disqualifies_pair for item in ordered for deviation in item.deviations)
    telemetry_complete = all(_telemetry_complete(item) for item in ordered)
    paired_and_controlled = not disqualifying_deviation
    reasons: set[str] = set()
    limitations = {
        "claim_is_bounded_to_the_exact_preregistered_task_evidence_context_and_policy_scope",
        "matched_association_does_not_establish_general_causal_superiority",
        "evaluation_evidence_is_not_agent_memory_and_does_not_train_or_rewrite_policy",
        "any_policy_change_requires_present_tense_approval_and_separate_admission",
    }

    hard_dynamic_failures = set(dynamic.metrics.failures) - {CompositionEvaluationFailure.DUPLICATE_EFFECT_PREVENTED}
    budget = protocol.held_constants.budget
    budget_violations = tuple(
        item.condition.value
        for item in ordered
        if (
            len(item.output_artifacts) > budget.max_items
            or item.metrics.model_calls + item.metrics.tool_calls > budget.max_calls
            or item.metrics.latency_ms > budget.max_latency_ms
            or (item.metrics.tokens is not None and item.metrics.tokens > budget.max_tokens)
            or (item.metrics.cost_microunits is not None and item.metrics.cost_microunits > budget.max_cost_microunits)
        )
    )
    evidence_closure_violations = tuple(
        item.condition.value
        for item in ordered
        if (
            (item.metrics.evidence_closure_bps > 0 and not item.cited_evidence)
            or (
                item.metrics.evidence_closure_bps == 10_000
                and not set(protocol.evidence_inputs).issubset(set(item.cited_evidence))
            )
        )
    )
    if budget_violations:
        paired_and_controlled = False
        reasons.add("one_or_more_conditions_exceeded_the_frozen_absolute_budget")
    if evidence_closure_violations:
        paired_and_controlled = False
        reasons.add("reported_evidence_closure_lacked_exact_citation_closure")
    deviations = tuple(
        sorted(
            (
                *deviations,
                *(f"{condition}:absolute_budget_exceeded" for condition in budget_violations),
                *(f"{condition}:evidence_citation_closure_invalid" for condition in evidence_closure_violations),
            )
        )
    )
    outcome_comparable = dynamic.metrics.outcome_availability is selected_control.metrics.outcome_availability
    if dynamic.metrics.outcome_availability is OutcomeAvailability.OBSERVED and outcome_comparable:
        assert dynamic.metrics.bounded_outcome_value is not None
        assert selected_control.metrics.bounded_outcome_value is not None
        outcome_gain = dynamic.metrics.bounded_outcome_value - selected_control.metrics.bounded_outcome_value
        outcome_passes = outcome_gain >= thresholds.minimum_observed_outcome_gain
    elif outcome_comparable:
        outcome_passes = True
        limitations.add("bounded_outcome_was_legitimately_unavailable_or_not_applicable")
    else:
        outcome_passes = False
        limitations.add("bounded_outcome_availability_differed_across_matched_conditions")

    if thresholds.require_complete_usage_and_cost_telemetry and not telemetry_complete:
        paired_and_controlled = False
        reasons.add("required_usage_or_cost_telemetry_unavailable")
    if hard_dynamic_failures:
        paired_and_controlled = False
        reasons.add("dynamic_condition_has_fail_closed_failure")
    if not outcome_comparable:
        paired_and_controlled = False
        reasons.add("bounded_outcome_is_not_comparable")

    control_metrics = selected_control.metrics
    dynamic_metrics = dynamic.metrics
    closure_gain = dynamic_metrics.evidence_closure_bps - control_metrics.evidence_closure_bps
    material_passes = dynamic_metrics.material_participant_count >= thresholds.minimum_material_participants
    latency_passes = dynamic_metrics.latency_ms - control_metrics.latency_ms <= thresholds.maximum_latency_increase_ms
    model_calls_pass = (
        dynamic_metrics.model_calls - control_metrics.model_calls <= thresholds.maximum_model_call_increase
    )
    tool_calls_pass = dynamic_metrics.tool_calls - control_metrics.tool_calls <= thresholds.maximum_tool_call_increase
    token_passes = (
        dynamic_metrics.tokens is not None
        and control_metrics.tokens is not None
        and dynamic_metrics.tokens - control_metrics.tokens <= thresholds.maximum_token_increase
    )
    cost_passes = (
        dynamic_metrics.cost_microunits is not None
        and control_metrics.cost_microunits is not None
        and dynamic_metrics.cost_microunits - control_metrics.cost_microunits
        <= thresholds.maximum_cost_increase_microunits
    )
    narrow_pass = all(
        (
            paired_and_controlled,
            dynamic_metrics.valid_completion,
            closure_gain >= thresholds.minimum_evidence_closure_gain_bps,
            material_passes,
            outcome_passes,
            latency_passes,
            model_calls_pass,
            tool_calls_pass,
            token_passes,
            cost_passes,
        )
    )

    if narrow_pass:
        disposition = CompositionComparisonDisposition.DYNAMIC_MATERIALLY_HELPS
        reasons.add("dynamic_met_every_preregistered_materiality_and_budget_threshold")
    elif not paired_and_controlled:
        disposition = CompositionComparisonDisposition.UNPROVEN_FAIL_CLOSED
        reasons.add("causal_benefit_not_claimed_from_unpaired_uncontrolled_or_incomplete_evidence")
    elif (
        by_condition[CompositionEvaluationCondition.FIXED_MINIMAL].metrics.valid_completion
        and by_condition[CompositionEvaluationCondition.FIXED_MINIMAL].metrics.evidence_closure_bps == 10_000
        and closure_gain < thresholds.minimum_evidence_closure_gain_bps
    ):
        disposition = CompositionComparisonDisposition.CONTROL_SUFFICES
        reasons.add("fixed_minimal_condition_satisfied_the_complete_preregistered_closure")
    else:
        disposition = CompositionComparisonDisposition.NO_MATERIAL_BENEFIT
        reasons.add("dynamic_did_not_clear_the_preregistered_material_gain_and_budget_rule")
    if dynamic_metrics.cost_microunits is not None and control_metrics.cost_microunits is not None:
        if dynamic_metrics.cost_microunits > control_metrics.cost_microunits and closure_gain <= 0:
            reasons.add("dynamic_added_cost_without_evidence_closure_gain")

    comparison = CompositionMatchedComparisonV1Alpha1(
        product_id=protocol.product_id,
        protocol=protocol_ref,
        assignment=assignment_ref,
        pair_key=assignment.pair_key,
        condition_results=tuple(_condition_result(item) for item in ordered),
        selected_control=selected_control.condition,
        disposition=disposition,
        paired_and_controlled=paired_and_controlled,
        deviations=deviations,
        reasons=tuple(sorted(reasons)),
        limitations=tuple(sorted(limitations)),
        compared_at=compared_at,
    )
    if disposition is not CompositionComparisonDisposition.DYNAMIC_MATERIALLY_HELPS:
        return comparison, None
    proposal = CompositionPolicyChangeProposalV1Alpha1(
        product_id=protocol.product_id,
        protocol=protocol_ref,
        comparison=measured_composition_reference(comparison),
        scope_ref=protocol.held_constants.authority_scope_ref,
        current_policy=current_policy,
        proposed_policy_rule_ref=proposed_policy_rule_ref,
        rollback_policy=current_policy,
        supersedes=(),
        rationale=(
            "Permit a separate governor to consider dynamic composition only for the exact frozen scope; "
            "the matched trio cleared every preregistered materiality and resource threshold."
        ),
        proposed_at=comparison.compared_at,
    )
    return comparison, proposal


__all__ = ["compare_measured_composition"]
