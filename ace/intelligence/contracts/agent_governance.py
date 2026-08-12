"""Provider-neutral semantic contracts for governed agent onboarding.

These contracts keep stable governance identity, immutable registration
evidence, definition/binding content, requested grants, runtime health, and
current lifecycle state separate.  None of them is bearer authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import (
    AgentPrincipalV1Alpha1,
    AuthorityClass,
    CompositionBudgetV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
)
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.state import ResolvedAuthorityGrantV1
from ace.intelligence.contracts.agent_composition import (
    GovernedAgentDefinitionRevisionV1Alpha1,
    LifecycleStage,
    OrchestrationPattern,
    StageRoleBindingRevisionV1Alpha1,
)

AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION = "ace.intelligence.agent-principal-lifecycle-revision/v1alpha1"
AGENT_DEFINITION_PROPOSAL_VERSION = "ace.intelligence.agent-definition-proposal/v1alpha1"
AGENT_BINDING_PROPOSAL_VERSION = "ace.intelligence.agent-binding-proposal/v1alpha1"
AGENT_GOVERNANCE_DIFF_VERSION = "ace.intelligence.agent-governance-diff/v1alpha1"
AGENT_REVIEW_DISPOSITION_VERSION = "ace.intelligence.agent-review-disposition/v1alpha1"
AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION = "ace.intelligence.agent-definition-lifecycle-revision/v1alpha1"
AGENT_BINDING_LIFECYCLE_REVISION_VERSION = "ace.intelligence.agent-binding-lifecycle-revision/v1alpha1"
AGENT_GRANT_REQUEST_VERSION = "ace.intelligence.agent-grant-request/v1alpha1"
AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION = "ace.intelligence.agent-grant-request-lifecycle-revision/v1alpha1"
AGENT_RUNTIME_HEALTH_REVISION_VERSION = "ace.intelligence.agent-runtime-health-revision/v1alpha1"
AGENT_COMPATIBILITY_RECEIPT_VERSION = "ace.intelligence.agent-compatibility-receipt/v1alpha1"
AGENT_CONFORMANCE_RECEIPT_VERSION = "ace.intelligence.agent-conformance-receipt/v1alpha1"
AGENT_DRY_RUN_RECEIPT_VERSION = "ace.intelligence.agent-dry-run-receipt/v1alpha1"
AGENT_ACTIVATION_RECEIPT_VERSION = "ace.intelligence.agent-activation-receipt/v1alpha1"
AGENT_COMPATIBILITY_REPLACEMENT_RECEIPT_VERSION = "ace.intelligence.agent-compatibility-replacement-receipt/v1alpha1"

MAX_REFERENCES = 256


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


def _sorted_unique(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    if len(values) > MAX_REFERENCES:
        raise ValueError(f"{name} exceed the {MAX_REFERENCES}-item bound")
    for value in values:
        _bounded(value, name=name)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values))


def _derive(
    instance: _Contract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
    exclude: set[str] | None = None,
) -> None:
    excluded = {id_field, digest_field}.union(exclude or set())
    material = instance.model_dump(mode="json", exclude=excluded)
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact governance material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact governance material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


def exact_registration_reference(principal: AgentPrincipalV1Alpha1) -> ExactArtifactReferenceV1Alpha1:
    """Return exact immutable coordinates for one frozen AC1 registration snapshot."""

    validated = AgentPrincipalV1Alpha1.model_validate(principal.model_dump(mode="python"))
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=str(validated.principal_id),
        artifact_digest=str(validated.principal_digest),
        artifact_contract=validated.contract,
    )


class PrincipalLifecycleState(StrEnum):
    SUSPENDED = "suspended"
    ACTIVE = "active"
    REVOKED = "revoked"
    RETIRED = "retired"


class GovernedContentState(StrEnum):
    APPROVED = "approved"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class GrantRequestState(StrEnum):
    REQUESTED = "requested"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"


class RuntimeHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    QUARANTINED = "quarantined"


class EvidenceDisposition(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class ReviewDisposition(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class ReviewActorClass(StrEnum):
    HUMAN = "human"
    CORE_POLICY = "core_policy"


class ProposalKind(StrEnum):
    DEFINITION = "definition"
    BINDING = "binding"


class AgentPrincipalLifecycleRevisionV1Alpha1(_Contract):
    """Current lifecycle state bound to one exact immutable registration snapshot."""

    contract: Literal["ace.intelligence.agent-principal-lifecycle-revision/v1alpha1"] = (
        AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    registration_implementation_ref: str
    registration_protocol_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    state: PrincipalLifecycleState
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    approval_receipt_ref: str
    actor_ref: str
    occurred_at: datetime
    lifecycle_revision_id: str | None = None
    lifecycle_revision_digest: str | None = None

    @field_validator("approval_receipt_ref", "actor_ref", "prior_revision_id", "registration_implementation_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @field_validator("registration_protocol_refs")
    @classmethod
    def normalize_protocols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="registration_protocol_refs")

    @model_validator(mode="after")
    def validate_lineage_and_identity(self) -> Self:
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("principal lifecycle lineage must exactly match its sequence")
        if self.sequence == 1 and self.state is not PrincipalLifecycleState.SUSPENDED:
            raise ValueError("onboarding begins suspended; registration does not activate a principal")
        _derive(
            self,
            prefix="agent_principal_lifecycle_revision",
            id_field="lifecycle_revision_id",
            digest_field="lifecycle_revision_digest",
        )
        return self


class AgentDefinitionDraftV1Alpha1(_Contract):
    """Author-controlled definition material before approval-owned fields exist."""

    principal_id: str
    purpose: str = Field(max_length=2_000)
    eligible_stages: tuple[LifecycleStage, ...] = Field(min_length=1, max_length=32)
    accepted_input_contracts: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    produced_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    eligible_cognition_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    required_tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    optional_tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    source_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    destination_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    maximum_authority: tuple[AuthorityClass, ...] = Field(default_factory=tuple)
    budget_ceiling: CompositionBudgetV1Alpha1
    escalation_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    failure_policy_ref: str
    implementation_protocol_ref: str

    @field_validator("principal_id", "failure_policy_ref", "implementation_protocol_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator(
        "accepted_input_contracts",
        "produced_output_contracts",
        "eligible_cognition_refs",
        "required_tool_refs",
        "optional_tool_refs",
        "source_policy_refs",
        "destination_policy_refs",
        "escalation_policy_refs",
    )
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_narrow_material(self) -> Self:
        if set(self.required_tool_refs).intersection(self.optional_tool_refs):
            raise ValueError("a tool cannot be both required and optional")
        if len(self.eligible_stages) != len(set(self.eligible_stages)):
            raise ValueError("eligible stages must be unique")
        if len(self.maximum_authority) != len(set(self.maximum_authority)):
            raise ValueError("maximum authority must be unique")
        object.__setattr__(self, "eligible_stages", tuple(sorted(self.eligible_stages, key=lambda item: item.value)))
        object.__setattr__(
            self,
            "maximum_authority",
            tuple(sorted(self.maximum_authority, key=lambda item: item.value)),
        )
        return self


class StageRoleBindingDraftV1Alpha1(_Contract):
    definition_revision: ExactArtifactReferenceV1Alpha1
    stage: LifecycleStage
    role_label: str
    objective_class: str
    required_input_contracts: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    expected_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    exit_criteria_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    instruction_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    orchestration_patterns: tuple[OrchestrationPattern, ...] = Field(min_length=1, max_length=8)
    independence_policy_ref: str
    gate_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    source_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    destination_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    authority_ceiling: tuple[AuthorityClass, ...] = Field(default_factory=tuple)
    budget_ceiling: CompositionBudgetV1Alpha1
    escalation_policy_ref: str

    @field_validator("role_label", "objective_class", "independence_policy_ref", "escalation_policy_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator(
        "required_input_contracts",
        "expected_output_contracts",
        "exit_criteria_refs",
        "instruction_policy_refs",
        "gate_refs",
        "tool_refs",
        "source_policy_refs",
        "destination_policy_refs",
    )
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @model_validator(mode="after")
    def normalize_enums(self) -> Self:
        if len(self.orchestration_patterns) != len(set(self.orchestration_patterns)):
            raise ValueError("orchestration patterns must be unique")
        if len(self.authority_ceiling) != len(set(self.authority_ceiling)):
            raise ValueError("authority ceiling must be unique")
        object.__setattr__(
            self,
            "orchestration_patterns",
            tuple(sorted(self.orchestration_patterns, key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "authority_ceiling",
            tuple(sorted(self.authority_ceiling, key=lambda item: item.value)),
        )
        return self


class AgentDefinitionProposalV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-definition-proposal/v1alpha1"] = AGENT_DEFINITION_PROPOSAL_VERSION
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    draft: AgentDefinitionDraftV1Alpha1
    base_definition: ExactArtifactReferenceV1Alpha1 | None = None
    sources: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    requested_by: str
    rationale: str = Field(min_length=1, max_length=10_000)
    proposed_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("requested_by")
    @classmethod
    def validate_actor(cls, value: str) -> str:
        return _bounded(value, name="requested_by")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=10_000)

    @field_validator("proposed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.draft.principal_id != self.registration_snapshot.artifact_id:
            raise ValueError("definition proposal must target the exact registration snapshot")
        _derive(
            self,
            prefix="agent_definition_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


class AgentBindingProposalV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-binding-proposal/v1alpha1"] = AGENT_BINDING_PROPOSAL_VERSION
    governance: AgentGovernanceCoordinateV1Alpha1
    binding_key: str
    draft: StageRoleBindingDraftV1Alpha1
    base_binding: ExactArtifactReferenceV1Alpha1 | None = None
    requested_by: str
    rationale: str = Field(min_length=1, max_length=10_000)
    proposed_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("binding_key", "requested_by")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=10_000)

    @field_validator("proposed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(self, prefix="agent_binding_proposal", id_field="proposal_id", digest_field="proposal_digest")
        return self


class AgentGovernanceDiffEntryV1Alpha1(_Contract):
    path: str
    operation: Literal["add", "remove", "replace"]
    before_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    after_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _bounded(value, name="path", maximum=1_000)


class AgentGovernanceDiffV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-governance-diff/v1alpha1"] = AGENT_GOVERNANCE_DIFF_VERSION
    proposal_kind: ProposalKind
    proposal_id: str
    proposal_digest: str
    base_revision_id: str | None = None
    base_digest: str | None = None
    draft_digest: str
    changes: tuple[AgentGovernanceDiffEntryV1Alpha1, ...] = Field(max_length=MAX_REFERENCES)
    diff_id: str | None = None
    diff_digest: str | None = None

    @field_validator("proposal_id", "base_revision_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("proposal_digest", "base_digest", "draft_digest")
    @classmethod
    def validate_digest(cls, value: str | None, info) -> str | None:
        if value is not None and (len(value) != 71 or not value.startswith("sha256:")):
            raise ValueError(f"{info.field_name} must use sha256:<64-hex> syntax")
        return value

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if (self.base_revision_id is None) != (self.base_digest is None):
            raise ValueError("diff base identity and digest must be supplied together")
        _derive(self, prefix="agent_governance_diff", id_field="diff_id", digest_field="diff_digest")
        return self


class AgentReviewDispositionV1Alpha1(_Contract):
    """Exact human/Core disposition; result fields do not define receipt identity."""

    contract: Literal["ace.intelligence.agent-review-disposition/v1alpha1"] = AGENT_REVIEW_DISPOSITION_VERSION
    review_request_id: str
    proposal_kind: ProposalKind
    proposal_id: str
    proposal_digest: str
    actor_ref: str
    actor_class: ReviewActorClass
    disposition: ReviewDisposition
    rationale: str = Field(min_length=1, max_length=10_000)
    expected_head_revision_id: str | None = None
    reviewed_at: datetime
    result_revision_id: str | None = None
    result_revision_digest: str | None = None
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "review_request_id",
        "proposal_id",
        "actor_ref",
        "expected_head_revision_id",
        "result_revision_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=10_000)

    @field_validator("reviewed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="reviewed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if (self.result_revision_id is None) != (self.result_revision_digest is None):
            raise ValueError("review result identity and digest must be supplied together")
        if self.disposition is not ReviewDisposition.APPROVE and self.result_revision_id is not None:
            raise ValueError("only approval can identify a projected result revision")
        _derive(
            self,
            prefix="agent_review_disposition",
            id_field="receipt_id",
            digest_field="receipt_digest",
            exclude={"result_revision_id", "result_revision_digest"},
        )
        return self


class AgentDefinitionLifecycleRevisionV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-definition-lifecycle-revision/v1alpha1"] = (
        AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    definition: GovernedAgentDefinitionRevisionV1Alpha1
    state: GovernedContentState
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    disposition_receipt_ref: str
    approval_receipt_ref: str
    actor_ref: str
    occurred_at: datetime
    lifecycle_revision_id: str | None = None
    lifecycle_revision_digest: str | None = None

    @field_validator("prior_revision_id", "disposition_receipt_ref", "approval_receipt_ref", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.definition.principal_id != self.registration_snapshot.artifact_id:
            raise ValueError("definition lifecycle must bind the current registration snapshot")
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("definition lifecycle lineage must exactly match its sequence")
        _derive(
            self,
            prefix="agent_definition_lifecycle_revision",
            id_field="lifecycle_revision_id",
            digest_field="lifecycle_revision_digest",
        )
        return self


class AgentBindingLifecycleRevisionV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-binding-lifecycle-revision/v1alpha1"] = (
        AGENT_BINDING_LIFECYCLE_REVISION_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    binding_key: str
    binding: StageRoleBindingRevisionV1Alpha1
    state: GovernedContentState
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    disposition_receipt_ref: str
    approval_receipt_ref: str
    actor_ref: str
    occurred_at: datetime
    lifecycle_revision_id: str | None = None
    lifecycle_revision_digest: str | None = None

    @field_validator(
        "binding_key",
        "prior_revision_id",
        "disposition_receipt_ref",
        "approval_receipt_ref",
        "actor_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("binding lifecycle lineage must exactly match its sequence")
        _derive(
            self,
            prefix="agent_binding_lifecycle_revision",
            id_field="lifecycle_revision_id",
            digest_field="lifecycle_revision_digest",
        )
        return self


class AgentGrantRequestV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-grant-request/v1alpha1"] = AGENT_GRANT_REQUEST_VERSION
    authority_class: AuthorityClass
    requested_grant_ref: str
    scope_ref: str
    policy_ref: str
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("requested_grant_ref", "scope_ref", "policy_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(self, prefix="agent_grant_request", id_field="request_id", digest_field="request_digest")
        return self


class AgentGrantRequestLifecycleRevisionV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-grant-request-lifecycle-revision/v1alpha1"] = (
        AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    requests: tuple[AgentGrantRequestV1Alpha1, ...] = Field(max_length=MAX_REFERENCES)
    state: GrantRequestState
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    approval_receipt_ref: str
    actor_ref: str
    occurred_at: datetime
    lifecycle_revision_id: str | None = None
    lifecycle_revision_digest: str | None = None

    @field_validator("prior_revision_id", "approval_receipt_ref", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("grant-request lifecycle lineage must exactly match its sequence")
        ids = [item.request_id for item in self.requests]
        if len(ids) != len(set(ids)):
            raise ValueError("grant requests must be unique")
        object.__setattr__(self, "requests", tuple(sorted(self.requests, key=lambda item: str(item.request_id))))
        _derive(
            self,
            prefix="agent_grant_request_lifecycle_revision",
            id_field="lifecycle_revision_id",
            digest_field="lifecycle_revision_digest",
        )
        return self

    @property
    def grants_authority(self) -> Literal[False]:
        return False


class AgentRuntimeHealthRevisionV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.agent-runtime-health-revision/v1alpha1"] = AGENT_RUNTIME_HEALTH_REVISION_VERSION
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    state: RuntimeHealthState
    implementation_ref: str
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    approval_receipt_ref: str
    actor_ref: str
    observed_at: datetime
    health_revision_id: str | None = None
    health_revision_digest: str | None = None

    @field_validator("implementation_ref", "prior_revision_id", "approval_receipt_ref", "actor_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="evidence_refs")

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="observed_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if (self.sequence == 1) != (self.prior_revision_id is None):
            raise ValueError("runtime-health lineage must exactly match its sequence")
        _derive(
            self,
            prefix="agent_runtime_health_revision",
            id_field="health_revision_id",
            digest_field="health_revision_digest",
        )
        return self

    @property
    def grants_authority(self) -> Literal[False]:
        return False


class _NoEffectEvidence(_Contract):
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    disposition: EvidenceDisposition
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    checked_at: datetime
    no_effect: Literal[True] = True

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="evidence_refs")

    @field_validator("checked_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="checked_at")


class AgentCompatibilityReceiptV1Alpha1(_NoEffectEvidence):
    contract: Literal["ace.intelligence.agent-compatibility-receipt/v1alpha1"] = AGENT_COMPATIBILITY_RECEIPT_VERSION
    required_protocol_ref: str
    supported_protocol_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("required_protocol_ref")
    @classmethod
    def validate_required(cls, value: str) -> str:
        return _bounded(value, name="required_protocol_ref")

    @field_validator("supported_protocol_refs")
    @classmethod
    def normalize_protocols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="supported_protocol_refs")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        compatible = self.required_protocol_ref in self.supported_protocol_refs
        if compatible != (self.disposition is EvidenceDisposition.PASSED):
            raise ValueError("compatibility disposition must match exact protocol support")
        _derive(self, prefix="agent_compatibility_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class AgentConformanceReceiptV1Alpha1(_NoEffectEvidence):
    contract: Literal["ace.intelligence.agent-conformance-receipt/v1alpha1"] = AGENT_CONFORMANCE_RECEIPT_VERSION
    suite_ref: str
    case_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    definition: ExactArtifactReferenceV1Alpha1
    binding: ExactArtifactReferenceV1Alpha1
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("suite_ref")
    @classmethod
    def validate_suite(cls, value: str) -> str:
        return _bounded(value, name="suite_ref")

    @field_validator("case_refs")
    @classmethod
    def normalize_cases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="case_refs")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(self, prefix="agent_conformance_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class AgentDryRunReceiptV1Alpha1(_NoEffectEvidence):
    contract: Literal["ace.intelligence.agent-dry-run-receipt/v1alpha1"] = AGENT_DRY_RUN_RECEIPT_VERSION
    definition: ExactArtifactReferenceV1Alpha1
    binding: ExactArtifactReferenceV1Alpha1
    attempted_tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    attempted_authority: tuple[AuthorityClass, ...] = Field(default_factory=tuple)
    external_effect_count: Literal[0] = 0
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("attempted_tool_refs")
    @classmethod
    def normalize_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="attempted_tool_refs")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.attempted_tool_refs or self.attempted_authority:
            raise ValueError("no-effect dry run cannot exercise tools or authority")
        _derive(self, prefix="agent_dry_run_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class AgentActivationReceiptV1Alpha1(_Contract):
    """No-effect eligibility receipt over exact current heads and admitted grants."""

    contract: Literal["ace.intelligence.agent-activation-receipt/v1alpha1"] = AGENT_ACTIVATION_RECEIPT_VERSION
    governance: AgentGovernanceCoordinateV1Alpha1
    principal_lifecycle_revision_id: str
    definition_lifecycle_revision_id: str
    binding_lifecycle_revision_id: str
    grant_request_lifecycle_revision_id: str
    runtime_health_revision_id: str
    compatibility_receipt_id: str
    conformance_receipt_id: str
    dry_run_receipt_id: str
    lifecycle_authority: ResolvedAuthorityGrantV1
    resolved_grants: tuple[ResolvedAuthorityGrantV1, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    actor_ref: str
    activated_at: datetime
    no_effect: Literal[True] = True
    reusable_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "principal_lifecycle_revision_id",
        "definition_lifecycle_revision_id",
        "binding_lifecycle_revision_id",
        "grant_request_lifecycle_revision_id",
        "runtime_health_revision_id",
        "compatibility_receipt_id",
        "conformance_receipt_id",
        "dry_run_receipt_id",
        "actor_ref",
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("resolved_grants")
    @classmethod
    def normalize_grants(cls, value: tuple[ResolvedAuthorityGrantV1, ...]) -> tuple[ResolvedAuthorityGrantV1, ...]:
        refs = [item.grant_ref for item in value]
        if len(refs) != len(set(refs)):
            raise ValueError("resolved grants must use unique grant references")
        return tuple(sorted(value, key=lambda item: item.grant_ref))

    @field_validator("activated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="activated_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(self, prefix="agent_activation_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class AgentCompatibilityReplacementReceiptV1Alpha1(_Contract):
    """No-effect replacement of one opaque compatibility participant reference.

    The receipt preserves the historical reference and points at exact eligible
    AC4 material.  It is not a migration, plan rewrite, grant, or runtime use.
    """

    contract: Literal["ace.intelligence.agent-compatibility-replacement-receipt/v1alpha1"] = (
        AGENT_COMPATIBILITY_REPLACEMENT_RECEIPT_VERSION
    )
    compatibility_participant: ExactArtifactReferenceV1Alpha1
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    definition: ExactArtifactReferenceV1Alpha1
    binding: ExactArtifactReferenceV1Alpha1
    activation_receipt: ExactArtifactReferenceV1Alpha1
    replaced_at: datetime
    no_effect: Literal[True] = True
    rewrites_history: Literal[False] = False
    carries_authority_forward: Literal[False] = False
    reusable_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("replaced_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="replaced_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(
            self,
            prefix="agent_compatibility_replacement_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


def project_approved_definition(
    proposal: AgentDefinitionProposalV1Alpha1,
    disposition: AgentReviewDispositionV1Alpha1,
    *,
    lifecycle_ref: str,
    prior_revision_ref: str | None,
) -> GovernedAgentDefinitionRevisionV1Alpha1:
    """Project one approved proposal without circular receipt identity."""

    if disposition.proposal_kind is not ProposalKind.DEFINITION:
        raise ValueError("definition projection requires a definition disposition")
    if disposition.disposition is not ReviewDisposition.APPROVE:
        raise ValueError("definition projection requires approval")
    if (disposition.proposal_id, disposition.proposal_digest) != (
        proposal.proposal_id,
        proposal.proposal_digest,
    ):
        raise ValueError("definition disposition does not bind the exact proposal")
    return GovernedAgentDefinitionRevisionV1Alpha1(
        **proposal.draft.model_dump(mode="python"),
        approval_receipt_ref=str(disposition.receipt_id),
        lifecycle_ref=_bounded(lifecycle_ref, name="lifecycle_ref"),
        prior_revision_ref=prior_revision_ref,
    )


def project_approved_binding(
    proposal: AgentBindingProposalV1Alpha1,
    disposition: AgentReviewDispositionV1Alpha1,
    *,
    lifecycle_ref: str,
    prior_binding_ref: str | None,
) -> StageRoleBindingRevisionV1Alpha1:
    if disposition.proposal_kind is not ProposalKind.BINDING:
        raise ValueError("binding projection requires a binding disposition")
    if disposition.disposition is not ReviewDisposition.APPROVE:
        raise ValueError("binding projection requires approval")
    if (disposition.proposal_id, disposition.proposal_digest) != (
        proposal.proposal_id,
        proposal.proposal_digest,
    ):
        raise ValueError("binding disposition does not bind the exact proposal")
    return StageRoleBindingRevisionV1Alpha1(
        **proposal.draft.model_dump(mode="python"),
        lifecycle_ref=_bounded(lifecycle_ref, name="lifecycle_ref"),
        prior_binding_ref=prior_binding_ref,
    )


def build_governance_diff(
    *,
    proposal_kind: ProposalKind,
    proposal_id: str,
    proposal_digest: str,
    draft: dict[str, Any],
    base: dict[str, Any] | None,
    base_revision_id: str | None,
    base_digest: str | None,
) -> AgentGovernanceDiffV1Alpha1:
    """Build a bounded deterministic top-level semantic diff."""

    before = base or {}
    changes: list[AgentGovernanceDiffEntryV1Alpha1] = []
    for key in sorted(set(before).union(draft)):
        if key not in before:
            operation = "add"
        elif key not in draft:
            operation = "remove"
        elif before[key] != draft[key]:
            operation = "replace"
        else:
            continue
        changes.append(
            AgentGovernanceDiffEntryV1Alpha1(
                path=f"$.{key}",
                operation=operation,
                before_hash=f"sha256:{canonical_hash(before[key])}" if key in before else None,
                after_hash=f"sha256:{canonical_hash(draft[key])}" if key in draft else None,
            )
        )
    return AgentGovernanceDiffV1Alpha1(
        proposal_kind=proposal_kind,
        proposal_id=proposal_id,
        proposal_digest=proposal_digest,
        base_revision_id=base_revision_id,
        base_digest=base_digest,
        draft_digest=f"sha256:{canonical_hash(draft)}",
        changes=tuple(changes),
    )


__all__ = [name for name in globals() if name.startswith("AGENT_") or name.startswith("Agent")]
__all__ += [
    "EvidenceDisposition",
    "GovernedContentState",
    "GrantRequestState",
    "PrincipalLifecycleState",
    "ProposalKind",
    "ReviewActorClass",
    "ReviewDisposition",
    "RuntimeHealthState",
    "StageRoleBindingDraftV1Alpha1",
    "build_governance_diff",
    "exact_registration_reference",
    "project_approved_binding",
    "project_approved_definition",
]
