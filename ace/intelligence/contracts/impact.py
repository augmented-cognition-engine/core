"""Domain-neutral measured-impact contracts.

Products own the criterion, comparison conditions, outcome measure, and the
mapping from a classification to a proposed governance action. Intelligence
owns only the provider-free ``useful``/``harmful``/``unproven`` evaluation
shape. Core-owned immutable references keep every artifact, use, Decision,
Action, Outcome, evaluation, and proposal exactly attributable.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictFloat, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.records import ImmutableRecordReferenceV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

IMPACT_CRITERION_VERSION = "ace.intelligence.impact-criterion/v1alpha1"
IMPACT_CONDITIONS_VERSION = "ace.intelligence.impact-conditions/v1alpha1"
IMPACT_OUTCOME_MEASURES_VERSION = "ace.intelligence.impact-outcome-measures/v1alpha1"
IMPACT_EVIDENCE_VERSION = "ace.intelligence.impact-evidence/v1alpha1"
IMPACT_EVALUATION_REQUEST_VERSION = "ace.intelligence.impact-evaluation-request/v1alpha1"
IMPACT_EVALUATION_VERSION = "ace.intelligence.impact-evaluation/v1alpha1"
IMPACT_GOVERNANCE_PROPOSAL_VERSION = "ace.intelligence.impact-governance-proposal/v1alpha1"

MAX_IMPACT_EVIDENCE = 1_000


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _finite(value: Any, *, name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite float without coercion")
    return value


def _canonical_object(value: str, *, name: str, maximum: int = 32_000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be bounded canonical JSON")
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite JSON") from exc
    if not isinstance(parsed, dict) or canonical_json(parsed) != value:
        raise ValueError(f"{name} must be one canonical JSON object")
    return value


def _derive_identity(
    instance: _StrictFrozenContract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class ImpactTargetKind(StrEnum):
    INTELLIGENCE_ARTIFACT = "intelligence_artifact"
    COGNITION_REVISION = "cognition_revision"


class ImpactMetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class ImpactClassification(StrEnum):
    USEFUL = "useful"
    HARMFUL = "harmful"
    UNPROVEN = "unproven"


class ImpactGovernanceAction(StrEnum):
    PROMOTE = "promote"
    REJECT = "reject"
    ROLLBACK = "rollback"
    RETIRE = "retire"


class ImpactCriterionV1Alpha1(_StrictFrozenContract):
    """One product-owned, Core-governed impact rule frozen before evaluation."""

    contract: Literal["ace.intelligence.impact-criterion/v1alpha1"] = IMPACT_CRITERION_VERSION
    product_id: str
    criterion_id: str
    criterion_version: str
    target_kind: ImpactTargetKind
    outcome_type: str
    measure_id: str
    metric_direction: ImpactMetricDirection
    useful_effect_threshold: StrictFloat = Field(gt=0.0)
    harmful_effect_threshold: StrictFloat = Field(gt=0.0)
    minimum_matched_pairs: int = Field(ge=2, le=MAX_IMPACT_EVIDENCE)
    requires_reviewed_action: bool = True
    useful_action: Literal[ImpactGovernanceAction.PROMOTE] | None = ImpactGovernanceAction.PROMOTE
    harmful_action: Literal[
        ImpactGovernanceAction.REJECT,
        ImpactGovernanceAction.ROLLBACK,
        ImpactGovernanceAction.RETIRE,
    ]
    unproven_action: Literal[ImpactGovernanceAction.REJECT, ImpactGovernanceAction.RETIRE] | None = None
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    frozen_at: datetime
    criterion_digest: str | None = None

    @field_validator("product_id", "criterion_id", "criterion_version", "outcome_type", "measure_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("useful_effect_threshold", "harmful_effect_threshold", mode="before")
    @classmethod
    def validate_thresholds(cls, value: Any, info) -> float:
        return _finite(value, name=info.field_name)

    @field_validator("frozen_at")
    @classmethod
    def normalize_frozen_at(cls, value: datetime) -> datetime:
        return _aware(value, name="frozen_at")

    @model_validator(mode="after")
    def validate_scope_and_digest(self) -> Self:
        if self.state_head_precondition.product_id != self.product_id:
            raise ValueError("impact criterion state head crossed exact product scope")
        if self.state_head_precondition.state_kind != "impact_criterion":
            raise ValueError("impact criterion requires an exact impact_criterion governed-state head")
        if self.state_head_precondition.state_id != self.criterion_id:
            raise ValueError("impact criterion state head does not name the exact criterion")
        expected = f"sha256:{canonical_hash(self.model_dump(mode='json', exclude={'criterion_digest'}))}"
        if self.criterion_digest is not None and self.criterion_digest != expected:
            raise ValueError("criterion_digest does not match exact criterion material")
        object.__setattr__(self, "criterion_digest", expected)
        return self


class ImpactConditionsV1Alpha1(_StrictFrozenContract):
    """Frozen matched-condition material; display labels never establish a match."""

    contract: Literal["ace.intelligence.impact-conditions/v1alpha1"] = IMPACT_CONDITIONS_VERSION
    product_id: str
    condition_key: str
    route_id: str
    context_json: str
    observation_window_start: datetime
    observation_window_end: datetime
    frozen_at: datetime
    conditions_id: str | None = None
    conditions_digest: str | None = None

    @field_validator("product_id", "condition_key", "route_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("context_json")
    @classmethod
    def validate_context(cls, value: str) -> str:
        return _canonical_object(value, name="context_json")

    @field_validator("observation_window_start", "observation_window_end", "frozen_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_window_and_identity(self) -> Self:
        if self.observation_window_end <= self.observation_window_start:
            raise ValueError("impact observation window must be positive")
        if self.frozen_at > self.observation_window_start:
            raise ValueError("impact conditions must be frozen before the observation window")
        _derive_identity(
            self,
            prefix="impact_conditions",
            id_field="conditions_id",
            digest_field="conditions_digest",
        )
        return self


class ImpactOutcomeMeasuresV1Alpha1(_StrictFrozenContract):
    """Domain-neutral measured fields carried inside one exact Core Outcome."""

    contract: Literal["ace.intelligence.impact-outcome-measures/v1alpha1"] = IMPACT_OUTCOME_MEASURES_VERSION
    primary_value: StrictFloat | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    cost_usd: StrictFloat | None = Field(default=None, ge=0.0)
    failure_count: int = Field(default=0, ge=0)
    degraded: bool = False
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=16)

    @field_validator("primary_value", "cost_usd", mode="before")
    @classmethod
    def validate_floats(cls, value: Any, info) -> float | None:
        return _finite(value, name=info.field_name) if value is not None else None

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bounded = tuple(sorted(_bounded(item, name="limitation", maximum=240) for item in value))
        if len(bounded) != len(set(bounded)):
            raise ValueError("impact outcome limitations must be unique")
        return bounded


class ImpactEvidenceV1Alpha1(_StrictFrozenContract):
    """One treatment/control pair with exact Core-owned lifecycle coordinates."""

    contract: Literal["ace.intelligence.impact-evidence/v1alpha1"] = IMPACT_EVIDENCE_VERSION
    product_id: str
    evidence_key: str
    treatment_attribution: ImmutableRecordReferenceV1 | None = None
    control_attribution: ImmutableRecordReferenceV1 | None = None
    treatment_decision: ImmutableRecordReferenceV1
    control_decision: ImmutableRecordReferenceV1
    treatment_action_review: ImmutableRecordReferenceV1 | None = None
    treatment_action_admission: ImmutableRecordReferenceV1 | None = None
    treatment_action_terminal: ImmutableRecordReferenceV1 | None = None
    control_action_review: ImmutableRecordReferenceV1 | None = None
    control_action_admission: ImmutableRecordReferenceV1 | None = None
    control_action_terminal: ImmutableRecordReferenceV1 | None = None
    treatment_outcome: ImmutableRecordReferenceV1 | None = None
    control_outcome: ImmutableRecordReferenceV1 | None = None
    treatment_outcome_unavailable_reason: str | None = None
    control_outcome_unavailable_reason: str | None = None
    treatment_conditions: ImpactConditionsV1Alpha1
    control_conditions: ImpactConditionsV1Alpha1
    evidence_id: str | None = None
    evidence_digest: str | None = None

    @field_validator("product_id", "evidence_key")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("treatment_outcome_unavailable_reason", "control_outcome_unavailable_reason")
    @classmethod
    def validate_unavailable_reason(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_scope_presence_and_identity(self) -> Self:
        references = tuple(
            item
            for item in (
                self.treatment_attribution,
                self.control_attribution,
                self.treatment_decision,
                self.control_decision,
                self.treatment_action_review,
                self.treatment_action_admission,
                self.treatment_action_terminal,
                self.control_action_review,
                self.control_action_admission,
                self.control_action_terminal,
                self.treatment_outcome,
                self.control_outcome,
            )
            if item is not None
        )
        if any(item.product_id != self.product_id for item in references):
            raise ValueError("impact evidence crossed exact product scope")
        if (
            self.treatment_conditions.product_id != self.product_id
            or self.control_conditions.product_id != self.product_id
        ):
            raise ValueError("impact conditions crossed exact evidence product scope")
        if (self.treatment_outcome is None) != (self.treatment_outcome_unavailable_reason is not None):
            raise ValueError("treatment outcome absence requires exactly one explicit reason")
        if (self.control_outcome is None) != (self.control_outcome_unavailable_reason is not None):
            raise ValueError("control outcome absence requires exactly one explicit reason")
        if self.treatment_decision.storage_id == self.control_decision.storage_id:
            raise ValueError("treatment and control require distinct Decision identities")
        _derive_identity(
            self,
            prefix="impact_evidence",
            id_field="evidence_id",
            digest_field="evidence_digest",
        )
        return self


class ImpactEvaluationRequestV1Alpha1(_StrictFrozenContract):
    """One bounded, authenticated request to classify exact matched evidence."""

    contract: Literal["ace.intelligence.impact-evaluation-request/v1alpha1"] = IMPACT_EVALUATION_REQUEST_VERSION
    evaluation_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    criterion: ImpactCriterionV1Alpha1
    target: ImmutableRecordReferenceV1
    control: ImmutableRecordReferenceV1
    evidence: tuple[ImpactEvidenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_IMPACT_EVIDENCE)
    cutoff_at: datetime
    requested_at: datetime
    request_digest: str | None = None

    @field_validator("evaluation_key", "product_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("cutoff_at", "requested_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("evidence")
    @classmethod
    def canonicalize_evidence(cls, value: tuple[ImpactEvidenceV1Alpha1, ...]) -> tuple[ImpactEvidenceV1Alpha1, ...]:
        ids = [str(item.evidence_id) for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate impact evidence identity")
        coordinates = [
            reference.storage_id
            for item in value
            for reference in (
                item.treatment_attribution,
                item.control_attribution,
                item.treatment_decision,
                item.control_decision,
                item.treatment_action_review,
                item.treatment_action_admission,
                item.treatment_action_terminal,
                item.control_action_review,
                item.control_action_admission,
                item.control_action_terminal,
                item.treatment_outcome,
                item.control_outcome,
            )
            if reference is not None
        ]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("duplicate exact impact evidence coordinate")
        return tuple(sorted(value, key=lambda item: str(item.evidence_id)))

    @model_validator(mode="after")
    def validate_scope_time_and_digest(self) -> Self:
        if self.cutoff_at > self.requested_at:
            raise ValueError("impact evaluation request cannot predate its evidence cutoff")
        if self.target.available_at > self.cutoff_at or self.control.available_at > self.cutoff_at:
            raise ValueError("impact target and control must both be available at the evidence cutoff")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("impact evaluation request must occur inside the authenticated window")
        if (
            self.authenticated_context.product_id != self.product_id
            or self.criterion.product_id != self.product_id
            or self.target.product_id != self.product_id
            or self.control.product_id != self.product_id
            or any(item.product_id != self.product_id for item in self.evidence)
        ):
            raise ValueError("impact evaluation request crossed exact product scope")
        if self.target.storage_id == self.control.storage_id:
            raise ValueError("impact target and control must be distinct exact artifacts")
        if self.criterion.target_kind is ImpactTargetKind.COGNITION_REVISION and (
            self.target.record_kind != "cognition_revision" or self.control.record_kind != "cognition_revision"
        ):
            raise ValueError("cognition-revision impact requires exact cognition_revision records")
        if self.criterion.target_kind is ImpactTargetKind.INTELLIGENCE_ARTIFACT and (
            self.target.record_kind == "cognition_revision" or self.control.record_kind == "cognition_revision"
        ):
            raise ValueError("intelligence-artifact impact cannot relabel a cognition revision")
        expected = f"sha256:{canonical_hash(self.model_dump(mode='json', exclude={'request_digest'}))}"
        if self.request_digest is not None and self.request_digest != expected:
            raise ValueError("request_digest does not match exact evaluation material")
        object.__setattr__(self, "request_digest", expected)
        return self


class ImpactEvidenceExclusionV1Alpha1(_StrictFrozenContract):
    evidence_id: str
    reasons: tuple[str, ...] = Field(min_length=1, max_length=16)

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str) -> str:
        return _bounded(value, name="evidence_id")

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bounded = tuple(sorted(_bounded(item, name="exclusion reason", maximum=120) for item in value))
        if len(bounded) != len(set(bounded)):
            raise ValueError("impact exclusion reasons must be unique")
        return bounded


class ImpactEvaluationV1Alpha1(_StrictFrozenContract):
    """Immutable provider-free classification and explicit uncertainty receipt."""

    contract: Literal["ace.intelligence.impact-evaluation/v1alpha1"] = IMPACT_EVALUATION_VERSION
    evaluation_key: str
    request_digest: str
    product_id: str
    criterion: ImpactCriterionV1Alpha1
    target: ImmutableRecordReferenceV1
    control: ImmutableRecordReferenceV1
    cutoff_at: datetime
    evaluated_at: datetime
    classification: ImpactClassification
    included_evidence_ids: tuple[str, ...] = Field(max_length=MAX_IMPACT_EVIDENCE)
    exclusions: tuple[ImpactEvidenceExclusionV1Alpha1, ...] = Field(max_length=MAX_IMPACT_EVIDENCE)
    matched_pair_count: int = Field(ge=0, le=MAX_IMPACT_EVIDENCE)
    mean_effect: StrictFloat | None = None
    confidence_low: StrictFloat | None = None
    confidence_high: StrictFloat | None = None
    treatment_mean: StrictFloat | None = None
    control_mean: StrictFloat | None = None
    treatment_mean_latency_ms: StrictFloat | None = Field(default=None, ge=0.0)
    control_mean_latency_ms: StrictFloat | None = Field(default=None, ge=0.0)
    treatment_cost_usd: StrictFloat | None = Field(default=None, ge=0.0)
    control_cost_usd: StrictFloat | None = Field(default=None, ge=0.0)
    treatment_failure_count: int = Field(ge=0)
    control_failure_count: int = Field(ge=0)
    treatment_degraded_count: int = Field(ge=0)
    control_degraded_count: int = Field(ge=0)
    evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    reasons: tuple[str, ...] = Field(min_length=1, max_length=16)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=16)
    evaluation_id: str | None = None
    evaluation_digest: str | None = None

    @field_validator("evaluation_key", "product_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("request_digest must be a lowercase SHA-256 digest")
        return value

    @field_validator("cutoff_at", "evaluated_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator(
        "mean_effect",
        "confidence_low",
        "confidence_high",
        "treatment_mean",
        "control_mean",
        "treatment_mean_latency_ms",
        "control_mean_latency_ms",
        "treatment_cost_usd",
        "control_cost_usd",
        mode="before",
    )
    @classmethod
    def validate_floats(cls, value: Any, info) -> float | None:
        return _finite(value, name=info.field_name) if value is not None else None

    @field_validator("included_evidence_ids")
    @classmethod
    def validate_included_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bounded = tuple(sorted(_bounded(item, name="evidence id") for item in value))
        if len(bounded) != len(set(bounded)):
            raise ValueError("included impact evidence identities must be unique")
        return bounded

    @field_validator("exclusions")
    @classmethod
    def validate_exclusions(
        cls, value: tuple[ImpactEvidenceExclusionV1Alpha1, ...]
    ) -> tuple[ImpactEvidenceExclusionV1Alpha1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.evidence_id))
        ids = [item.evidence_id for item in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("excluded impact evidence identities must be unique")
        return ordered

    @field_validator("reasons", "limitations")
    @classmethod
    def validate_reason_text(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        bounded = tuple(sorted(_bounded(item, name=info.field_name, maximum=240) for item in value))
        if len(bounded) != len(set(bounded)):
            raise ValueError(f"{info.field_name} must be unique")
        return bounded

    @model_validator(mode="after")
    def validate_classification_and_identity(self) -> Self:
        if self.evaluated_at < self.cutoff_at:
            raise ValueError("impact evaluation cannot predate its evidence cutoff")
        if self.matched_pair_count != len(self.included_evidence_ids):
            raise ValueError("matched pair count must equal included evidence identities")
        if set(self.included_evidence_ids) & {item.evidence_id for item in self.exclusions}:
            raise ValueError("impact evidence cannot be both included and excluded")
        interval = (self.mean_effect, self.confidence_low, self.confidence_high)
        if self.matched_pair_count == 0 and any(value is not None for value in interval):
            raise ValueError("empty impact evidence cannot report an effect interval")
        if self.classification is not ImpactClassification.UNPROVEN and any(value is None for value in interval):
            raise ValueError("useful or harmful impact requires a complete effect interval")
        _derive_identity(
            self,
            prefix="impact_evaluation",
            id_field="evaluation_id",
            digest_field="evaluation_digest",
        )
        return self


class ImpactGovernanceProposalV1Alpha1(_StrictFrozenContract):
    """A non-effective proposal; it carries no activation or mutation authority."""

    contract: Literal["ace.intelligence.impact-governance-proposal/v1alpha1"] = IMPACT_GOVERNANCE_PROPOSAL_VERSION
    product_id: str
    evaluation_id: str
    evaluation_digest: str
    target: ImmutableRecordReferenceV1
    action: ImpactGovernanceAction
    rationale: str = Field(min_length=1, max_length=2_000)
    live_effect: Literal[False] = False
    selectable: Literal[False] = False
    requires_human_review: Literal[True] = True
    proposed_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("product_id", "evaluation_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("evaluation_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("evaluation_digest must be a lowercase SHA-256 digest")
        return value

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=2_000)

    @field_validator("proposed_at")
    @classmethod
    def normalize_proposed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.target.product_id != self.product_id:
            raise ValueError("impact proposal crossed exact target product scope")
        _derive_identity(
            self,
            prefix="impact_governance_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


__all__ = [
    "IMPACT_CONDITIONS_VERSION",
    "IMPACT_CRITERION_VERSION",
    "IMPACT_EVALUATION_REQUEST_VERSION",
    "IMPACT_EVALUATION_VERSION",
    "IMPACT_EVIDENCE_VERSION",
    "IMPACT_GOVERNANCE_PROPOSAL_VERSION",
    "IMPACT_OUTCOME_MEASURES_VERSION",
    "MAX_IMPACT_EVIDENCE",
    "ImpactClassification",
    "ImpactConditionsV1Alpha1",
    "ImpactCriterionV1Alpha1",
    "ImpactEvaluationRequestV1Alpha1",
    "ImpactEvaluationV1Alpha1",
    "ImpactEvidenceExclusionV1Alpha1",
    "ImpactEvidenceV1Alpha1",
    "ImpactGovernanceAction",
    "ImpactGovernanceProposalV1Alpha1",
    "ImpactMetricDirection",
    "ImpactOutcomeMeasuresV1Alpha1",
    "ImpactTargetKind",
]
