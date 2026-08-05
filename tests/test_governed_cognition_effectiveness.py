"""E1-F matched revision-effectiveness and proposal-authority gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.cognition.effectiveness import (
    CognitionOutcomeObservationV1,
    EffectConclusion,
    ExperimentVariant,
    OutcomeDisposition,
    evaluate_revision_effectiveness,
    propose_from_effectiveness,
)

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _observation(
    index: int,
    *,
    variant: ExperimentVariant,
    positive: bool,
    cohort: str = "coding:moderate:model-a",
    used: bool | None = None,
    observed_at: datetime = NOW,
    product_id: str = "product:test",
) -> CognitionOutcomeObservationV1:
    return CognitionOutcomeObservationV1(
        observation_id=f"outcome:{variant.value}:{index}:{cohort}",
        product_id=product_id,
        task_id=f"task:{variant.value}:{index}",
        revision_id="cognition_revision:test",
        variant=variant,
        cohort_key=cohort,
        use_receipt_id=f"cognition_use:{index}" if variant is ExperimentVariant.REVISION else None,
        materially_used=(variant is ExperimentVariant.REVISION if used is None else used),
        outcome=OutcomeDisposition.POSITIVE if positive else OutcomeDisposition.NEGATIVE,
        model_route="provider:model-a",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01 if variant is ExperimentVariant.REVISION else 0.008,
        latency_ms=500,
        failure_count=0 if positive else 1,
        observed_at=observed_at,
    )


def _matched(*, treatment_positive: int, control_positive: int, count: int = 40):
    return tuple(
        [
            _observation(
                index,
                variant=ExperimentVariant.REVISION,
                positive=index < treatment_positive,
            )
            for index in range(count)
        ]
        + [
            _observation(
                index,
                variant=ExperimentVariant.CONTROL,
                positive=index < control_positive,
            )
            for index in range(count)
        ]
    )


def test_single_task_and_insufficient_cohorts_are_unproven() -> None:
    receipt = evaluate_revision_effectiveness(
        (
            _observation(1, variant=ExperimentVariant.REVISION, positive=True),
            _observation(1, variant=ExperimentVariant.CONTROL, positive=False),
        ),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert receipt.conclusion is EffectConclusion.UNPROVEN
    assert "no_single_task_benefit_claim" in receipt.reasons
    assert propose_from_effectiveness(receipt) is None


def test_matched_high_confidence_help_and_harm_are_distinct() -> None:
    helped = evaluate_revision_effectiveness(
        _matched(treatment_positive=40, control_positive=0),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    hurt = evaluate_revision_effectiveness(
        _matched(treatment_positive=0, control_positive=40),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert helped.conclusion is EffectConclusion.HELPED
    assert helped.confidence_low is not None and helped.confidence_low > 0
    assert hurt.conclusion is EffectConclusion.HURT
    assert hurt.confidence_high is not None and hurt.confidence_high < 0
    proposal = propose_from_effectiveness(hurt)
    assert proposal is not None
    assert proposal.action == "revise"
    assert proposal.selectable is False
    assert proposal.requires_human_review is True


def test_null_effect_remains_unproven_with_cost_and_failure_evidence() -> None:
    receipt = evaluate_revision_effectiveness(
        _matched(treatment_positive=20, control_positive=20),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert receipt.conclusion is EffectConclusion.UNPROVEN
    assert receipt.confidence_low is not None and receipt.confidence_low < 0
    assert receipt.confidence_high is not None and receipt.confidence_high > 0
    assert receipt.treatment_cost_usd == 0.4
    assert receipt.control_cost_usd == 0.32
    assert receipt.treatment_failure_rate == 0.5
    assert receipt.control_failure_rate == 0.5


def test_unmatched_cohorts_and_foreign_product_are_excluded() -> None:
    observations = tuple(
        [
            _observation(
                index,
                variant=ExperimentVariant.REVISION,
                positive=True,
                cohort="coding:model-a",
            )
            for index in range(25)
        ]
        + [
            _observation(
                index,
                variant=ExperimentVariant.CONTROL,
                positive=False,
                cohort="research:model-b",
            )
            for index in range(25)
        ]
        + [
            _observation(
                99,
                variant=ExperimentVariant.REVISION,
                positive=True,
                product_id="product:foreign",
            )
        ]
    )
    receipt = evaluate_revision_effectiveness(
        observations,
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert receipt.conclusion is EffectConclusion.UNPROVEN
    assert receipt.treatment_count == 0
    assert receipt.control_count == 0
    assert len(receipt.excluded_observation_ids) == 50


def test_unused_and_stale_are_explicit_and_only_stale_can_propose_retirement() -> None:
    unused = evaluate_revision_effectiveness(
        (
            _observation(
                1,
                variant=ExperimentVariant.REVISION,
                positive=True,
                used=False,
            ),
        ),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    stale = evaluate_revision_effectiveness(
        (
            _observation(
                1,
                variant=ExperimentVariant.REVISION,
                positive=True,
                observed_at=NOW - timedelta(days=120),
            ),
        ),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert unused.conclusion is EffectConclusion.UNUSED
    assert propose_from_effectiveness(unused) is None
    assert stale.conclusion is EffectConclusion.STALE
    proposal = propose_from_effectiveness(stale)
    assert proposal is not None
    assert proposal.action == "retire"
    assert proposal.requires_human_review is True


def test_evaluation_is_deterministic_under_observation_reordering() -> None:
    observations = _matched(treatment_positive=30, control_positive=10)
    first = evaluate_revision_effectiveness(
        observations,
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    second = evaluate_revision_effectiveness(
        tuple(reversed(observations)),
        product_id="product:test",
        revision_id="cognition_revision:test",
        now=NOW,
    )
    assert first == second


def test_evaluation_inputs_and_receipt_cardinality_are_bounded() -> None:
    observation = _observation(1, variant=ExperimentVariant.REVISION, positive=True)
    with pytest.raises(ValueError, match="limited to 10000 observations"):
        evaluate_revision_effectiveness(
            (observation,) * 10_001,
            product_id="product:test",
            revision_id="cognition_revision:test",
            now=NOW,
        )
