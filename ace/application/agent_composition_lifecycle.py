"""AC3 compatibility bridge for existing lifecycle execution owners.

The bridge wraps existing bounded services without changing their maturity,
provider mode, or authority.  A lifecycle service receives one frozen AC1
manifest and returns exact immutable coordinates for artifacts that it owns.
The bridge owns only task-time composition evidence.  It never activates an
agent definition, provisions a grant, sends a delivery, or claims an external
effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable, Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.agent_composition_runtime import (
    CompositionAuthorityResolutionReceiptV1Alpha1,
    TaskAuthenticationReceiptV1Alpha1,
)
from ace.core.agent_composition import (
    AuthorityClass,
    AuthorityCoordinateV1Alpha1,
    CompositionBudgetV1Alpha1,
    CompositionNodeKind,
    CompositionNodeV1Alpha1,
    CompositionParticipantV1Alpha1,
    ContextUseState,
    ExactArtifactReferenceV1Alpha1,
    HandoffState,
    ParticipantKind,
    RunState,
    StageHandoffContractV1Alpha1,
    StageHandoffReceiptV1Alpha1,
    StageRunManifestV1Alpha1,
    StageRunReceiptV1Alpha1,
    TaskCompositionPlanV1Alpha1,
    UsageV1Alpha1,
    validate_run_receipt_against_manifest,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import GovernedOperationBindingV1Alpha1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.agent_composition import LifecycleStage

LIFECYCLE_STAGE_REQUEST_VERSION = "ace.application.lifecycle-stage-request/v1alpha1"
LIFECYCLE_STAGE_PROFILE_VERSION = "ace.application.lifecycle-stage-compatibility-profile/v1alpha1"
LIFECYCLE_SERVICE_OUTCOME_VERSION = "ace.application.lifecycle-service-outcome/v1alpha1"
PREPARED_LIFECYCLE_DELIVERY_VERSION = "ace.application.prepared-lifecycle-delivery/v1alpha1"
SENTINEL_OBSERVATION_PROJECTION_VERSION = "ace.application.sentinel-observation-projection/v1alpha1"
LIFECYCLE_COMPOSITION_RECORD_SET_VERSION = "ace.application.lifecycle-composition-record-set/v1alpha1"


class LifecycleCompositionError(RuntimeError):
    """A governed lifecycle composition failed closed."""


class UnsupportedLifecycleStage(LifecycleCompositionError):
    """The bounded AC3 packet has no honest compatibility owner for a stage."""


class LifecycleOwnerFailure(LifecycleCompositionError):
    """Explicit translation of an existing owner's bounded failure semantics."""

    def __init__(
        self,
        *,
        state: RunState,
        issue_codes: tuple[str, ...],
        owner_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...] = (),
        occurred_at: datetime,
    ) -> None:
        if state not in {
            RunState.BLOCKED,
            RunState.DEGRADED,
            RunState.ABSTAINED,
            RunState.CANCELLED,
            RunState.FAILED,
        }:
            raise ValueError("owner failure requires an explicit non-success run state")
        if not issue_codes:
            raise ValueError("owner failure requires at least one issue code")
        super().__init__(", ".join(issue_codes))
        self.state = state
        self.issue_codes = issue_codes
        self.owner_receipts = owner_receipts
        self.occurred_at = _aware(occurred_at, "occurred_at")


