"""Provider-neutral contracts for preregistered composition evaluation.

The contracts in this module describe immutable evaluation evidence only. They
do not execute participants, carry reusable authority, activate a composition
policy, alter a roster, schedule work, deliver or export data, send an external
effect, or write Agent Memory.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import CompositionBudgetV1Alpha1, ExactArtifactReferenceV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

COMPOSITION_EVALUATION_PROTOCOL_VERSION = "ace.intelligence.composition-evaluation-protocol/v1alpha1"
COMPOSITION_CONDITION_ASSIGNMENT_VERSION = "ace.intelligence.composition-condition-assignment/v1alpha1"
COMPOSITION_RUN_OBSERVATION_VERSION = "ace.intelligence.composition-run-observation/v1alpha1"
COMPOSITION_MATCHED_COMPARISON_VERSION = "ace.intelligence.composition-matched-comparison/v1alpha1"
COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION = "ace.intelligence.composition-policy-change-proposal/v1alpha1"
COMPOSITION_POLICY_PROPOSAL_DISPOSITION_VERSION = "ace.intelligence.composition-policy-proposal-disposition/v1alpha1"

MAX_REFERENCES = 256
EXPECTED_CONDITIONS = {"fixed_minimal", "fixed_multi", "dynamic"}


class _Contract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:") or value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    return value


def _unique_strings(values: tuple[str, ...], *, name: str, minimum: int = 0) -> tuple[str, ...]:
    if len(values) < minimum or len(values) > MAX_REFERENCES:
        raise ValueError(f"{name} must contain between {minimum} and {MAX_REFERENCES} values")
    normalized = tuple(sorted(_bounded(item, name=name) for item in values))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must be unique")
    return normalized


def _unique_refs(
    values: tuple[ExactArtifactReferenceV1Alpha1, ...], *, name: str, minimum: int = 0
) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
    if len(values) < minimum or len(values) > MAX_REFERENCES:
        raise ValueError(f"{name} must contain between {minimum} and {MAX_REFERENCES} values")
    identities = [(item.artifact_contract, item.artifact_id, item.artifact_digest) for item in values]
    if len(identities) != len(set(identities)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values, key=lambda item: (item.artifact_contract, item.artifact_id, item.artifact_digest)))


def _identity(instance: _Contract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact contract material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class CompositionEvaluationCondition(StrEnum):
    FIXED_MINIMAL = "fixed_minimal"
    FIXED_MULTI = "fixed_multi"
    DYNAMIC = "dynamic"


class OutcomeAvailability(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class TelemetryAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class CompositionEvaluationFailure(StrEnum):
    MISSING_PARTICIPANT = "missing_participant"
    TIMEOUT = "timeout"
    ABSTENTION = "abstention"
    PARTIAL_JOIN = "partial_join"
    TAINTED_JOIN = "tainted_join"
    STALE_AUTHORITY = "stale_authority"
    REVOKED_AUTHORITY = "revoked_authority"
    ROTATED_AUTHORITY = "rotated_authority"
    DELIVERY_DENIED = "delivery_denied"
    EFFECT_DENIED = "effect_denied"
    USAGE_TELEMETRY_UNAVAILABLE = "usage_telemetry_unavailable"
    COST_TELEMETRY_UNAVAILABLE = "cost_telemetry_unavailable"
    DUPLICATE_EFFECT_PREVENTED = "duplicate_effect_prevented"
    POLICY_SELF_ACTIVATION_ATTEMPT = "policy_self_activation_attempt"


class CompositionComparisonDisposition(StrEnum):
    DYNAMIC_MATERIALLY_HELPS = "dynamic_materially_helps"
    CONTROL_SUFFICES = "control_suffices"
    NO_MATERIAL_BENEFIT = "no_material_benefit"
    UNPROVEN_FAIL_CLOSED = "unproven_fail_closed"


class CompositionPolicyProposalDisposition(StrEnum):
    ACCEPT_FOR_SEPARATE_ADMISSION = "accept_for_separate_admission"
    REJECT = "reject"
    SUPERSEDE = "supersede"
    ROLLBACK = "rollback"


class CompositionMaterialityThresholdsV1Alpha1(_Contract):
    minimum_evidence_closure_gain_bps: int = Field(ge=0, le=10_000)
    minimum_material_participants: int = Field(ge=1, le=64)
    minimum_observed_outcome_gain: int = Field(ge=0)
    maximum_latency_increase_ms: int = Field(ge=0)
    maximum_model_call_increase: int = Field(ge=0)
    maximum_tool_call_increase: int = Field(ge=0)
    maximum_token_increase: int = Field(ge=0)
    maximum_cost_increase_microunits: int = Field(ge=0)
    require_complete_usage_and_cost_telemetry: bool = True


class CompositionHeldConstantsV1Alpha1(_Contract):
    provider_ref: str
    model_ref: str
    model_version_ref: str
    randomness_seed: int = Field(ge=0)
    time_assumption_ref: str
    authority_scope_ref: str
    destination_policy_ref: str
    budget: CompositionBudgetV1Alpha1

    @field_validator(
        "provider_ref",
        "model_ref",
        "model_version_ref",
        "time_assumption_ref",
        "authority_scope_ref",
        "destination_policy_ref",
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)


class CompositionEvaluationProtocolV1Alpha1(_Contract):
    """Frozen registration that must exist before any assigned observation."""

    contract: Literal["ace.intelligence.composition-evaluation-protocol/v1alpha1"] = (
        COMPOSITION_EVALUATION_PROTOCOL_VERSION
    )
    product_id: str
    protocol_key: str
    task_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    evidence_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    context_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    admissible_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    evidence_closure_criteria: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    material_use_criteria: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    conditions: tuple[CompositionEvaluationCondition, ...] = Field(min_length=3, max_length=3)
    held_constants: CompositionHeldConstantsV1Alpha1
    thresholds: CompositionMaterialityThresholdsV1Alpha1
    failure_taxonomy: tuple[CompositionEvaluationFailure, ...] = Field(
        min_length=len(CompositionEvaluationFailure), max_length=len(CompositionEvaluationFailure)
    )
    evaluation_authority: ExactArtifactReferenceV1Alpha1
    current_governed_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=2, max_length=64)
    preregistered_at: datetime
    frozen_before_observation: Literal[True] = True
    protocol_id: str | None = None
    protocol_digest: str | None = None

    @field_validator("product_id", "protocol_key")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("task_inputs", "evidence_inputs", "context_inputs")
    @classmethod
    def normalize_inputs(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...], info
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name=info.field_name, minimum=1)

    @field_validator("admissible_output_contracts", "evidence_closure_criteria", "material_use_criteria")
    @classmethod
    def normalize_criteria(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _unique_strings(value, name=info.field_name, minimum=1)

    @field_validator("conditions")
    @classmethod
    def normalize_conditions(
        cls, value: tuple[CompositionEvaluationCondition, ...]
    ) -> tuple[CompositionEvaluationCondition, ...]:
        if {item.value for item in value} != EXPECTED_CONDITIONS:
            raise ValueError(
                "protocol must preregister fixed minimal, fixed multi, and dynamic conditions exactly once"
            )
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("failure_taxonomy")
    @classmethod
    def normalize_failures(
        cls, value: tuple[CompositionEvaluationFailure, ...]
    ) -> tuple[CompositionEvaluationFailure, ...]:
        if set(value) != set(CompositionEvaluationFailure) or len(value) != len(set(value)):
            raise ValueError("protocol must freeze the complete AC6 failure taxonomy exactly once")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("current_governed_heads")
    @classmethod
    def normalize_heads(
        cls, value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        keys = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("current governed heads must be unique")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @field_validator("preregistered_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="preregistered_at")

    @field_validator("protocol_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="protocol_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_authority_and_identity(self) -> Self:
        if any(item.product_id != self.product_id for item in self.current_governed_heads):
            raise ValueError("protocol crossed governed-head product scope")
        if self.evaluation_authority.artifact_contract != (
            "ace.application.composition-evaluation-authority-resolution/v1alpha1"
        ):
            raise ValueError("protocol requires exact present-tense composition-evaluation authority")
        forbidden = {
            "ace.application.domain-activation-commit-reference/v1alpha2",
            "ace.application.prepared-lifecycle-delivery/v1alpha1",
            "ace.core.delivery-receipt/v1alpha1",
            "ace.core.portability-receipt/v1alpha1",
        }
        if self.evaluation_authority.artifact_contract in forbidden:
            raise ValueError("historical activation or delivery/export evidence cannot authorize evaluation")
        _identity(
            self, prefix="composition_evaluation_protocol", id_field="protocol_id", digest_field="protocol_digest"
        )
        return self


class CompositionConditionPlanV1Alpha1(_Contract):
    condition: CompositionEvaluationCondition
    composition_plan: ExactArtifactReferenceV1Alpha1
    participant_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    composition_policy_ref: str

    @field_validator("participant_refs")
    @classmethod
    def normalize_participants(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(value, name="participant_refs", minimum=1)

    @field_validator("composition_policy_ref")
    @classmethod
    def validate_policy_ref(cls, value: str) -> str:
        return _bounded(value, name="composition_policy_ref")


class CompositionConditionAssignmentV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.composition-condition-assignment/v1alpha1"] = (
        COMPOSITION_CONDITION_ASSIGNMENT_VERSION
    )
    product_id: str
    protocol: ExactArtifactReferenceV1Alpha1
    pair_key: str
    task_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    evidence_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    context_inputs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    condition_plans: tuple[CompositionConditionPlanV1Alpha1, ...] = Field(min_length=3, max_length=3)
    held_constants: CompositionHeldConstantsV1Alpha1
    assigned_at: datetime
    assignment_id: str | None = None
    assignment_digest: str | None = None

    @field_validator("product_id", "pair_key")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("task_inputs", "evidence_inputs", "context_inputs")
    @classmethod
    def normalize_inputs(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...], info
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name=info.field_name, minimum=1)

    @field_validator("condition_plans")
    @classmethod
    def normalize_plans(
        cls, value: tuple[CompositionConditionPlanV1Alpha1, ...]
    ) -> tuple[CompositionConditionPlanV1Alpha1, ...]:
        if {item.condition.value for item in value} != EXPECTED_CONDITIONS:
            raise ValueError("assignment must bind all three preregistered conditions exactly once")
        return tuple(sorted(value, key=lambda item: item.condition.value))

    @field_validator("assigned_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="assigned_at")

    @field_validator("assignment_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="assignment_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.protocol.artifact_contract != COMPOSITION_EVALUATION_PROTOCOL_VERSION:
            raise ValueError("assignment requires one exact frozen evaluation protocol")
        _identity(
            self, prefix="composition_condition_assignment", id_field="assignment_id", digest_field="assignment_digest"
        )
        return self


class CompositionMaterialUseV1Alpha1(_Contract):
    participant_ref: str
    participant_output: ExactArtifactReferenceV1Alpha1
    final_output: ExactArtifactReferenceV1Alpha1
    use_kind: Literal["cited", "structurally_incorporated", "decision_material"]

    @field_validator("participant_ref")
    @classmethod
    def validate_participant(cls, value: str) -> str:
        return _bounded(value, name="participant_ref")


class CompositionEvaluationDeviationV1Alpha1(_Contract):
    code: str
    detail: str = Field(max_length=1_000)
    disqualifies_pair: bool

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return _bounded(value, name="code")

    @field_validator("detail")
    @classmethod
    def validate_detail(cls, value: str) -> str:
        return _bounded(value, name="detail", maximum=1_000)


class CompositionRunMetricsV1Alpha1(_Contract):
    valid_completion: bool
    evidence_closure_bps: int = Field(ge=0, le=10_000)
    material_participant_count: int = Field(ge=0, le=64)
    outcome_availability: OutcomeAvailability
    bounded_outcome_value: int | None = None
    latency_ms: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    token_telemetry: TelemetryAvailability
    tokens: int | None = Field(default=None, ge=0)
    cost_telemetry: TelemetryAvailability
    cost_microunits: int | None = Field(default=None, ge=0)
    failures: tuple[CompositionEvaluationFailure, ...] = Field(default_factory=tuple, max_length=32)
    timeouts: int = Field(default=0, ge=0)
    abstentions: int = Field(default=0, ge=0)
    partial_joins: int = Field(default=0, ge=0)
    tainted_joins: int = Field(default=0, ge=0)
    authority_denials: int = Field(default=0, ge=0)
    destination_denials: int = Field(default=0, ge=0)
    effect_denials: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    duplicate_effects_prevented: int = Field(default=0, ge=0)

    @field_validator("failures")
    @classmethod
    def normalize_failures(
        cls, value: tuple[CompositionEvaluationFailure, ...]
    ) -> tuple[CompositionEvaluationFailure, ...]:
        if len(value) != len(set(value)):
            raise ValueError("observed failures must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @model_validator(mode="after")
    def validate_telemetry_and_outcome(self) -> Self:
        if (self.token_telemetry is TelemetryAvailability.AVAILABLE) != (self.tokens is not None):
            raise ValueError("token telemetry availability must match the observed token value")
        if (self.cost_telemetry is TelemetryAvailability.AVAILABLE) != (self.cost_microunits is not None):
            raise ValueError("cost telemetry availability must match the observed cost value")
        if (self.outcome_availability is OutcomeAvailability.OBSERVED) != (self.bounded_outcome_value is not None):
            raise ValueError("bounded outcome availability must match the observed outcome value")
        if self.timeouts and CompositionEvaluationFailure.TIMEOUT not in self.failures:
            raise ValueError("timeouts require the timeout failure classification")
        if self.abstentions and CompositionEvaluationFailure.ABSTENTION not in self.failures:
            raise ValueError("abstentions require the abstention failure classification")
        if self.partial_joins and CompositionEvaluationFailure.PARTIAL_JOIN not in self.failures:
            raise ValueError("partial joins require the partial-join failure classification")
        if self.tainted_joins and CompositionEvaluationFailure.TAINTED_JOIN not in self.failures:
            raise ValueError("tainted joins require the tainted-join failure classification")
        return self


class CompositionRunObservationV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.composition-run-observation/v1alpha1"] = COMPOSITION_RUN_OBSERVATION_VERSION
    product_id: str
    protocol: ExactArtifactReferenceV1Alpha1
    assignment: ExactArtifactReferenceV1Alpha1
    pair_key: str
    condition: CompositionEvaluationCondition
    invocation: ExactArtifactReferenceV1Alpha1
    run_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    authority_resolutions: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    output_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    cited_evidence: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(max_length=MAX_REFERENCES)
    material_uses: tuple[CompositionMaterialUseV1Alpha1, ...] = Field(max_length=64)
    metrics: CompositionRunMetricsV1Alpha1
    deviations: tuple[CompositionEvaluationDeviationV1Alpha1, ...] = Field(default_factory=tuple, max_length=64)
    observed_at: datetime
    observation_id: str | None = None
    observation_digest: str | None = None

    @field_validator("product_id", "pair_key")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("run_receipts", "authority_resolutions", "output_artifacts", "cited_evidence")
    @classmethod
    def normalize_refs(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...], info
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        minimum = 0 if info.field_name == "cited_evidence" else 1
        return _unique_refs(value, name=info.field_name, minimum=minimum)

    @field_validator("material_uses")
    @classmethod
    def normalize_uses(
        cls, value: tuple[CompositionMaterialUseV1Alpha1, ...]
    ) -> tuple[CompositionMaterialUseV1Alpha1, ...]:
        keys = [
            (item.participant_ref, item.participant_output.artifact_id, item.final_output.artifact_id) for item in value
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("material-use bindings must be unique")
        return tuple(sorted(value, key=lambda item: (item.participant_ref, item.participant_output.artifact_id)))

    @field_validator("deviations")
    @classmethod
    def normalize_deviations(
        cls, value: tuple[CompositionEvaluationDeviationV1Alpha1, ...]
    ) -> tuple[CompositionEvaluationDeviationV1Alpha1, ...]:
        codes = [item.code for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("each observed deviation code may appear only once")
        return tuple(sorted(value, key=lambda item: item.code))

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="observed_at")

    @field_validator("observation_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="observation_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        if self.protocol.artifact_contract != COMPOSITION_EVALUATION_PROTOCOL_VERSION:
            raise ValueError("observation requires the exact preregistered protocol")
        if self.assignment.artifact_contract != COMPOSITION_CONDITION_ASSIGNMENT_VERSION:
            raise ValueError("observation requires the exact condition assignment")
        output_set = set(self.output_artifacts)
        if any(
            item.participant_output not in output_set or item.final_output not in output_set
            for item in self.material_uses
        ):
            raise ValueError("material use must bind exact observed output artifacts")
        if self.metrics.material_participant_count != len({item.participant_ref for item in self.material_uses}):
            raise ValueError("material participant count must equal exact material-use bindings")
        _identity(
            self, prefix="composition_run_observation", id_field="observation_id", digest_field="observation_digest"
        )
        return self


class CompositionConditionResultV1Alpha1(_Contract):
    condition: CompositionEvaluationCondition
    observation: ExactArtifactReferenceV1Alpha1
    valid_completion: bool
    evidence_closure_bps: int = Field(ge=0, le=10_000)
    material_participant_count: int = Field(ge=0, le=64)
    bounded_outcome_value: int | None = None
    latency_ms: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    tokens: int | None = Field(default=None, ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)
    failures: tuple[CompositionEvaluationFailure, ...] = Field(default_factory=tuple, max_length=32)


class CompositionMatchedComparisonV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.composition-matched-comparison/v1alpha1"] = (
        COMPOSITION_MATCHED_COMPARISON_VERSION
    )
    product_id: str
    protocol: ExactArtifactReferenceV1Alpha1
    assignment: ExactArtifactReferenceV1Alpha1
    pair_key: str
    condition_results: tuple[CompositionConditionResultV1Alpha1, ...] = Field(min_length=3, max_length=3)
    selected_control: CompositionEvaluationCondition
    disposition: CompositionComparisonDisposition
    paired_and_controlled: bool
    deviations: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=32)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=32)
    compared_at: datetime
    comparison_id: str | None = None
    comparison_digest: str | None = None

    @field_validator("product_id", "pair_key")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("condition_results")
    @classmethod
    def normalize_results(
        cls, value: tuple[CompositionConditionResultV1Alpha1, ...]
    ) -> tuple[CompositionConditionResultV1Alpha1, ...]:
        if {item.condition.value for item in value} != EXPECTED_CONDITIONS:
            raise ValueError("comparison requires all three matched conditions exactly once")
        return tuple(sorted(value, key=lambda item: item.condition.value))

    @field_validator("deviations", "reasons", "limitations")
    @classmethod
    def normalize_text(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        minimum = 0 if info.field_name == "deviations" else 1
        return _unique_strings(value, name=info.field_name, minimum=minimum)

    @field_validator("compared_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="compared_at")

    @field_validator("comparison_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="comparison_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_claim_and_identity(self) -> Self:
        if self.selected_control is CompositionEvaluationCondition.DYNAMIC:
            raise ValueError("dynamic treatment cannot be relabeled as its own control")
        if (
            self.disposition is CompositionComparisonDisposition.DYNAMIC_MATERIALLY_HELPS
            and not self.paired_and_controlled
        ):
            raise ValueError("dynamic material benefit cannot be claimed from an unpaired or uncontrolled comparison")
        _identity(
            self, prefix="composition_matched_comparison", id_field="comparison_id", digest_field="comparison_digest"
        )
        return self


class CompositionPolicyChangeProposalV1Alpha1(_Contract):
    """Inert governed proposal; a current approval and separate admission are required."""

    contract: Literal["ace.intelligence.composition-policy-change-proposal/v1alpha1"] = (
        COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION
    )
    product_id: str
    protocol: ExactArtifactReferenceV1Alpha1
    comparison: ExactArtifactReferenceV1Alpha1
    scope_ref: str
    current_policy: ExactArtifactReferenceV1Alpha1
    proposed_policy_rule_ref: str
    rollback_policy: ExactArtifactReferenceV1Alpha1
    supersedes: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    rationale: str = Field(min_length=1, max_length=2_000)
    live_effect: Literal[False] = False
    activates_policy: Literal[False] = False
    changes_roster: Literal[False] = False
    grants_authority: Literal[False] = False
    schedules_execution: Literal[False] = False
    delivers: Literal[False] = False
    exports: Literal[False] = False
    sends_external_effect: Literal[False] = False
    writes_agent_memory: Literal[False] = False
    trains_or_rewrites_policy: Literal[False] = False
    requires_present_tense_approval: Literal[True] = True
    requires_separate_admission: Literal[True] = True
    proposed_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("product_id", "scope_ref", "proposed_policy_rule_ref")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("supersedes")
    @classmethod
    def normalize_supersedes(
        cls, value: tuple[ExactArtifactReferenceV1Alpha1, ...]
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        return _unique_refs(value, name="supersedes")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=2_000)

    @field_validator("proposed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @field_validator("proposal_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="proposal_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_lineage_and_identity(self) -> Self:
        if self.protocol.artifact_contract != COMPOSITION_EVALUATION_PROTOCOL_VERSION:
            raise ValueError("policy proposal requires the exact preregistered protocol")
        if self.comparison.artifact_contract != COMPOSITION_MATCHED_COMPARISON_VERSION:
            raise ValueError("policy proposal requires one exact matched comparison")
        if self.rollback_policy != self.current_policy:
            raise ValueError("rollback must preserve the exact current policy coordinate")
        _identity(
            self, prefix="composition_policy_change_proposal", id_field="proposal_id", digest_field="proposal_digest"
        )
        return self


class CompositionPolicyProposalDispositionV1Alpha1(_Contract):
    """Review evidence only; even acceptance cannot apply the proposal."""

    contract: Literal["ace.intelligence.composition-policy-proposal-disposition/v1alpha1"] = (
        COMPOSITION_POLICY_PROPOSAL_DISPOSITION_VERSION
    )
    product_id: str
    proposal: ExactArtifactReferenceV1Alpha1
    disposition: CompositionPolicyProposalDisposition
    present_tense_approval: ExactArtifactReferenceV1Alpha1
    current_policy_head: GovernedStateHeadPreconditionV1Alpha1
    superseding_proposal: ExactArtifactReferenceV1Alpha1 | None = None
    rationale: str = Field(min_length=1, max_length=2_000)
    applies_change: Literal[False] = False
    decided_at: datetime
    disposition_id: str | None = None
    disposition_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _bounded(value, name="product_id")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=2_000)

    @field_validator("decided_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="decided_at")

    @field_validator("disposition_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="disposition_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.proposal.artifact_contract != COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION:
            raise ValueError("disposition requires one exact inert composition-policy proposal")
        if self.current_policy_head.product_id != self.product_id:
            raise ValueError("proposal disposition crossed current policy product scope")
        if self.disposition is CompositionPolicyProposalDisposition.SUPERSEDE and self.superseding_proposal is None:
            raise ValueError("supersession requires an exact superseding proposal")
        if (
            self.disposition is not CompositionPolicyProposalDisposition.SUPERSEDE
            and self.superseding_proposal is not None
        ):
            raise ValueError("only supersession may name a superseding proposal")
        _identity(
            self,
            prefix="composition_policy_proposal_disposition",
            id_field="disposition_id",
            digest_field="disposition_digest",
        )
        return self


def measured_composition_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    contract = str(getattr(value, "contract"))
    for id_field, digest_field in (
        ("protocol_id", "protocol_digest"),
        ("assignment_id", "assignment_digest"),
        ("observation_id", "observation_digest"),
        ("comparison_id", "comparison_digest"),
        ("proposal_id", "proposal_digest"),
        ("disposition_id", "disposition_digest"),
    ):
        artifact_id = getattr(value, id_field, None)
        artifact_digest = getattr(value, digest_field, None)
        if artifact_id is not None and artifact_digest is not None:
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(artifact_id), artifact_digest=str(artifact_digest), artifact_contract=contract
            )
    raise ValueError("value does not expose measured-composition artifact coordinates")


__all__ = [
    "COMPOSITION_CONDITION_ASSIGNMENT_VERSION",
    "COMPOSITION_EVALUATION_PROTOCOL_VERSION",
    "COMPOSITION_MATCHED_COMPARISON_VERSION",
    "COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION",
    "COMPOSITION_POLICY_PROPOSAL_DISPOSITION_VERSION",
    "COMPOSITION_RUN_OBSERVATION_VERSION",
    "CompositionComparisonDisposition",
    "CompositionConditionAssignmentV1Alpha1",
    "CompositionConditionPlanV1Alpha1",
    "CompositionConditionResultV1Alpha1",
    "CompositionEvaluationCondition",
    "CompositionEvaluationDeviationV1Alpha1",
    "CompositionEvaluationFailure",
    "CompositionEvaluationProtocolV1Alpha1",
    "CompositionHeldConstantsV1Alpha1",
    "CompositionMatchedComparisonV1Alpha1",
    "CompositionMaterialityThresholdsV1Alpha1",
    "CompositionMaterialUseV1Alpha1",
    "CompositionPolicyChangeProposalV1Alpha1",
    "CompositionPolicyProposalDisposition",
    "CompositionPolicyProposalDispositionV1Alpha1",
    "CompositionRunMetricsV1Alpha1",
    "CompositionRunObservationV1Alpha1",
    "OutcomeAvailability",
    "TelemetryAvailability",
    "measured_composition_reference",
]
