"""Provider-free revision-level effectiveness evaluation and proposal emission."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from core.engine.cognition.contracts import FrozenContract, canonical_hash, stable_id

COGNITION_EFFECTIVENESS_VERSION = "ace.cognition.effectiveness/v1"
COGNITION_EFFECT_PROPOSAL_VERSION = "ace.cognition.effect-proposal/v1"
COGNITION_EFFECTIVENESS_POLICY = "ace.cognition.effectiveness-policy/v1"
MAX_EFFECT_OBSERVATIONS = 10_000
EffectToken = Annotated[str, Field(min_length=1, max_length=240)]
EffectReason = Annotated[str, Field(min_length=1, max_length=240)]


class ExperimentVariant(StrEnum):
    REVISION = "revision"
    CONTROL = "control"


class OutcomeDisposition(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class EffectConclusion(StrEnum):
    HELPED = "helped"
    HURT = "hurt"
    UNPROVEN = "unproven"
    UNUSED = "unused"
    STALE = "stale"


class CognitionOutcomeObservationV1(FrozenContract):
    observation_id: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    task_id: str = Field(min_length=1, max_length=240)
    revision_id: str = Field(min_length=1, max_length=240)
    variant: ExperimentVariant
    cohort_key: str = Field(min_length=1, max_length=240)
    use_receipt_id: str | None = Field(default=None, max_length=240)
    materially_used: bool
    outcome: OutcomeDisposition
    model_route: str = Field(min_length=1, max_length=240)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effect observation time must include a timezone")
        return value


class CognitionEffectivenessReceiptV1(FrozenContract):
    contract_version: str = COGNITION_EFFECTIVENESS_VERSION
    receipt_id: str | None = None
    product_id: EffectToken
    revision_id: EffectToken
    policy_version: str = COGNITION_EFFECTIVENESS_POLICY
    conclusion: EffectConclusion
    treatment_count: int = Field(ge=0)
    control_count: int = Field(ge=0)
    materially_used_count: int = Field(ge=0)
    matched_cohorts: tuple[EffectToken, ...] = Field(max_length=MAX_EFFECT_OBSERVATIONS)
    excluded_observation_ids: tuple[EffectToken, ...] = Field(max_length=MAX_EFFECT_OBSERVATIONS)
    treatment_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    control_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    effect_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    confidence_low: float | None = Field(default=None, ge=-1.0, le=1.0)
    confidence_high: float | None = Field(default=None, ge=-1.0, le=1.0)
    treatment_cost_usd: float = Field(ge=0.0)
    control_cost_usd: float = Field(ge=0.0)
    treatment_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    control_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    evaluated_observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reasons: tuple[EffectReason, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = stable_id(
            "cognition_effectiveness",
            self.model_dump(mode="json", exclude={"receipt_id"}),
        )
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("effectiveness receipt identity does not match exact evidence")
        object.__setattr__(self, "receipt_id", expected)
        return self


class CognitionEffectProposalV1(FrozenContract):
    contract_version: str = COGNITION_EFFECT_PROPOSAL_VERSION
    proposal_id: str | None = None
    product_id: str
    revision_id: str
    action: str = Field(pattern=r"^(revise|retire)$")
    effectiveness_receipt_id: str
    rationale: str = Field(min_length=1, max_length=2_000)
    selectable: bool = False
    requires_human_review: bool = True

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.selectable or not self.requires_human_review:
            raise ValueError("effect proposal cannot grant activation authority")
        expected = stable_id(
            "cognition_effect_proposal",
            self.model_dump(mode="json", exclude={"proposal_id"}),
        )
        if self.proposal_id is not None and self.proposal_id != expected:
            raise ValueError("effect proposal identity does not match exact evidence")
        object.__setattr__(self, "proposal_id", expected)
        return self


def _rate(items: list[CognitionOutcomeObservationV1]) -> float:
    return sum(item.outcome is OutcomeDisposition.POSITIVE for item in items) / len(items)


def _failure_rate(items: list[CognitionOutcomeObservationV1]) -> float:
    return sum(item.failure_count > 0 for item in items) / len(items)


def evaluate_revision_effectiveness(
    observations: tuple[CognitionOutcomeObservationV1, ...],
    *,
    product_id: str,
    revision_id: str,
    min_per_variant: int = 20,
    minimum_material_effect: float = 0.02,
    stale_after: timedelta = timedelta(days=90),
    now: datetime | None = None,
) -> CognitionEffectivenessReceiptV1:
    if len(observations) > MAX_EFFECT_OBSERVATIONS:
        raise ValueError(f"effectiveness evaluation is limited to {MAX_EFFECT_OBSERVATIONS} observations")
    if min_per_variant < 1 or min_per_variant > MAX_EFFECT_OBSERVATIONS // 2:
        raise ValueError("min_per_variant is outside the supported bound")
    if minimum_material_effect < 0.0 or minimum_material_effect > 1.0:
        raise ValueError("minimum_material_effect must be between zero and one")
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("effectiveness evaluation time must include a timezone")
    scoped = [item for item in observations if item.product_id == product_id and item.revision_id == revision_id]
    used = [item for item in scoped if item.variant is ExperimentVariant.REVISION and item.materially_used]
    if not used:
        conclusion = EffectConclusion.UNUSED
        reasons = ("no_material_use_evidence",)
        matched_treatment: list[CognitionOutcomeObservationV1] = []
        matched_control: list[CognitionOutcomeObservationV1] = []
        matched_cohorts: tuple[str, ...] = ()
        excluded = scoped
    elif max(item.observed_at for item in used) < now - stale_after:
        conclusion = EffectConclusion.STALE
        reasons = ("material_use_evidence_is_stale",)
        matched_treatment = []
        matched_control = []
        matched_cohorts = ()
        excluded = scoped
    else:
        treatment_cohorts = {
            item.cohort_key
            for item in scoped
            if item.variant is ExperimentVariant.REVISION
            and item.materially_used
            and item.outcome is not OutcomeDisposition.UNKNOWN
        }
        control_cohorts = {
            item.cohort_key
            for item in scoped
            if item.variant is ExperimentVariant.CONTROL and item.outcome is not OutcomeDisposition.UNKNOWN
        }
        matched_cohorts = tuple(sorted(treatment_cohorts & control_cohorts))
        matched_treatment = [
            item
            for item in scoped
            if item.variant is ExperimentVariant.REVISION
            and item.materially_used
            and item.cohort_key in matched_cohorts
            and item.outcome is not OutcomeDisposition.UNKNOWN
        ]
        matched_control = [
            item
            for item in scoped
            if item.variant is ExperimentVariant.CONTROL
            and item.cohort_key in matched_cohorts
            and item.outcome is not OutcomeDisposition.UNKNOWN
        ]
        included_ids = {item.observation_id for item in matched_treatment + matched_control}
        excluded = [item for item in scoped if item.observation_id not in included_ids]
        if len(matched_treatment) < min_per_variant or len(matched_control) < min_per_variant:
            conclusion = EffectConclusion.UNPROVEN
            reasons = (
                "insufficient_matched_treatment_or_control_samples",
                "no_single_task_benefit_claim",
            )
        else:
            treatment_rate = _rate(matched_treatment)
            control_rate = _rate(matched_control)
            delta = treatment_rate - control_rate
            standard_error = math.sqrt(
                treatment_rate * (1 - treatment_rate) / len(matched_treatment)
                + control_rate * (1 - control_rate) / len(matched_control)
            )
            low = max(-1.0, delta - 1.96 * standard_error)
            high = min(1.0, delta + 1.96 * standard_error)
            if low > minimum_material_effect:
                conclusion = EffectConclusion.HELPED
                reasons = ("matched_effect_interval_above_material_threshold",)
            elif high < -minimum_material_effect:
                conclusion = EffectConclusion.HURT
                reasons = ("matched_effect_interval_below_harm_threshold",)
            else:
                conclusion = EffectConclusion.UNPROVEN
                reasons = ("confidence_interval_includes_null_or_immaterial_effect",)

    treatment_rate = _rate(matched_treatment) if matched_treatment else None
    control_rate = _rate(matched_control) if matched_control else None
    delta = treatment_rate - control_rate if treatment_rate is not None and control_rate is not None else None
    if delta is not None and matched_treatment and matched_control:
        standard_error = math.sqrt(
            treatment_rate * (1 - treatment_rate) / len(matched_treatment)
            + control_rate * (1 - control_rate) / len(matched_control)
        )
        low = max(-1.0, delta - 1.96 * standard_error)
        high = min(1.0, delta + 1.96 * standard_error)
    else:
        low = high = None
    evidence = sorted(
        (item.model_dump(mode="json") for item in scoped),
        key=lambda item: item["observation_id"],
    )
    return CognitionEffectivenessReceiptV1(
        product_id=product_id,
        revision_id=revision_id,
        conclusion=conclusion,
        treatment_count=len(matched_treatment),
        control_count=len(matched_control),
        materially_used_count=len(used),
        matched_cohorts=matched_cohorts,
        excluded_observation_ids=tuple(sorted(item.observation_id for item in excluded)),
        treatment_positive_rate=treatment_rate,
        control_positive_rate=control_rate,
        effect_delta=delta,
        confidence_low=low,
        confidence_high=high,
        treatment_cost_usd=sum(item.cost_usd for item in matched_treatment),
        control_cost_usd=sum(item.cost_usd for item in matched_control),
        treatment_failure_rate=_failure_rate(matched_treatment) if matched_treatment else None,
        control_failure_rate=_failure_rate(matched_control) if matched_control else None,
        evaluated_observation_hash=canonical_hash(evidence),
        reasons=reasons,
    )


def propose_from_effectiveness(
    receipt: CognitionEffectivenessReceiptV1,
) -> CognitionEffectProposalV1 | None:
    if receipt.conclusion is EffectConclusion.HURT:
        return CognitionEffectProposalV1(
            product_id=receipt.product_id,
            revision_id=receipt.revision_id,
            action="revise",
            effectiveness_receipt_id=str(receipt.receipt_id),
            rationale=(
                "Matched treatment/control evidence indicates harm; inspect the exact revision and "
                "create a human-reviewed correction or retirement decision."
            ),
        )
    if receipt.conclusion is EffectConclusion.STALE:
        return CognitionEffectProposalV1(
            product_id=receipt.product_id,
            revision_id=receipt.revision_id,
            action="retire",
            effectiveness_receipt_id=str(receipt.receipt_id),
            rationale="The last material-use evidence is stale; human review is required before retirement.",
        )
    return None