class _StrictFrozen(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _digest(value: str, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:") or value != value.lower():
        raise ValueError(f"{name} must use sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use sha256:<64-hex> syntax") from exc
    return value


def _identity(instance: _StrictFrozen, prefix: str, id_field: str, digest_field: str) -> None:
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


def lifecycle_exact_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    contract = str(getattr(value, "contract"))
    for id_field, digest_field in (
        ("request_id", "request_digest"),
        ("outcome_id", "outcome_digest"),
        ("package_id", "package_digest"),
        ("binding_id", "binding_digest"),
        ("receipt_id", "receipt_digest"),
        ("contract_id", "contract_digest"),
        ("composition_plan_id", "composition_plan_digest"),
        ("manifest_id", "manifest_digest"),
    ):
        identity = getattr(value, id_field, None)
        digest = getattr(value, digest_field, None)
        if identity is not None and digest is not None:
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(identity),
                artifact_digest=str(digest),
                artifact_contract=contract,
            )
    raise ValueError("value does not expose an exact lifecycle coordinate")


class LifecycleStageRequestV1Alpha1(_StrictFrozen):
    """Content-free exact request to one existing lifecycle execution owner."""

    contract: Literal["ace.application.lifecycle-stage-request/v1alpha1"] = LIFECYCLE_STAGE_REQUEST_VERSION
    product_id: str
    actor_ref: str
    session_ref: str
    task_ref: str
    case_ref: str | None = None
    stage: LifecycleStage
    objective: str = Field(max_length=4_000)
    input_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=64)
    trigger_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=64)
    context_manifest: ExactArtifactReferenceV1Alpha1
    context_selection_receipt: ExactArtifactReferenceV1Alpha1
    instruction_resolution: ExactArtifactReferenceV1Alpha1
    instruction_layer_refs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=16)
    source_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    destination_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    created_at: datetime
    expires_at: datetime | None = None
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("product_id", "actor_ref", "session_ref", "task_ref", "case_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, info.field_name) if value is not None else None

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("source_scope_refs", "destination_scope_refs")
    @classmethod
    def normalize_scopes(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted(_bounded(item, info.field_name) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("request_digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        return _digest(value, "request_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("lifecycle request expiry must follow creation")
        identities = [
            (item.artifact_contract, item.artifact_id, item.artifact_digest)
            for item in (*self.input_artifacts, *self.trigger_artifacts)
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("lifecycle input and trigger coordinates must be unique")
        _identity(self, "lifecycle_stage_request", "request_id", "request_digest")
        return self


@dataclass(frozen=True, slots=True)
class LifecycleStageCompatibilityProfile:
    stage: LifecycleStage
    maturity: str
    participant_kind: ParticipantKind
    participant_refs: tuple[str, ...]
    operation: str
    authority_class: AuthorityClass
    accepted_input_contracts: tuple[str, ...]
    output_contracts: tuple[str, ...]
    next_stage_id: str
    failure_policy_ref: str
    validator_refs: tuple[str, ...]
    exit_criteria_refs: tuple[str, ...]

    def material(self) -> dict:
        return {
            "contract": LIFECYCLE_STAGE_PROFILE_VERSION,
            "stage": self.stage.value,
            "maturity": self.maturity,
            "participant_kind": self.participant_kind.value,
            "participant_refs": self.participant_refs,
            "operation": self.operation,
            "authority_class": self.authority_class.value,
            "accepted_input_contracts": self.accepted_input_contracts,
            "output_contracts": self.output_contracts,
            "next_stage_id": self.next_stage_id,
            "failure_policy_ref": self.failure_policy_ref,
            "validator_refs": self.validator_refs,
            "exit_criteria_refs": self.exit_criteria_refs,
        }

    @property
    def profile_digest(self) -> str:
        return f"sha256:{canonical_hash(self.material())}"

    @property
    def profile_id(self) -> str:
        return f"lifecycle_stage_profile:{self.profile_digest[7:39]}"

    @property
    def coordinate_ref(self) -> str:
        return f"{self.profile_id}@{self.profile_digest}"


LIFECYCLE_STAGE_PROFILES: dict[LifecycleStage, LifecycleStageCompatibilityProfile] = {
    LifecycleStage.ACQUIRE: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.ACQUIRE,
        maturity="partial_bounded_live_ingress",
        participant_kind=ParticipantKind.ADAPTER,
        participant_refs=("ace.application.LiveSourceIngressService",),
        operation="capture",
        authority_class=AuthorityClass.OBSERVE_READ,
        accepted_input_contracts=("ace.intelligence.live-source-ingress-request/v1alpha1",),
        output_contracts=(
            "ace.intelligence.source-acquisition-receipt/v1alpha1",
            "ace.intelligence.live-source-admission-receipt/v1alpha1",
            "ace.core.canonical-source-snapshot/v1alpha1",
            "ace.intelligence.observation/v1alpha1",
            "ace.intelligence.entity-snapshot/v1alpha1",
        ),
        next_stage_id=LifecycleStage.GROUND.value,
        failure_policy_ref="failure:acquire-no-silent-source-expansion-v1",
        validator_refs=("validator:exact-source-acquisition-lineage-v1",),
        exit_criteria_refs=("exit:immutable-source-admission-v1",),
    ),
    LifecycleStage.DETECT: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.DETECT,
        maturity="strong_bounded_configured_detectors",
        participant_kind=ParticipantKind.DETERMINISTIC_SERVICE,
        participant_refs=(
            "ace.intelligence.detection.numeric_delta",
            "ace.intelligence.detection.categorical_transition",
        ),
        operation="detect",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.intelligence.observation/v1alpha1",
            "ace.intelligence.entity-snapshot/v1alpha1",
        ),
        output_contracts=(
            "ace.intelligence.shift/v1alpha1",
            "ace.intelligence.signal/v1alpha1",
            "ace.application.intelligence-model-proposal/v1alpha1",
            "ace.application.intelligence-model-disposition/v1alpha1",
        ),
        next_stage_id=LifecycleStage.INVESTIGATE.value,
        failure_policy_ref="failure:detect-explicit-no-detection-v1",
        validator_refs=("validator:configured-detector-lineage-v1",),
        exit_criteria_refs=("exit:signal-shift-or-no-detection-v1",),
    ),
    LifecycleStage.INVESTIGATE: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.INVESTIGATE,
        maturity="partial_case_brief_and_bounded_research",
        participant_kind=ParticipantKind.ADAPTER,
        participant_refs=(
            "ace.application.BriefSynthesisService",
            "ace.application.CaseBriefSynthesisService",
            "ace.application.IntelligenceAgent",
            "ace.application.BriefingAgent",
        ),
        operation="investigate",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.intelligence.signal/v1alpha1",
            "ace.intelligence.shift/v1alpha1",
            "ace.application.intelligence-model-proposal/v1alpha1",
            "ace.application.intelligence-model-disposition/v1alpha1",
            "ace.application.first-briefing-preview/v1alpha1",
        ),
        output_contracts=(
            "ace.intelligence.brief/v1alpha1",
            "ace.intelligence.brief-synthesis-receipt/v1alpha1",
            "ace.intelligence.case-brief-synthesis-receipt/v1alpha1",
            "ace.application.first-briefing-preview/v1alpha1",
            "ace.application.briefing-derivation/v1alpha1",
        ),
        next_stage_id=LifecycleStage.COMPOSE.value,
        failure_policy_ref="failure:investigate-abstain-on-evidence-gap-v1",
        validator_refs=("validator:case-brief-citation-lineage-v1",),
        exit_criteria_refs=("exit:evidence-pack-or-explicit-gap-v1",),
    ),
    LifecycleStage.ACT: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.ACT,
        maturity="experimental_effect_free_action_preparation",
        participant_kind=ParticipantKind.ADAPTER,
        participant_refs=(
            "ace.core.GovernedActionExecutionService.prepare",
            "ace.core.GovernedActionReviewService.prepare_for_review",
        ),
        operation="prepare_action",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.core.action-intent/v1alpha1",
            "ace.core.decision/v1alpha1",
        ),
        output_contracts=(
            "ace.core.prepared-action/v1alpha1",
            "ace.core.action-review/v1alpha1",
        ),
        next_stage_id=LifecycleStage.VERIFY.value,
        failure_policy_ref="failure:act-preparation-no-effect-v1",
        validator_refs=("validator:prepared-action-exact-intent-v1",),
        exit_criteria_refs=("exit:effect-free-prepared-action-v1",),
    ),
    LifecycleStage.VERIFY: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.VERIFY,
        maturity="experimental_ship_verification",
        participant_kind=ParticipantKind.ADAPTER,
        participant_refs=("ace.core.GovernedActionReviewService",),
        operation="verify",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.core.prepared-action/v1alpha1",
            "ace.core.action-terminal/v1alpha1",
            "ace.core.action-review/v1alpha1",
        ),
        output_contracts=(
            "ace.core.action-verification/v1alpha1",
            "ace.core.action-repair/v1alpha1",
        ),
        next_stage_id=LifecycleStage.DELIVER.value,
        failure_policy_ref="failure:verify-veto-or-repair-v1",
        validator_refs=("validator:independent-action-verification-v1",),
        exit_criteria_refs=("exit:verification-verdict-v1",),
    ),
    LifecycleStage.DELIVER: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.DELIVER,
        maturity="prepared_handoff_only_no_send",
        participant_kind=ParticipantKind.DETERMINISTIC_SERVICE,
        participant_refs=("ace.application.PreparedLifecycleDeliveryOwner",),
        operation="prepare_delivery",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.core.action-verification/v1alpha1",
            "ace.intelligence.brief/v1alpha1",
            "ace.application.first-briefing-preview/v1alpha1",
        ),
        output_contracts=(PREPARED_LIFECYCLE_DELIVERY_VERSION,),
        next_stage_id="ac5_delivery_authority_gate",
        failure_policy_ref="failure:prepared-delivery-never-send-v1",
        validator_refs=("validator:prepared-delivery-no-effect-v1",),
        exit_criteria_refs=("exit:typed-prepared-handoff-v1",),
    ),
    LifecycleStage.OBSERVE: LifecycleStageCompatibilityProfile(
        stage=LifecycleStage.OBSERVE,
        maturity="strong_bounded_outcome_and_sentinel_paths",
        participant_kind=ParticipantKind.ADAPTER,
        participant_refs=(
            "ace.application.PreparedDecisionFeedbackService",
            "core.engine.sentinel.SentinelScheduler",
            "core.engine.arms.capture_outcome",
        ),
        operation="observe",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        accepted_input_contracts=(
            "ace.core.action-terminal/v1alpha1",
            "ace.core.stage-handoff-receipt/v1alpha1",
            "ace.core.decision/v1alpha1",
        ),
        output_contracts=(
            "ace.intelligence.feedback-proposal/v1alpha1",
            "ace.core.outcome/v1alpha1",
            SENTINEL_OBSERVATION_PROJECTION_VERSION,
        ),
        next_stage_id=LifecycleStage.LEARN_EVOLVE.value,
        failure_policy_ref="failure:observe-no-causal-overclaim-v1",
        validator_refs=("validator:outcome-applicability-lineage-v1",),
        exit_criteria_refs=("exit:observation-or-explicit-missing-outcome-v1",),
    ),
}


