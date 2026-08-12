"""Semantic contracts for provider-neutral lifecycle composition.

Intelligence owns stage meaning, definition and role policy, candidate/roster
semantics, instruction contributions, and semantic validation.  Core owns the
exact task-time identities and authority coordinates consumed here.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import (
    AuthorityClass,
    CompositionBudgetV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    ParticipantKind,
)
from ace.core.contracts import FrozenContract, canonical_hash

AGENT_DEFINITION_REVISION_VERSION = "ace.intelligence.governed-agent-definition-revision/v1alpha1"
STAGE_ROLE_BINDING_REVISION_VERSION = "ace.intelligence.stage-role-binding-revision/v1alpha1"
COMPOSITION_REQUIREMENT_VERSION = "ace.intelligence.composition-requirement/v1alpha1"
COMPOSITION_CANDIDATE_VERSION = "ace.intelligence.composition-candidate/v1alpha1"
ROSTER_SELECTION_RECEIPT_VERSION = "ace.intelligence.roster-selection-receipt/v1alpha1"
INSTRUCTION_CONTRIBUTION_VERSION = "ace.intelligence.instruction-contribution/v1alpha1"
INSTRUCTION_RESOLUTION_RECEIPT_VERSION = "ace.intelligence.instruction-resolution-receipt/v1alpha1"

MAX_REFERENCES = 256


class CompositionSemanticContract(FrozenContract):
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


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    if value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _sorted_unique(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    if len(values) > MAX_REFERENCES:
        raise ValueError(f"{name} exceed the {MAX_REFERENCES}-item bound")
    for value in values:
        _bounded(value, name=name)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values))


def _derive_identity(
    instance: CompositionSemanticContract,
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
        raise ValueError(f"{id_field} does not match exact semantic material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact semantic material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class LifecycleStage(StrEnum):
    ACTIVATE = "activate"
    ACQUIRE = "acquire"
    GROUND = "ground"
    DETECT = "detect"
    INVESTIGATE = "investigate"
    COMPOSE = "compose"
    DELIBERATE = "deliberate"
    DECIDE = "decide"
    ACT = "act"
    VERIFY = "verify"
    DELIVER = "deliver"
    OBSERVE = "observe"
    LEARN_EVOLVE = "learn_evolve"
    OPERATE_OFFBOARD = "operate_offboard"


class OrchestrationPattern(StrEnum):
    DETERMINISTIC = "deterministic"
    SOLO = "solo"
    PIPELINE = "pipeline"
    FANOUT_JOIN = "fanout_join"
    ADVERSARIAL = "adversarial"
    QUORUM = "quorum"
    HUMAN_GATE = "human_gate"
    SCHEDULED = "scheduled"


class InstructionLayer(IntEnum):
    CORE_INVARIANTS = 1
    RUNTIME_AUTHORITY_SAFETY = 2
    DOMAIN_ACTIVATION = 3
    AGENT_DEFINITION = 4
    STAGE_ROLE_BINDING = 5
    TASK_BRIEF = 6
    AUTHORIZED_CONTEXT_MANIFEST = 7
    HANDOFF_DESTINATION = 8


class CandidateDisposition(StrEnum):
    ELIGIBLE = "eligible"
    SELECTED = "selected"
    REJECTED = "rejected"
    OMITTED = "omitted"


class GovernedAgentDefinitionRevisionV1Alpha1(CompositionSemanticContract):
    """Approved reusable behavior; never a schedule, grant, route, or run."""

    contract: Literal["ace.intelligence.governed-agent-definition-revision/v1alpha1"] = (
        AGENT_DEFINITION_REVISION_VERSION
    )
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
    approval_receipt_ref: str
    lifecycle_ref: str
    implementation_protocol_ref: str
    prior_revision_ref: str | None = None
    definition_revision_id: str | None = None
    definition_digest: str | None = None

    @field_validator(
        "principal_id",
        "failure_policy_ref",
        "approval_receipt_ref",
        "lifecycle_ref",
        "implementation_protocol_ref",
        "prior_revision_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

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

    @field_validator("eligible_stages")
    @classmethod
    def normalize_stages(cls, value: tuple[LifecycleStage, ...]) -> tuple[LifecycleStage, ...]:
        if len(value) != len(set(value)):
            raise ValueError("eligible stages must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("maximum_authority")
    @classmethod
    def normalize_authority(cls, value: tuple[AuthorityClass, ...]) -> tuple[AuthorityClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("maximum authority must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("definition_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="definition_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if set(self.required_tool_refs).intersection(self.optional_tool_refs):
            raise ValueError("a tool cannot be both required and optional")
        _derive_identity(
            self,
            prefix="agent_definition_revision",
            id_field="definition_revision_id",
            digest_field="definition_digest",
        )
        return self


class StageRoleBindingRevisionV1Alpha1(CompositionSemanticContract):
    """A stage-specific narrowing of one governed agent definition."""

    contract: Literal["ace.intelligence.stage-role-binding-revision/v1alpha1"] = STAGE_ROLE_BINDING_REVISION_VERSION
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
    lifecycle_ref: str
    prior_binding_ref: str | None = None
    binding_revision_id: str | None = None
    binding_digest: str | None = None

    @field_validator(
        "role_label",
        "objective_class",
        "independence_policy_ref",
        "escalation_policy_ref",
        "lifecycle_ref",
        "prior_binding_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

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

    @field_validator("orchestration_patterns")
    @classmethod
    def normalize_patterns(cls, value: tuple[OrchestrationPattern, ...]) -> tuple[OrchestrationPattern, ...]:
        if len(value) != len(set(value)):
            raise ValueError("orchestration patterns must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("authority_ceiling")
    @classmethod
    def normalize_authority(cls, value: tuple[AuthorityClass, ...]) -> tuple[AuthorityClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("authority ceiling must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("binding_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="binding_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(
            self,
            prefix="stage_role_binding_revision",
            id_field="binding_revision_id",
            digest_field="binding_digest",
        )
        return self


def validate_role_binding_narrows_definition(
    definition: GovernedAgentDefinitionRevisionV1Alpha1,
    binding: StageRoleBindingRevisionV1Alpha1,
) -> None:
    """Fail closed unless the stage binding is a strict subset of its definition."""

    expected = (str(definition.definition_revision_id), str(definition.definition_digest))
    actual = (binding.definition_revision.artifact_id, binding.definition_revision.artifact_digest)
    if actual != expected:
        raise ValueError("role binding must reference the exact governed definition revision")
    if binding.stage not in definition.eligible_stages:
        raise ValueError("role binding stage is not eligible under the definition")
    checks = (
        (binding.required_input_contracts, definition.accepted_input_contracts, "input contracts"),
        (binding.expected_output_contracts, definition.produced_output_contracts, "output contracts"),
        (binding.tool_refs, definition.required_tool_refs + definition.optional_tool_refs, "tools"),
        (binding.source_policy_refs, definition.source_policy_refs, "source policies"),
        (binding.destination_policy_refs, definition.destination_policy_refs, "destination policies"),
        (binding.authority_ceiling, definition.maximum_authority, "authority"),
    )
    for narrower, wider, label in checks:
        if not set(narrower).issubset(set(wider)):
            raise ValueError(f"role binding widens definition {label}")
    for field in CompositionBudgetV1Alpha1.model_fields:
        if getattr(binding.budget_ceiling, field) > getattr(definition.budget_ceiling, field):
            raise ValueError(f"role binding widens definition budget: {field}")


class CompositionRequirementV1Alpha1(CompositionSemanticContract):
    contract: Literal["ace.intelligence.composition-requirement/v1alpha1"] = COMPOSITION_REQUIREMENT_VERSION
    stage: LifecycleStage
    objective_class: str
    required_input_contracts: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    required_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    allowed_patterns: tuple[OrchestrationPattern, ...] = Field(min_length=1, max_length=8)
    maximum_authority: tuple[AuthorityClass, ...] = Field(default_factory=tuple)
    deterministic_sufficient: bool = False
    human_gate_required: bool = False
    requirement_id: str | None = None
    requirement_digest: str | None = None

    @field_validator("objective_class")
    @classmethod
    def validate_objective(cls, value: str) -> str:
        return _bounded(value, name="objective_class")

    @field_validator("required_input_contracts", "required_output_contracts")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("allowed_patterns")
    @classmethod
    def normalize_patterns(cls, value: tuple[OrchestrationPattern, ...]) -> tuple[OrchestrationPattern, ...]:
        if len(value) != len(set(value)):
            raise ValueError("allowed patterns must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("maximum_authority")
    @classmethod
    def normalize_authority(cls, value: tuple[AuthorityClass, ...]) -> tuple[AuthorityClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("maximum authority must be unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("requirement_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="requirement_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.human_gate_required and OrchestrationPattern.HUMAN_GATE not in self.allowed_patterns:
            raise ValueError("a required human gate must be an allowed pattern")
        _derive_identity(
            self,
            prefix="composition_requirement",
            id_field="requirement_id",
            digest_field="requirement_digest",
        )
        return self


class CompositionCandidateV1Alpha1(CompositionSemanticContract):
    contract: Literal["ace.intelligence.composition-candidate/v1alpha1"] = COMPOSITION_CANDIDATE_VERSION
    requirement: ExactArtifactReferenceV1Alpha1
    participant_kind: ParticipantKind
    participant_ref: str
    definition_revision: ExactArtifactReferenceV1Alpha1 | None = None
    role_binding: ExactArtifactReferenceV1Alpha1 | None = None
    authorization_receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    compatibility_receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    candidate_id: str | None = None
    candidate_digest: str | None = None

    @field_validator("participant_ref")
    @classmethod
    def validate_participant(cls, value: str) -> str:
        return _bounded(value, name="participant_ref")

    @field_validator("authorization_receipt_refs", "compatibility_receipt_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("candidate_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="candidate_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.participant_kind in {ParticipantKind.MODEL_AGENT, ParticipantKind.EXTERNAL_AGENT}:
            if self.definition_revision is None or self.role_binding is None:
                raise ValueError("agent candidates require definition and role-binding coordinates")
        _derive_identity(
            self,
            prefix="composition_candidate",
            id_field="candidate_id",
            digest_field="candidate_digest",
        )
        return self


class CandidateDispositionV1Alpha1(CompositionSemanticContract):
    candidate: ExactArtifactReferenceV1Alpha1
    disposition: CandidateDisposition
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("reason_codes")
    @classmethod
    def normalize_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="reason codes")


class RosterSelectionReceiptV1Alpha1(CompositionSemanticContract):
    contract: Literal["ace.intelligence.roster-selection-receipt/v1alpha1"] = ROSTER_SELECTION_RECEIPT_VERSION
    requirement: ExactArtifactReferenceV1Alpha1
    policy_revision_ref: str
    dispositions: tuple[CandidateDispositionV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("policy_revision_ref")
    @classmethod
    def validate_policy(cls, value: str) -> str:
        return _bounded(value, name="policy_revision_ref")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        candidate_ids = [item.candidate.artifact_id for item in self.dispositions]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("each candidate must receive exactly one disposition")
        _derive_identity(self, prefix="roster_selection_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class InstructionConstraintsV1Alpha1(CompositionSemanticContract):
    """None means no additional narrowing; an empty tuple means deny all."""

    tool_refs: tuple[str, ...] | None = None
    source_scope_refs: tuple[str, ...] | None = None
    destination_scope_refs: tuple[str, ...] | None = None
    authority_classes: tuple[AuthorityClass, ...] | None = None

    @field_validator("tool_refs", "source_scope_refs", "destination_scope_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...] | None, info) -> tuple[str, ...] | None:
        return _sorted_unique(value, name=info.field_name) if value is not None else None

    @field_validator("authority_classes")
    @classmethod
    def normalize_authority(cls, value: tuple[AuthorityClass, ...] | None) -> tuple[AuthorityClass, ...] | None:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("authority classes must be unique")
        return tuple(sorted(value, key=lambda item: item.value))


class InstructionContributionV1Alpha1(CompositionSemanticContract):
    contract: Literal["ace.intelligence.instruction-contribution/v1alpha1"] = INSTRUCTION_CONTRIBUTION_VERSION
    product_id: str
    layer: InstructionLayer
    policy_ref: ExactArtifactReferenceV1Alpha1
    constraints: InstructionConstraintsV1Alpha1
    instruction_content_ref: ExactArtifactReferenceV1Alpha1 | None = None
    source_content_is_data_only: bool = True
    contribution_id: str | None = None
    contribution_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _bounded(value, name="product_id")

    @field_validator("contribution_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="contribution_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.layer == InstructionLayer.AUTHORIZED_CONTEXT_MANIFEST and not self.source_content_is_data_only:
            raise ValueError("Context Manifest content remains data unless separately governed as instruction policy")
        _derive_identity(
            self,
            prefix="instruction_contribution",
            id_field="contribution_id",
            digest_field="contribution_digest",
        )
        return self


class InstructionResolutionIssueV1Alpha1(CompositionSemanticContract):
    issue_code: str
    layer: InstructionLayer | None = None
    contribution_ref: str | None = None

    @field_validator("issue_code", "contribution_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None


class InstructionResolutionReceiptV1Alpha1(CompositionSemanticContract):
    contract: Literal["ace.intelligence.instruction-resolution-receipt/v1alpha1"] = (
        INSTRUCTION_RESOLUTION_RECEIPT_VERSION
    )
    product_id: str
    ordered_contributions: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(max_length=MAX_REFERENCES)
    effective_constraints: InstructionConstraintsV1Alpha1
    issues: tuple[InstructionResolutionIssueV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    blocked: bool
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return _bounded(value, name="product_id")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.blocked != bool(self.issues):
            raise ValueError("blocked must exactly reflect instruction-resolution issues")
        _derive_identity(
            self,
            prefix="instruction_resolution_receipt",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


def _intersect(current: tuple[Any, ...] | None, narrower: tuple[Any, ...] | None) -> tuple[Any, ...] | None:
    if narrower is None:
        return current
    if current is None:
        return narrower
    return tuple(item for item in current if item in set(narrower))


def resolve_instruction_contributions(
    contributions: tuple[InstructionContributionV1Alpha1, ...],
    *,
    required_layers: tuple[InstructionLayer, ...] = tuple(InstructionLayer),
) -> InstructionResolutionReceiptV1Alpha1:
    """Resolve constraints in canonical precedence order without prompt content."""

    products = {item.product_id for item in contributions}
    if len(products) != 1:
        raise ValueError("instruction contributions must share one exact product")
    ordered = tuple(sorted(contributions, key=lambda item: (int(item.layer), str(item.contribution_id))))
    present_layers = {item.layer for item in ordered}
    issues = [
        InstructionResolutionIssueV1Alpha1(
            issue_code="ace.composition.instruction.missing_required_layer",
            layer=layer,
        )
        for layer in required_layers
        if layer not in present_layers
    ]
    tools: tuple[str, ...] | None = None
    sources: tuple[str, ...] | None = None
    destinations: tuple[str, ...] | None = None
    authority: tuple[AuthorityClass, ...] | None = None
    for item in ordered:
        tools = _intersect(tools, item.constraints.tool_refs)
        sources = _intersect(sources, item.constraints.source_scope_refs)
        destinations = _intersect(destinations, item.constraints.destination_scope_refs)
        authority = _intersect(authority, item.constraints.authority_classes)
    references = tuple(
        ExactArtifactReferenceV1Alpha1(
            artifact_id=str(item.contribution_id),
            artifact_digest=str(item.contribution_digest),
            artifact_contract=item.contract,
        )
        for item in ordered
    )
    return InstructionResolutionReceiptV1Alpha1(
        product_id=next(iter(products)),
        ordered_contributions=references,
        effective_constraints=InstructionConstraintsV1Alpha1(
            tool_refs=tools,
            source_scope_refs=sources,
            destination_scope_refs=destinations,
            authority_classes=authority,
        ),
        issues=tuple(issues),
        blocked=bool(issues),
    )


__all__ = [
    "AGENT_DEFINITION_REVISION_VERSION",
    "COMPOSITION_CANDIDATE_VERSION",
    "COMPOSITION_REQUIREMENT_VERSION",
    "INSTRUCTION_CONTRIBUTION_VERSION",
    "INSTRUCTION_RESOLUTION_RECEIPT_VERSION",
    "ROSTER_SELECTION_RECEIPT_VERSION",
    "STAGE_ROLE_BINDING_REVISION_VERSION",
    "CandidateDisposition",
    "CandidateDispositionV1Alpha1",
    "CompositionCandidateV1Alpha1",
    "CompositionRequirementV1Alpha1",
    "GovernedAgentDefinitionRevisionV1Alpha1",
    "InstructionConstraintsV1Alpha1",
    "InstructionContributionV1Alpha1",
    "InstructionLayer",
    "InstructionResolutionIssueV1Alpha1",
    "InstructionResolutionReceiptV1Alpha1",
    "LifecycleStage",
    "OrchestrationPattern",
    "RosterSelectionReceiptV1Alpha1",
    "StageRoleBindingRevisionV1Alpha1",
    "resolve_instruction_contributions",
    "validate_role_binding_narrows_definition",
]
