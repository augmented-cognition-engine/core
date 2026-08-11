"""Provider-free measured-impact classification.

The durable application service resolves and validates Core-owned references.
This module receives only those resolved values and computes a bounded paired
comparison under the exact product-owned criterion carried by the request.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.impact import (
    ImpactClassification,
    ImpactEvaluationRequestV1Alpha1,
    ImpactEvaluationV1Alpha1,
    ImpactEvidenceExclusionV1Alpha1,
    ImpactGovernanceProposalV1Alpha1,
    ImpactMetricDirection,
    ImpactOutcomeMeasuresV1Alpha1,
)


@dataclass(frozen=True, slots=True)
class ResolvedImpactEvidence:
    """Exact-load result for one treatment/control pair."""

    evidence_id: str
    treatment: ImpactOutcomeMeasuresV1Alpha1 | None
    control: ImpactOutcomeMeasuresV1Alpha1 | None
    exclusion_reasons: tuple[str, ...] = ()


def _optional_mean(values: list[int | float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return float(fmean(value for value in values if value is not None))


def _optional_sum(values: list[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return float(sum(value for value in values if value is not None))


def _proposal_action(request: ImpactEvaluationRequestV1Alpha1, classification: ImpactClassification):
    if classification is ImpactClassification.USEFUL:
        return request.criterion.useful_action
    if classification is ImpactClassification.HARMFUL:
        return request.criterion.harmful_action
    return request.criterion.unproven_action


def evaluate_measured_impact(
    request: ImpactEvaluationRequestV1Alpha1,
    resolved: tuple[ResolvedImpactEvidence, ...],
    *,
    evaluated_at,
) -> tuple[ImpactEvaluationV1Alpha1, ImpactGovernanceProposalV1Alpha1 | None]:
    """Classify exact matched evidence and optionally emit a non-effective proposal."""

    request_ids = tuple(str(item.evidence_id) for item in request.evidence)
    resolved_ids = tuple(item.evidence_id for item in resolved)
    if len(resolved_ids) != len(set(resolved_ids)):
        raise ValueError("resolved impact evidence identities must be unique")
    if tuple(sorted(resolved_ids)) != request_ids:
        raise ValueError("resolved impact evidence does not match the exact request closure")

    ordered = tuple(sorted(resolved, key=lambda item: item.evidence_id))
    included = tuple(item for item in ordered if not item.exclusion_reasons)
    exclusions = tuple(
        ImpactEvidenceExclusionV1Alpha1(
            evidence_id=item.evidence_id,
            reasons=tuple(sorted(set(item.exclusion_reasons))),
        )
        for item in ordered
        if item.exclusion_reasons
    )

    treatment_values = [float(item.treatment.primary_value) for item in included if item.treatment is not None]
    control_values = [float(item.control.primary_value) for item in included if item.control is not None]
    if len(treatment_values) != len(included) or len(control_values) != len(included):
        raise ValueError("included impact evidence must have complete primary outcome values")

    treatment_mean = float(fmean(treatment_values)) if treatment_values else None
    control_mean = float(fmean(control_values)) if control_values else None
    effects = [
        treatment - control
        if request.criterion.metric_direction is ImpactMetricDirection.HIGHER_IS_BETTER
        else control - treatment
        for treatment, control in zip(treatment_values, control_values, strict=True)
    ]
    mean_effect = float(fmean(effects)) if effects else None
    if len(effects) >= 2 and mean_effect is not None:
        variance = sum((item - mean_effect) ** 2 for item in effects) / (len(effects) - 1)
        margin = 1.96 * math.sqrt(variance / len(effects))
        confidence_low = float(mean_effect - margin)
        confidence_high = float(mean_effect + margin)
    else:
        confidence_low = confidence_high = None

    reasons: set[str] = set()
    if len(included) < request.criterion.minimum_matched_pairs:
        classification = ImpactClassification.UNPROVEN
        reasons.add("insufficient_matched_evidence")
    elif confidence_low is None or confidence_high is None or mean_effect is None:
        classification = ImpactClassification.UNPROVEN
        reasons.add("effect_uncertainty_unavailable")
    elif confidence_low >= request.criterion.useful_effect_threshold:
        classification = ImpactClassification.USEFUL
        reasons.add("paired_interval_meets_product_useful_threshold")
    elif confidence_high <= -request.criterion.harmful_effect_threshold:
        classification = ImpactClassification.HARMFUL
        reasons.add("paired_interval_meets_product_harmful_threshold")
    else:
        classification = ImpactClassification.UNPROVEN
        reasons.add("paired_interval_does_not_establish_use_or_harm")
    if exclusions:
        reasons.add("some_evidence_excluded_fail_closed")

    treatment_measures = [item.treatment for item in included if item.treatment is not None]
    control_measures = [item.control for item in included if item.control is not None]
    treatment_latency = _optional_mean([item.latency_ms for item in treatment_measures])
    control_latency = _optional_mean([item.latency_ms for item in control_measures])
    treatment_cost = _optional_sum([item.cost_usd for item in treatment_measures])
    control_cost = _optional_sum([item.cost_usd for item in control_measures])
    limitations = {
        "paired_association_under_product_defined_conditions_does_not_by_itself_establish_causality",
        "classification_is_bounded_to_the_exact_target_control_criterion_and_cutoff",
        "proposal_requires_separate_human_review_and_has_no_live_effect",
    }
    if treatment_latency is None or control_latency is None:
        limitations.add("latency_comparison_unavailable_or_incomplete")
    if treatment_cost is None or control_cost is None:
        limitations.add("cost_comparison_unavailable_or_incomplete")
    for item in treatment_measures + control_measures:
        limitations.update(item.limitations)

    evidence_hash = f"sha256:{
        canonical_hash(
            {
                'request_digest': request.request_digest,
                'resolved': [
                    {
                        'evidence_id': item.evidence_id,
                        'treatment': item.treatment.model_dump(mode='json') if item.treatment is not None else None,
                        'control': item.control.model_dump(mode='json') if item.control is not None else None,
                        'exclusion_reasons': sorted(set(item.exclusion_reasons)),
                    }
                    for item in ordered
                ],
            }
        )
    }"
    evaluation = ImpactEvaluationV1Alpha1(
        evaluation_key=request.evaluation_key,
        request_digest=str(request.request_digest),
        product_id=request.product_id,
        criterion=request.criterion,
        target=request.target,
        control=request.control,
        cutoff_at=request.cutoff_at,
        evaluated_at=evaluated_at,
        classification=classification,
        included_evidence_ids=tuple(item.evidence_id for item in included),
        exclusions=exclusions,
        matched_pair_count=len(included),
        mean_effect=mean_effect,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        treatment_mean=treatment_mean,
        control_mean=control_mean,
        treatment_mean_latency_ms=treatment_latency,
        control_mean_latency_ms=control_latency,
        treatment_cost_usd=treatment_cost,
        control_cost_usd=control_cost,
        treatment_failure_count=sum(item.failure_count for item in treatment_measures),
        control_failure_count=sum(item.failure_count for item in control_measures),
        treatment_degraded_count=sum(item.degraded for item in treatment_measures),
        control_degraded_count=sum(item.degraded for item in control_measures),
        evidence_hash=evidence_hash,
        reasons=tuple(sorted(reasons)),
        limitations=tuple(sorted(limitations)),
    )
    action = _proposal_action(request, classification)
    if action is None:
        return evaluation, None
    proposal = ImpactGovernanceProposalV1Alpha1(
        product_id=request.product_id,
        evaluation_id=str(evaluation.evaluation_id),
        evaluation_digest=str(evaluation.evaluation_digest),
        target=request.target,
        action=action,
        rationale=(
            f"The exact {classification.value} classification maps to {action.value} under "
            f"product criterion {request.criterion.criterion_id}; separate human review is required."
        ),
        proposed_at=evaluation.evaluated_at,
    )
    return evaluation, proposal


__all__ = ["ResolvedImpactEvidence", "evaluate_measured_impact"]