class LifecycleServiceOutcomeV1Alpha1(_StrictFrozen):
    """Exact output coordinates reported by the existing execution owner."""

    contract: Literal["ace.application.lifecycle-service-outcome/v1alpha1"] = LIFECYCLE_SERVICE_OUTCOME_VERSION
    stage: LifecycleStage
    participant_ref: str
    state: RunState
    output_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=64)
    owner_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=64)
    actual_route: ExactArtifactReferenceV1Alpha1 | None = None
    actual_tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    context_states: tuple[ContextUseState, ...] = Field(default_factory=tuple)
    issue_codes: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    duration_ms: int = Field(default=0, ge=0)
    external_effect_occurred: Literal[False] = False
    occurred_at: datetime
    outcome_id: str | None = None
    outcome_digest: str | None = None

    @field_validator("participant_ref")
    @classmethod
    def validate_participant(cls, value: str) -> str:
        return _bounded(value, "participant_ref")

    @field_validator("actual_tool_refs", "issue_codes")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted(_bounded(item, info.field_name) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "occurred_at")

    @field_validator("outcome_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, "outcome_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_state_and_identity(self) -> Self:
        if self.state is RunState.COMPLETE and not self.output_artifacts:
            raise ValueError("complete lifecycle service outcomes require an exact output")
        if self.state is RunState.BLOCKED and self.output_artifacts:
            raise ValueError("blocked lifecycle service outcomes cannot claim outputs")
        _identity(self, "lifecycle_service_outcome", "outcome_id", "outcome_digest")
        return self


class PreparedLifecycleDeliveryV1Alpha1(_StrictFrozen):
    """An inert package awaiting AC5 destination and delivery authority."""

    contract: Literal["ace.application.prepared-lifecycle-delivery/v1alpha1"] = (
        PREPARED_LIFECYCLE_DELIVERY_VERSION
    )
    product_id: str
    source_manifest: ExactArtifactReferenceV1Alpha1
    artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=64)
    target_ref: str
    external_send_occurred: Literal[False] = False
    prepared_at: datetime
    package_id: str | None = None
    package_digest: str | None = None

    @field_validator("product_id", "target_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("prepared_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "prepared_at")

    @field_validator("package_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, "package_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(self, "prepared_lifecycle_delivery", "package_id", "package_digest")
        return self


class SentinelObservationProjectionV1Alpha1(_StrictFrozen):
    """Immutable coordinate wrapper for one legacy sentinel observation.

    Scheduling is trigger policy only.  The projection carries neither a grant
    nor authority to mutate the observed source or prior lifecycle artifacts.
    """

    contract: Literal["ace.application.sentinel-observation-projection/v1alpha1"] = (
        SENTINEL_OBSERVATION_PROJECTION_VERSION
    )
    product_id: str
    sentinel_owner_ref: str
    source_record: ExactArtifactReferenceV1Alpha1
    trigger_receipt: ExactArtifactReferenceV1Alpha1
    disposition: Literal["observed", "degraded"]
    execution_authority: Literal[False] = False
    external_effect_occurred: Literal[False] = False
    observed_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "sentinel_owner_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, "observed_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, "receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _identity(self, "sentinel_observation", "receipt_id", "receipt_digest")
        return self


class LifecycleCompositionRuntimeAuthorityBundle(_StrictFrozen):
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    execution_binding: GovernedOperationBindingV1Alpha1
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: tuple[AuthorityUseReceiptV1Alpha1, ...] = Field(min_length=1, max_length=32)
    authority_coordinates: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(min_length=1, max_length=32)
    current_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=3, max_length=64)
    resolution_receipt: CompositionAuthorityResolutionReceiptV1Alpha1

    @model_validator(mode="after")
    def validate_exact_bundle(self) -> Self:
        receipt = self.resolution_receipt
        if (
            receipt.product_id != self.authenticated_context.product_id
            or receipt.actor_ref != self.authenticated_context.actor_ref
            or receipt.authentication_receipt_ref != self.authenticated_context.authentication_receipt_ref
            or receipt.execution_binding != lifecycle_exact_reference(self.execution_binding)
            or receipt.capability_use != lifecycle_exact_reference(self.capability_use)
            or receipt.authority_use != tuple(lifecycle_exact_reference(item) for item in self.authority_use)
            or receipt.authority_coordinates != self.authority_coordinates
            or receipt.current_heads != self.current_heads
        ):
            raise ValueError("lifecycle authority bundle crossed exact resolution material")
        return self


