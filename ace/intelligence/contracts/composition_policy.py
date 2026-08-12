"""Provider-neutral contracts for governed composition-policy admission.

AC6 policy-change proposals are immutable evidence only.  The contracts here
describe the separate present-tense governance transaction that may make a
selection policy current.  Policy can constrain selection; it cannot grant
authority, make a participant eligible, execute work, deliver, export, choose
a model/provider, or create any external effect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.measured_composition import (
    COMPOSITION_EVALUATION_PROTOCOL_VERSION,
    COMPOSITION_MATCHED_COMPARISON_VERSION,
    COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION,
)

COMPOSITION_POLICY_ADMISSION_PLAN_VERSION = "ace.intelligence.composition-policy-admission-plan/v1alpha1"
COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION = "ace.intelligence.composition-policy-admission-request/v1alpha1"
COMPOSITION_POLICY_REVIEW_VERSION = "ace.intelligence.composition-policy-review/v1alpha1"
COMPOSITION_POLICY_REVISION_VERSION = "ace.intelligence.composition-policy-revision/v1alpha1"
COMPOSITION_POLICY_ADMISSION_RECEIPT_VERSION = "ace.intelligence.composition-policy-admission-receipt/v1alpha1"
COMPOSITION_POLICY_REJECTION_VERSION = "ace.intelligence.composition-policy-rejection/v1alpha1"
COMPOSITION_POLICY_RUNTIME_RESOLUTION_VERSION = (
    "ace.intelligence.composition-policy-runtime-resolution-receipt/v1alpha1"
)

MAX_HEADS = 64
MAX_RULES = 128


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


def _strings(values: tuple[str, ...], *, name: str, minimum: int = 0) -> tuple[str, ...]:
    if len(values) < minimum or len(values) > MAX_RULES:
        raise ValueError(f"{name} must contain between {minimum} and {MAX_RULES} values")
    normalized = tuple(sorted(_bounded(item, name=name, maximum=500) for item in values))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must contain unique values")
    return normalized


def _heads(
    values: tuple[GovernedStateHeadPreconditionV1Alpha1, ...], *, product_id: str
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    if len(values) > MAX_HEADS:
        raise ValueError(f"current_heads cannot contain more than {MAX_HEADS} values")
    keys = [(item.state_kind, item.product_id, item.state_id) for item in values]
    if len(keys) != len(set(keys)):
        raise ValueError("current_heads must name each Core state identity once")
    if any(item.product_id != product_id for item in values):
        raise ValueError("current_heads crossed product scope")
    return tuple(sorted(values, key=lambda item: (item.state_kind, item.product_id, item.state_id)))


class CompositionPolicyAction(StrEnum):
    ADMIT = "admit"
    SUPERSEDE = "supersede"
    ROLLBACK = "rollback"
    SUSPEND = "suspend"
    RECOVER = "recover"


class CompositionPolicyLifecycle(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class CompositionPolicyReviewDisposition(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class CompositionPolicyReviewerClass(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class CompositionPolicyAdmissionPlanV1Alpha1(_Contract):
    """Immutable, effect-free plan for one exact policy-head transaction."""

    contract: Literal["ace.intelligence.composition-policy-admission-plan/v1alpha1"] = (
        COMPOSITION_POLICY_ADMISSION_PLAN_VERSION
    )
    product_id: str
    policy_id: str
    scope_ref: str
    action: CompositionPolicyAction
    proposal: ExactArtifactReferenceV1Alpha1 | None = None
    protocol: ExactArtifactReferenceV1Alpha1 | None = None
    comparison: ExactArtifactReferenceV1Alpha1 | None = None
    expected_current_head: GovernedStateHeadPreconditionV1Alpha1 | None = None
    rollback_target_revision: ExactArtifactReferenceV1Alpha1 | None = None
    proposed_policy_rule_ref: str | None = None
    selection_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    selection_preferences: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    frozen_ac6_authority_lineage: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_HEADS
    )
    rationale: str = Field(min_length=1, max_length=2_000)
    created_at: datetime
    expires_at: datetime
    changes_roster: Literal[False] = False
    grants_authority: Literal[False] = False
    changes_model_or_provider: Literal[False] = False
    schedules_or_executes: Literal[False] = False
    delivers_or_exports: Literal[False] = False
    sends_external_effect: Literal[False] = False
    changes_lifecycle: Literal[False] = False
    writes_agent_memory: Literal[False] = False
    proposal_is_live_authority: Literal[False] = False
    plan_id: str | None = None
    plan_digest: str | None = None

    @field_validator("product_id", "policy_id", "scope_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("proposed_policy_rule_ref")
    @classmethod
    def validate_optional_ref(cls, value: str | None) -> str | None:
        return _bounded(value, name="proposed_policy_rule_ref") if value is not None else None

    @field_validator("selection_constraints", "selection_preferences")
    @classmethod
    def normalize_rules(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _strings(value, name=info.field_name)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=2_000)

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("plan_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="plan_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_transaction_shape(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("policy admission plan must have a positive review window")
        evidence_action = self.action in {
            CompositionPolicyAction.ADMIT,
            CompositionPolicyAction.SUPERSEDE,
            CompositionPolicyAction.ROLLBACK,
        }
        if evidence_action:
            if self.proposal is None or self.protocol is None or self.comparison is None:
                raise ValueError("admission, supersession, and rollback require exact AC6 proposal lineage")
            if self.proposal.artifact_contract != COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION:
                raise ValueError("policy admission requires an exact inert AC6 proposal")
            if self.protocol.artifact_contract != COMPOSITION_EVALUATION_PROTOCOL_VERSION:
                raise ValueError("policy admission requires the exact frozen AC6 protocol")
            if self.comparison.artifact_contract != COMPOSITION_MATCHED_COMPARISON_VERSION:
                raise ValueError("policy admission requires the exact AC6 matched comparison")
            if self.proposed_policy_rule_ref is None:
                raise ValueError("policy admission requires one exact proposed selection rule")
            if len(self.frozen_ac6_authority_lineage) < 2:
                raise ValueError("policy admission requires exact frozen AC6 authority/configuration lineage")
        elif any((self.proposal, self.protocol, self.comparison, self.proposed_policy_rule_ref)):
            raise ValueError("suspension and recovery cannot smuggle proposal or selection-rule changes")
        if self.action is CompositionPolicyAction.ADMIT:
            if self.expected_current_head is not None or self.rollback_target_revision is not None:
                raise ValueError("first admission must expect no current policy head")
        else:
            if self.expected_current_head is None:
                raise ValueError("later policy transactions require the exact expected current head")
            if (
                self.expected_current_head.product_id != self.product_id
                or self.expected_current_head.state_kind != "composition_policy"
                or self.expected_current_head.state_id != self.policy_id
            ):
                raise ValueError("expected current policy head crossed exact policy scope")
        if self.action is CompositionPolicyAction.ROLLBACK:
            if self.rollback_target_revision is None:
                raise ValueError("rollback requires an exact prior policy revision")
            if self.rollback_target_revision.artifact_contract != COMPOSITION_POLICY_REVISION_VERSION:
                raise ValueError("rollback target must be an exact immutable policy revision")
        elif self.rollback_target_revision is not None:
            raise ValueError("only rollback may target a historical revision")
        object.__setattr__(
            self,
            "frozen_ac6_authority_lineage",
            _heads(self.frozen_ac6_authority_lineage, product_id=self.product_id),
        )
        _identity(self, prefix="composition_policy_plan", id_field="plan_id", digest_field="plan_digest")
        return self


class CompositionPolicyAdmissionRequestV1Alpha1(_Contract):
    """One non-idempotent intent whose stable nonce is bound to exact material."""

    contract: Literal["ace.intelligence.composition-policy-admission-request/v1alpha1"] = (
        COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION
    )
    product_id: str
    policy_id: str
    scope_ref: str
    plan: ExactArtifactReferenceV1Alpha1
    requester_actor_ref: str
    requester_principal_ref: str
    administrator_actor_ref: str
    administrator_principal_ref: str
    approval_receipt_ref: str
    administration_grant_ref: str
    expected_current_head: GovernedStateHeadPreconditionV1Alpha1 | None = None
    current_core_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=2, max_length=MAX_HEADS)
    request_nonce: str
    requested_at: datetime
    expires_at: datetime
    historical_receipts_are_authority: Literal[False] = False
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator(
        "product_id",
        "policy_id",
        "scope_ref",
        "requester_actor_ref",
        "requester_principal_ref",
        "administrator_actor_ref",
        "administrator_principal_ref",
        "approval_receipt_ref",
        "administration_grant_ref",
        "request_nonce",
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="request_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.plan.artifact_contract != COMPOSITION_POLICY_ADMISSION_PLAN_VERSION:
            raise ValueError("policy request requires one exact immutable admission plan")
        if self.expires_at <= self.requested_at:
            raise ValueError("policy request must have a positive validity window")
        if self.expected_current_head is not None and (
            self.expected_current_head.product_id != self.product_id
            or self.expected_current_head.state_kind != "composition_policy"
            or self.expected_current_head.state_id != self.policy_id
        ):
            raise ValueError("request expected head crossed exact policy scope")
        object.__setattr__(self, "current_core_heads", _heads(self.current_core_heads, product_id=self.product_id))
        if not any(
            item.state_kind == "authority_grant" and item.state_id == self.administration_grant_ref
            for item in self.current_core_heads
        ):
            raise ValueError("policy request must bind the exact current administration-grant head")
        if not any(item.state_kind != "authority_grant" for item in self.current_core_heads):
            raise ValueError("policy request must bind at least one current configuration head")
        _identity(self, prefix="composition_policy_request", id_field="request_id", digest_field="request_digest")
        return self


class CompositionPolicyReviewV1Alpha1(_Contract):
    """Independent human/service review evidence; it never changes a head."""

    contract: Literal["ace.intelligence.composition-policy-review/v1alpha1"] = COMPOSITION_POLICY_REVIEW_VERSION
    product_id: str
    policy_id: str
    scope_ref: str
    plan: ExactArtifactReferenceV1Alpha1
    request: ExactArtifactReferenceV1Alpha1
    reviewer_actor_ref: str
    reviewer_principal_ref: str
    reviewer_class: CompositionPolicyReviewerClass
    disposition: CompositionPolicyReviewDisposition
    reasons: tuple[str, ...] = Field(min_length=1, max_length=MAX_RULES)
    reviewed_at: datetime
    applies_policy: Literal[False] = False
    grants_authority: Literal[False] = False
    review_id: str | None = None
    review_digest: str | None = None

    @field_validator("product_id", "policy_id", "scope_ref", "reviewer_actor_ref", "reviewer_principal_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("reasons")
    @classmethod
    def normalize_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _strings(value, name="reasons", minimum=1)

    @field_validator("reviewed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="reviewed_at")

    @field_validator("review_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="review_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_refs_and_identity(self) -> Self:
        if self.plan.artifact_contract != COMPOSITION_POLICY_ADMISSION_PLAN_VERSION:
            raise ValueError("review requires one exact admission plan")
        if self.request.artifact_contract != COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION:
            raise ValueError("review requires one exact admission request")
        _identity(self, prefix="composition_policy_review", id_field="review_id", digest_field="review_digest")
        return self


class CompositionPolicyRevisionV1Alpha1(_Contract):
    """Immutable policy configuration revision projected from an approved transaction."""

    contract: Literal["ace.intelligence.composition-policy-revision/v1alpha1"] = COMPOSITION_POLICY_REVISION_VERSION
    product_id: str
    policy_id: str
    scope_ref: str
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    action: CompositionPolicyAction
    lifecycle: CompositionPolicyLifecycle
    proposal: ExactArtifactReferenceV1Alpha1 | None = None
    protocol: ExactArtifactReferenceV1Alpha1 | None = None
    comparison: ExactArtifactReferenceV1Alpha1 | None = None
    rollback_target_revision: ExactArtifactReferenceV1Alpha1 | None = None
    policy_rule_ref: str | None = None
    selection_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    selection_preferences: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    plan: ExactArtifactReferenceV1Alpha1
    request: ExactArtifactReferenceV1Alpha1
    review: ExactArtifactReferenceV1Alpha1
    authority_and_configuration_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        min_length=2, max_length=MAX_HEADS
    )
    administrator_actor_ref: str
    administrator_principal_ref: str
    admitted_at: datetime
    policy_never_grants_authority: Literal[True] = True
    runtime_revalidation_required: Literal[True] = True
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator("product_id", "policy_id", "scope_ref", "administrator_actor_ref", "administrator_principal_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("prior_revision_id", "policy_rule_ref")
    @classmethod
    def validate_optional_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("selection_constraints", "selection_preferences")
    @classmethod
    def normalize_rules(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _strings(value, name=info.field_name)

    @field_validator("admitted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @field_validator("revision_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="revision_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_shape_and_identity(self) -> Self:
        if self.sequence == 1 and self.prior_revision_id is not None:
            raise ValueError("first policy revision cannot name a prior revision")
        if self.sequence > 1 and self.prior_revision_id is None:
            raise ValueError("later policy revisions require exact prior lineage")
        if (
            self.action is CompositionPolicyAction.SUSPEND
            and self.lifecycle is not CompositionPolicyLifecycle.SUSPENDED
        ):
            raise ValueError("suspension must produce a suspended policy head")
        if (
            self.action is not CompositionPolicyAction.SUSPEND
            and self.lifecycle is not CompositionPolicyLifecycle.ACTIVE
        ):
            raise ValueError("admission, supersession, rollback, and recovery must produce an active policy head")
        if self.action in {
            CompositionPolicyAction.ADMIT,
            CompositionPolicyAction.SUPERSEDE,
            CompositionPolicyAction.ROLLBACK,
        }:
            if (
                self.proposal is None
                or self.protocol is None
                or self.comparison is None
                or self.policy_rule_ref is None
            ):
                raise ValueError("policy revision lacks exact AC6 proposal and selection-rule lineage")
        if self.action is CompositionPolicyAction.ROLLBACK and self.rollback_target_revision is None:
            raise ValueError("rollback revision lacks its exact historical target")
        if self.plan.artifact_contract != COMPOSITION_POLICY_ADMISSION_PLAN_VERSION:
            raise ValueError("policy revision requires exact plan lineage")
        if self.request.artifact_contract != COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION:
            raise ValueError("policy revision requires exact request lineage")
        if self.review.artifact_contract != COMPOSITION_POLICY_REVIEW_VERSION:
            raise ValueError("policy revision requires exact review lineage")
        object.__setattr__(
            self,
            "authority_and_configuration_heads",
            _heads(self.authority_and_configuration_heads, product_id=self.product_id),
        )
        _identity(self, prefix="composition_policy_revision", id_field="revision_id", digest_field="revision_digest")
        return self


class CompositionPolicyAdmissionReceiptV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.composition-policy-admission-receipt/v1alpha1"] = (
        COMPOSITION_POLICY_ADMISSION_RECEIPT_VERSION
    )
    product_id: str
    policy_id: str
    scope_ref: str
    action: CompositionPolicyAction
    revision: ExactArtifactReferenceV1Alpha1
    current_policy_head: GovernedStateHeadPreconditionV1Alpha1
    core_commit_receipt_id: str
    core_commit_receipt_digest: str
    review: ExactArtifactReferenceV1Alpha1
    admitted_at: datetime
    historical_receipt_is_live_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "policy_id", "scope_ref", "core_commit_receipt_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("core_commit_receipt_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("admitted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.revision.artifact_contract != COMPOSITION_POLICY_REVISION_VERSION:
            raise ValueError("admission receipt requires exact policy revision")
        if self.review.artifact_contract != COMPOSITION_POLICY_REVIEW_VERSION:
            raise ValueError("admission receipt requires exact independent review")
        if (
            self.current_policy_head.product_id != self.product_id
            or self.current_policy_head.state_kind != "composition_policy"
            or self.current_policy_head.state_id != self.policy_id
            or self.current_policy_head.revision_id != self.revision.artifact_id
        ):
            raise ValueError("admission receipt crossed the exact current policy head")
        _identity(self, prefix="composition_policy_admission", id_field="receipt_id", digest_field="receipt_digest")
        return self


class CompositionPolicyRejectionV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.composition-policy-rejection/v1alpha1"] = COMPOSITION_POLICY_REJECTION_VERSION
    product_id: str
    policy_id: str
    scope_ref: str
    plan: ExactArtifactReferenceV1Alpha1
    request: ExactArtifactReferenceV1Alpha1
    review: ExactArtifactReferenceV1Alpha1
    reasons: tuple[str, ...] = Field(min_length=1, max_length=MAX_RULES)
    rejected_at: datetime
    creates_policy_head: Literal[False] = False
    rejection_id: str | None = None
    rejection_digest: str | None = None

    @field_validator("product_id", "policy_id", "scope_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("reasons")
    @classmethod
    def normalize_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _strings(value, name="reasons", minimum=1)

    @field_validator("rejected_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="rejected_at")

    @field_validator("rejection_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="rejection_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.plan.artifact_contract != COMPOSITION_POLICY_ADMISSION_PLAN_VERSION:
            raise ValueError("rejection requires exact admission-plan lineage")
        if self.request.artifact_contract != COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION:
            raise ValueError("rejection requires exact admission-request lineage")
        if self.review.artifact_contract != COMPOSITION_POLICY_REVIEW_VERSION:
            raise ValueError("rejection requires exact review lineage")
        _identity(self, prefix="composition_policy_rejection", id_field="rejection_id", digest_field="rejection_digest")
        return self


class CompositionPolicyRuntimeResolutionReceiptV1Alpha1(_Contract):
    """Bounded one-use projection of a current active policy, never authority."""

    contract: Literal["ace.intelligence.composition-policy-runtime-resolution-receipt/v1alpha1"] = (
        COMPOSITION_POLICY_RUNTIME_RESOLUTION_VERSION
    )
    product_id: str
    policy_id: str
    scope_ref: str
    actor_ref: str
    principal_ref: str
    use_subject_ref: str
    use_subject_digest: str
    current_policy_head: GovernedStateHeadPreconditionV1Alpha1
    policy_revision: ExactArtifactReferenceV1Alpha1
    current_authority_and_configuration_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        min_length=2, max_length=MAX_HEADS
    )
    selection_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    selection_preferences: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_RULES)
    request_nonce: str
    resolved_at: datetime
    expires_at: datetime
    reusable: Literal[False] = False
    grants_authority: Literal[False] = False
    makes_participant_eligible: Literal[False] = False
    execution_authority_revalidation_required: Literal[True] = True
    participant_heads_revalidation_required: Literal[True] = True
    task_scope_and_budget_revalidation_required: Literal[True] = True
    delivery_export_effect_revalidation_required: Literal[True] = True
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id", "policy_id", "scope_ref", "actor_ref", "principal_ref", "use_subject_ref", "request_nonce"
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("use_subject_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("selection_constraints", "selection_preferences")
    @classmethod
    def normalize_rules(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _strings(value, name=info.field_name)

    @field_validator("resolved_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if self.expires_at <= self.resolved_at:
            raise ValueError("runtime policy receipt must have a positive bounded window")
        if self.policy_revision.artifact_contract != COMPOSITION_POLICY_REVISION_VERSION:
            raise ValueError("runtime resolution requires exact policy revision")
        if (
            self.current_policy_head.product_id != self.product_id
            or self.current_policy_head.state_kind != "composition_policy"
            or self.current_policy_head.state_id != self.policy_id
            or self.current_policy_head.revision_id != self.policy_revision.artifact_id
        ):
            raise ValueError("runtime resolution crossed exact current policy scope")
        object.__setattr__(
            self,
            "current_authority_and_configuration_heads",
            _heads(self.current_authority_and_configuration_heads, product_id=self.product_id),
        )
        if not any(item.state_kind == "authority_grant" for item in self.current_authority_and_configuration_heads):
            raise ValueError("runtime resolution requires at least one exact current authority head")
        if not any(item.state_kind != "authority_grant" for item in self.current_authority_and_configuration_heads):
            raise ValueError("runtime resolution requires at least one exact current configuration head")
        _identity(self, prefix="composition_policy_runtime", id_field="receipt_id", digest_field="receipt_digest")
        return self


def composition_policy_reference(value: object) -> ExactArtifactReferenceV1Alpha1:
    contract = str(getattr(value, "contract"))
    for id_field, digest_field in (
        ("plan_id", "plan_digest"),
        ("request_id", "request_digest"),
        ("review_id", "review_digest"),
        ("revision_id", "revision_digest"),
        ("receipt_id", "receipt_digest"),
        ("rejection_id", "rejection_digest"),
    ):
        artifact_id = getattr(value, id_field, None)
        artifact_digest = getattr(value, digest_field, None)
        if artifact_id is not None and artifact_digest is not None:
            return ExactArtifactReferenceV1Alpha1(
                artifact_id=str(artifact_id), artifact_digest=str(artifact_digest), artifact_contract=contract
            )
    raise ValueError("value does not expose composition-policy artifact coordinates")


__all__ = [
    "COMPOSITION_POLICY_ADMISSION_PLAN_VERSION",
    "COMPOSITION_POLICY_ADMISSION_RECEIPT_VERSION",
    "COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION",
    "COMPOSITION_POLICY_REJECTION_VERSION",
    "COMPOSITION_POLICY_REVIEW_VERSION",
    "COMPOSITION_POLICY_REVISION_VERSION",
    "COMPOSITION_POLICY_RUNTIME_RESOLUTION_VERSION",
    "CompositionPolicyAction",
    "CompositionPolicyAdmissionPlanV1Alpha1",
    "CompositionPolicyAdmissionReceiptV1Alpha1",
    "CompositionPolicyAdmissionRequestV1Alpha1",
    "CompositionPolicyLifecycle",
    "CompositionPolicyRejectionV1Alpha1",
    "CompositionPolicyReviewDisposition",
    "CompositionPolicyReviewV1Alpha1",
    "CompositionPolicyReviewerClass",
    "CompositionPolicyRevisionV1Alpha1",
    "CompositionPolicyRuntimeResolutionReceiptV1Alpha1",
    "composition_policy_reference",
]