class LifecycleCompositionRuntimeAuthorityPort(Protocol):
    async def resolve_planning(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject: ExactArtifactReferenceV1Alpha1,
        profile: LifecycleStageCompatibilityProfile,
        participant_principal_ref: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> LifecycleCompositionRuntimeAuthorityBundle: ...

    async def resolve_pre_execution(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        manifest: StageRunManifestV1Alpha1,
        profile: LifecycleStageCompatibilityProfile,
        evaluated_at: datetime,
    ) -> LifecycleCompositionRuntimeAuthorityBundle: ...


class LifecycleExecutionOwner(Protocol):
    stage: LifecycleStage
    participant_ref: str
    participant_kind: ParticipantKind

    async def execute(self, manifest: StageRunManifestV1Alpha1) -> LifecycleServiceOutcomeV1Alpha1: ...


class BoundLifecycleExecutionOwner:
    """Small wrapper keeping each existing service as the execution owner."""

    def __init__(
        self,
        *,
        stage: LifecycleStage,
        participant_ref: str,
        participant_kind: ParticipantKind,
        executor: Callable[[StageRunManifestV1Alpha1], Awaitable[LifecycleServiceOutcomeV1Alpha1]],
    ) -> None:
        self.stage = stage
        self.participant_ref = participant_ref
        self.participant_kind = participant_kind
        self._executor = executor

    async def execute(self, manifest: StageRunManifestV1Alpha1) -> LifecycleServiceOutcomeV1Alpha1:
        return await self._executor(manifest)


class PreparedLifecycleDeliveryOwner:
    stage = LifecycleStage.DELIVER
    participant_ref = "ace.application.PreparedLifecycleDeliveryOwner"
    participant_kind = ParticipantKind.DETERMINISTIC_SERVICE

    def __init__(
        self,
        *,
        target_ref: str = "ac5_delivery_gate:required",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.target_ref = _bounded(target_ref, "target_ref")
        self.clock = clock or (lambda: datetime.now(UTC))

    async def execute(self, manifest: StageRunManifestV1Alpha1) -> LifecycleServiceOutcomeV1Alpha1:
        occurred_at = _aware(self.clock(), "prepared delivery clock")
        package = PreparedLifecycleDeliveryV1Alpha1(
            product_id=manifest.product_id,
            source_manifest=lifecycle_exact_reference(manifest),
            artifacts=manifest.input_artifacts,
            target_ref=self.target_ref,
            prepared_at=occurred_at,
        )
        reference = lifecycle_exact_reference(package)
        return LifecycleServiceOutcomeV1Alpha1(
            stage=self.stage,
            participant_ref=self.participant_ref,
            state=RunState.COMPLETE,
            output_artifacts=(reference,),
            owner_receipts=(reference,),
            occurred_at=occurred_at,
        )


@dataclass(frozen=True, slots=True)
class PreparedLifecycleComposition:
    request: LifecycleStageRequestV1Alpha1
    profile: LifecycleStageCompatibilityProfile
    plan: TaskCompositionPlanV1Alpha1
    manifest: StageRunManifestV1Alpha1
    planning_authority: LifecycleCompositionRuntimeAuthorityBundle


@dataclass(frozen=True, slots=True)
class CompletedLifecycleComposition:
    request: LifecycleStageRequestV1Alpha1
    profile: LifecycleStageCompatibilityProfile
    plan: TaskCompositionPlanV1Alpha1
    manifest: StageRunManifestV1Alpha1
    run_receipt: StageRunReceiptV1Alpha1
    service_outcome: LifecycleServiceOutcomeV1Alpha1
    handoff_contract: StageHandoffContractV1Alpha1
    handoff_receipt: StageHandoffReceiptV1Alpha1
    planning_authority_receipt: ExactArtifactReferenceV1Alpha1
    execution_authority_receipt: ExactArtifactReferenceV1Alpha1

    def projection(self) -> dict:
        return {
            "contract": LIFECYCLE_COMPOSITION_RECORD_SET_VERSION,
            "stage": self.profile.stage.value,
            "maturity": self.profile.maturity,
            "task_composition_plan": self.plan.model_dump(mode="json"),
            "stage_run_manifest": self.manifest.model_dump(mode="json"),
            "stage_run_receipt": self.run_receipt.model_dump(mode="json"),
            "service_outcome": self.service_outcome.model_dump(mode="json"),
            "stage_handoff_contract": self.handoff_contract.model_dump(mode="json"),
            "stage_handoff_receipt": self.handoff_receipt.model_dump(mode="json"),
            "planning_authority_receipt": self.planning_authority_receipt.model_dump(mode="json"),
            "execution_authority_receipt": self.execution_authority_receipt.model_dump(mode="json"),
            "external_effect_authority": False,
            "agent_definition_promoted": False,
        }


class LifecycleParticipantCompositionBridge:
    """One-stage compatibility composition with fresh current-use checks."""

    def __init__(self, *, authority: LifecycleCompositionRuntimeAuthorityPort) -> None:
        self.authority = authority

    @staticmethod
    def profile_for(stage: LifecycleStage) -> LifecycleStageCompatibilityProfile:
        try:
            return LIFECYCLE_STAGE_PROFILES[stage]
        except KeyError as exc:
            raise UnsupportedLifecycleStage(
                f"lifecycle stage {stage.value} is unsupported by the bounded AC3 compatibility packet"
            ) from exc

    @staticmethod
    def _validate_owner(profile: LifecycleStageCompatibilityProfile, owner: LifecycleExecutionOwner) -> None:
        if (
            owner.stage is not profile.stage
            or owner.participant_ref not in profile.participant_refs
            or owner.participant_kind is not profile.participant_kind
        ):
            raise LifecycleCompositionError("lifecycle execution owner crossed the exact compatibility profile")

    async def prepare(
        self,
        *,
        request: LifecycleStageRequestV1Alpha1,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        owner: LifecycleExecutionOwner,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        now: datetime | None = None,
    ) -> PreparedLifecycleComposition:
        now = _aware(now or datetime.now(UTC), "now")
        profile = self.profile_for(request.stage)
        self._validate_owner(profile, owner)
        if request.product_id != authenticated_context.product_id or request.actor_ref != authenticated_context.actor_ref:
            raise LifecycleCompositionError("lifecycle request crossed authenticated product or actor scope")
        if not (authenticated_context.authenticated_at <= now < authenticated_context.expires_at):
            raise LifecycleCompositionError("lifecycle planning falls outside the authenticated window")
        if request.created_at > now or (request.expires_at is not None and request.expires_at <= now):
            raise LifecycleCompositionError("lifecycle request is future-dated or expired")
        if not any(item.artifact_contract in profile.accepted_input_contracts for item in request.input_artifacts):
            raise LifecycleCompositionError("lifecycle request lacks a stage-compatible exact input")
        planning = await self.authority.resolve_planning(
            authenticated_context=authenticated_context,
            use_subject=lifecycle_exact_reference(request),
            profile=profile,
            participant_principal_ref=owner.participant_ref,
            grant_ref=grant_ref,
            scope_ref=scope_ref,
            policy_ref=policy_ref,
            evaluated_at=now,
        )
        participant_id = "composition_participant:" + canonical_hash(
            {"request": request.request_id, "participant": owner.participant_ref}
        )[:32]
        participant = CompositionParticipantV1Alpha1(
            composition_participant_id=participant_id,
            participant_kind=owner.participant_kind,
            participant_ref=owner.participant_ref,
            authority=planning.authority_coordinates,
            source_scope_refs=request.source_scope_refs,
            destination_scope_refs=request.destination_scope_refs,
        )
        node = CompositionNodeV1Alpha1(
            node_id=f"{profile.stage.value}:execution:1",
            node_kind=CompositionNodeKind.EXECUTION,
            composition_participant_id=participant_id,
            input_contracts=profile.accepted_input_contracts,
            output_contracts=profile.output_contracts,
            validator_refs=profile.validator_refs,
            exit_criteria_refs=profile.exit_criteria_refs,
        )
        plan = TaskCompositionPlanV1Alpha1(
            product_id=request.product_id,
            actor_ref=request.actor_ref,
            session_ref=request.session_ref,
            task_ref=request.task_ref,
            case_ref=request.case_ref,
            objective=request.objective,
            stage_id=profile.stage.value,
            trigger_artifacts=request.trigger_artifacts,
            classifier_revision_ref=profile.coordinate_ref,
            routing_revision_ref=profile.coordinate_ref,
            policy_revision_ref=policy_ref,
            composer_revision_ref="composer:ac3-lifecycle-adapter-v1",
            participants=(participant,),
            nodes=(node,),
            orchestration_pattern="deterministic" if owner.participant_kind is ParticipantKind.DETERMINISTIC_SERVICE else "solo",
            expected_output_contracts=profile.output_contracts,
            allowed_next_stage_ids=(profile.next_stage_id,),
            aggregate_budget=CompositionBudgetV1Alpha1(
                max_items=64,
                max_calls=1,
                max_latency_ms=300_000,
                max_concurrency=1,
            ),
            context_request_ref=request.context_manifest.artifact_id,
            context_receipts=(request.context_selection_receipt,),
            failure_policy_ref=profile.failure_policy_ref,
            created_at=now,
            expires_at=request.expires_at,
        )
        manifest = StageRunManifestV1Alpha1(
            plan=lifecycle_exact_reference(plan),
            product_id=request.product_id,
            stage_id=profile.stage.value,
            node_id=node.node_id,
            composition_participant_id=participant_id,
            task_ref=request.task_ref,
            invocation_key=f"lifecycle:{request.request_id}",
            instruction_resolution=request.instruction_resolution,
            instruction_layer_refs=request.instruction_layer_refs,
            context_manifest=request.context_manifest,
            source_scope_refs=request.source_scope_refs,
            destination_scope_refs=request.destination_scope_refs,
            authority=planning.authority_coordinates,
            execution_binding=lifecycle_exact_reference(planning.execution_binding),
            input_artifacts=request.input_artifacts,
            output_contracts=profile.output_contracts,
            validator_refs=profile.validator_refs,
            exit_criteria_refs=profile.exit_criteria_refs,
            handoff_target_ref=profile.next_stage_id,
            budget=plan.aggregate_budget,
            cancellation_ref="cancellation:task-owner-v1",
            retry_ref="retry:fresh-auth-and-current-use-v1",
            idempotency_key=f"lifecycle:{request.request_id}:attempt:1",
            degraded_policy_ref=profile.failure_policy_ref,
            escalation_policy_ref="escalation:unsupported-or-stale-authority-v1",
            created_at=now,
            expires_at=request.expires_at,
        )
        return PreparedLifecycleComposition(
            request=request,
            profile=profile,
            plan=plan,
            manifest=manifest,
            planning_authority=planning,
        )

    async def execute(
        self,
        *,
        prepared: PreparedLifecycleComposition,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        owner: LifecycleExecutionOwner,
        now: datetime | None = None,
        attempt: int = 1,
        retry_of_receipt_ref: str | None = None,
    ) -> CompletedLifecycleComposition:
        now = _aware(now or datetime.now(UTC), "now")
        self._validate_owner(prepared.profile, owner)
        current = await self.authority.resolve_pre_execution(
            authenticated_context=authenticated_context,
            manifest=prepared.manifest,
            profile=prepared.profile,
            evaluated_at=now,
        )
        if (
            current.execution_binding != prepared.planning_authority.execution_binding
            or current.authority_coordinates != prepared.planning_authority.authority_coordinates
            or current.current_heads != prepared.planning_authority.current_heads
        ):
            raise LifecycleCompositionError("lifecycle authority rotated between planning and execution")
        try:
            outcome = await owner.execute(prepared.manifest)
        except LifecycleOwnerFailure as failure:
            outcome = LifecycleServiceOutcomeV1Alpha1(
                stage=prepared.profile.stage,
                participant_ref=owner.participant_ref,
                state=failure.state,
                owner_receipts=failure.owner_receipts,
                issue_codes=failure.issue_codes,
                occurred_at=failure.occurred_at,
            )
        if outcome.stage is not prepared.profile.stage or outcome.participant_ref != owner.participant_ref:
            raise LifecycleCompositionError("lifecycle service outcome crossed stage or owner identity")
        if any(item.artifact_contract not in prepared.profile.output_contracts for item in outcome.output_artifacts):
            raise LifecycleCompositionError("lifecycle service widened the declared output contracts")
        started_at = None
        if outcome.state is not RunState.BLOCKED:
            started_at = outcome.occurred_at - timedelta(milliseconds=outcome.duration_ms)
        receipt = StageRunReceiptV1Alpha1(
            plan=lifecycle_exact_reference(prepared.plan),
            manifest=lifecycle_exact_reference(prepared.manifest),
            product_id=prepared.manifest.product_id,
            composition_participant_id=prepared.manifest.composition_participant_id,
            attempt=attempt,
            state=outcome.state,
            started_at=started_at,
            ended_at=outcome.occurred_at,
            actual_route=outcome.actual_route,
            usage=UsageV1Alpha1(
                items=len(outcome.output_artifacts),
                calls=0 if outcome.state is RunState.BLOCKED else 1,
                latency_ms=outcome.duration_ms,
                external_effects=0,
            ),
            actual_tool_refs=outcome.actual_tool_refs,
            authority_exercised=(
                () if outcome.state in {RunState.BLOCKED, RunState.CANCELLED} else prepared.manifest.authority
            ),
            output_artifacts=outcome.output_artifacts,
            context_states=outcome.context_states,
            issue_codes=outcome.issue_codes,
            retry_of_receipt_ref=retry_of_receipt_ref,
        )
        validate_run_receipt_against_manifest(prepared.manifest, receipt)
        handoff_contract = StageHandoffContractV1Alpha1(
            source_stage_id=prepared.profile.stage.value,
            target_stage_id=prepared.profile.next_stage_id,
            source_product_id=prepared.request.product_id,
            target_product_id=prepared.request.product_id,
            destination_kind=(
                "prepared_external_delivery_gate"
                if prepared.profile.stage is LifecycleStage.DELIVER
                else "internal_lifecycle_stage"
            ),
            accepted_contracts=prepared.profile.output_contracts,
            required_evidence_refs=tuple(item.artifact_id for item in outcome.owner_receipts),
            required_policy_refs=(prepared.profile.failure_policy_ref,),
            completion_policy_ref="completion:exact-stage-exit-v1",
            retry_policy_ref="retry:fresh-auth-and-current-use-v1",
            acknowledgment_policy_ref="ack:typed-internal-handoff-v1",
            allowed_next_stage_ids=(prepared.profile.next_stage_id,),
        )
        state = HandoffState.PREPARED
        if outcome.state in {RunState.PARTIAL, RunState.DEGRADED, RunState.ABSTAINED}:
            state = HandoffState.PARTIAL
        elif outcome.state in {RunState.FAILED, RunState.BLOCKED}:
            state = HandoffState.FAILED
        elif outcome.state is RunState.CANCELLED:
            state = HandoffState.CANCELLED
        handoff = StageHandoffReceiptV1Alpha1(
            handoff_contract=lifecycle_exact_reference(handoff_contract),
            source_plan=lifecycle_exact_reference(prepared.plan),
            source_runs=(lifecycle_exact_reference(receipt),),
            target_ref=(
                "ac5_delivery_gate:required"
                if prepared.profile.stage is LifecycleStage.DELIVER
                else f"lifecycle_stage:{prepared.profile.next_stage_id}"
            ),
            artifacts=outcome.output_artifacts,
            authority_used=(),
            policy_refs=(prepared.profile.failure_policy_ref,),
            state=state,
            external_send_occurred=False,
            omitted_refs=outcome.issue_codes,
            idempotency_key=f"handoff:{prepared.plan.composition_plan_id}:attempt:{attempt}",
            retry_of_receipt_ref=retry_of_receipt_ref,
            occurred_at=outcome.occurred_at,
        )
        return CompletedLifecycleComposition(
            request=prepared.request,
            profile=prepared.profile,
            plan=prepared.plan,
            manifest=prepared.manifest,
            run_receipt=receipt,
            service_outcome=outcome,
            handoff_contract=handoff_contract,
            handoff_receipt=handoff,
            planning_authority_receipt=lifecycle_exact_reference(
                prepared.planning_authority.resolution_receipt
            ),
            execution_authority_receipt=lifecycle_exact_reference(current.resolution_receipt),
        )


__all__ = [
    "LIFECYCLE_COMPOSITION_RECORD_SET_VERSION",
    "LIFECYCLE_SERVICE_OUTCOME_VERSION",
    "LIFECYCLE_STAGE_PROFILES",
    "LIFECYCLE_STAGE_PROFILE_VERSION",
    "LIFECYCLE_STAGE_REQUEST_VERSION",
    "PREPARED_LIFECYCLE_DELIVERY_VERSION",
    "SENTINEL_OBSERVATION_PROJECTION_VERSION",
    "BoundLifecycleExecutionOwner",
    "CompletedLifecycleComposition",
    "LifecycleCompositionError",
    "LifecycleCompositionRuntimeAuthorityBundle",
    "LifecycleCompositionRuntimeAuthorityPort",
    "LifecycleExecutionOwner",
    "LifecycleOwnerFailure",
    "LifecycleParticipantCompositionBridge",
    "LifecycleServiceOutcomeV1Alpha1",
    "LifecycleStage",
    "LifecycleStageCompatibilityProfile",
    "LifecycleStageRequestV1Alpha1",
    "PreparedLifecycleComposition",
    "PreparedLifecycleDeliveryOwner",
    "PreparedLifecycleDeliveryV1Alpha1",
    "SentinelObservationProjectionV1Alpha1",
    "TaskAuthenticationReceiptV1Alpha1",
    "UnsupportedLifecycleStage",
    "lifecycle_exact_reference",
]
