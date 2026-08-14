"""Provider-neutral Core contracts for lifecycle-wide agent composition.

These contracts own immutable task-time control coordinates only.  They do not
select providers, activate Domain Packs, grant authority, persist memory, or
execute participants.  Higher layers interpret stage and orchestration
semantics; adapters implement storage and execution behind application ports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash

AGENT_PRINCIPAL_VERSION = "ace.core.agent-principal/v1alpha1"
EXACT_ARTIFACT_REFERENCE_VERSION = "ace.core.exact-artifact-reference/v1alpha1"
DOMAIN_ACTIVATION_LINEAGE_VERSION = "ace.core.domain-activation-lineage/v1alpha1"
AUTHORITY_COORDINATE_VERSION = "ace.core.authority-coordinate/v1alpha1"
TASK_COMPOSITION_PLAN_VERSION = "ace.core.task-composition-plan/v1alpha1"
STAGE_RUN_MANIFEST_VERSION = "ace.core.stage-run-manifest/v1alpha1"
STAGE_RUN_RECEIPT_VERSION = "ace.core.stage-run-receipt/v1alpha1"
STAGE_HANDOFF_CONTRACT_VERSION = "ace.core.stage-handoff-contract/v1alpha1"
STAGE_HANDOFF_RECEIPT_VERSION = "ace.core.stage-handoff-receipt/v1alpha1"
DELIVERY_RECEIPT_VERSION = "ace.core.delivery-receipt/v1alpha1"

MAX_REFERENCES = 256
MAX_PARTICIPANTS = 64
MAX_NODES = 128


class CompositionContract(FrozenContract):
    """Strict immutable base for composition control-plane contracts."""

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


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _sorted_unique(values: tuple[str, ...], *, name: str, maximum: int = MAX_REFERENCES) -> tuple[str, ...]:
    if len(values) > maximum:
        raise ValueError(f"{name} exceed the {maximum}-item bound")
    for value in values:
        _bounded(value, name=name)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values))


def _derive_identity(
    instance: CompositionContract,
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
        raise ValueError(f"{id_field} does not match exact contract material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class PrincipalKind(StrEnum):
    MODEL_AGENT = "model_agent"
    EXTERNAL_AGENT = "external_agent"
    SERVICE = "service"


class PrincipalLifecycle(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ParticipantKind(StrEnum):
    DETERMINISTIC_SERVICE = "deterministic_service"
    MODEL_AGENT = "model_agent"
    EXTERNAL_AGENT = "external_agent"
    HUMAN = "human"
    COMMITTEE = "committee"
    ADAPTER = "adapter"


class AuthorityClass(StrEnum):
    INTELLIGENCE_BUILD = "intelligence_build"
    OBSERVE_READ = "observe_read"
    DERIVE_PROPOSE = "derive_propose"
    DECIDE_APPROVE = "decide_approve"
    MUTATE_INTERNAL = "mutate_internal"
    EXECUTE_EXTERNAL = "execute_external"
    DELIVER_EXPORT = "deliver_export"
    ADMINISTER_LIFECYCLE = "administer_lifecycle"


class RunState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    ABSTAINED = "abstained"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BLOCKED = "blocked"


class HandoffState(StrEnum):
    PREPARED = "prepared"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CompositionNodeKind(StrEnum):
    PLANNING = "planning"
    EXECUTION = "execution"
    JOIN = "join"
    HUMAN_GATE = "human_gate"
    HANDOFF = "handoff"


class ExactArtifactReferenceV1Alpha1(CompositionContract):
    """Content-free coordinate for one exact immutable artifact."""

    contract: Literal["ace.core.exact-artifact-reference/v1alpha1"] = EXACT_ARTIFACT_REFERENCE_VERSION
    artifact_id: str
    artifact_digest: str
    artifact_contract: str

    @field_validator("artifact_id", "artifact_contract")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("artifact_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="artifact_digest")


class DomainActivationLineageV1Alpha1(CompositionContract):
    """Historical activation lineage only; never current runtime authority."""

    contract: Literal["ace.core.domain-activation-lineage/v1alpha1"] = DOMAIN_ACTIVATION_LINEAGE_VERSION
    commit_reference: ExactArtifactReferenceV1Alpha1
    live_authority: Literal[False] = False

    @model_validator(mode="after")
    def reject_plan_coordinates(self) -> Self:
        if self.commit_reference.artifact_contract != "ace.application.domain-activation-commit-reference/v1alpha2":
            raise ValueError("activation lineage must use the accepted historical commit-reference contract")
        if "activation-plan" in self.commit_reference.artifact_contract or self.commit_reference.artifact_id.startswith(
            "activation_plan:"
        ):
            raise ValueError("composition lineage cannot embed a Domain Activation Plan")
        return self


class CompositionBudgetV1Alpha1(CompositionContract):
    max_items: int = Field(default=256, ge=0)
    max_tokens: int = Field(default=0, ge=0)
    max_calls: int = Field(default=0, ge=0)
    max_latency_ms: int = Field(default=0, ge=0)
    max_cost_microunits: int = Field(default=0, ge=0)
    max_concurrency: int = Field(default=1, ge=1, le=64)
    max_external_effects: int = Field(default=0, ge=0)


class AgentPrincipalV1Alpha1(CompositionContract):
    """Stable worker identity without embedded authority, context, or route policy."""

    contract: Literal["ace.core.agent-principal/v1alpha1"] = AGENT_PRINCIPAL_VERSION
    product_id: str
    principal_key: str
    principal_kind: PrincipalKind
    owner_ref: str
    implementation_ref: str
    supported_protocol_versions: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    lifecycle: PrincipalLifecycle
    lifecycle_revision: int = Field(ge=1)
    principal_id: str | None = None
    principal_digest: str | None = None

    @field_validator("product_id", "principal_key", "owner_ref", "implementation_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("supported_protocol_versions")
    @classmethod
    def normalize_protocols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique(value, name="supported protocol versions")

    @field_validator("principal_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="principal_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(self, prefix="agent_principal", id_field="principal_id", digest_field="principal_digest")
        return self


class AuthorityCoordinateV1Alpha1(CompositionContract):
    """One exact, separately governed authority dimension."""

    contract: Literal["ace.core.authority-coordinate/v1alpha1"] = AUTHORITY_COORDINATE_VERSION
    product_id: str
    principal_ref: str
    authority_class: AuthorityClass
    grant_ref: str
    scope_ref: str
    policy_ref: str
    expires_at: datetime | None = None

    @field_validator("product_id", "principal_ref", "grant_ref", "scope_ref", "policy_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        return _aware(value, name="expires_at") if value is not None else None


class CompositionParticipantV1Alpha1(CompositionContract):
    composition_participant_id: str
    participant_kind: ParticipantKind
    participant_ref: str
    definition_revision: ExactArtifactReferenceV1Alpha1 | None = None
    role_binding: ExactArtifactReferenceV1Alpha1 | None = None
    required: bool = True
    authority: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    source_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    destination_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)

    @field_validator("composition_participant_id", "participant_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("tool_refs", "source_scope_refs", "destination_scope_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("authority")
    @classmethod
    def normalize_authority(
        cls, value: tuple[AuthorityCoordinateV1Alpha1, ...]
    ) -> tuple[AuthorityCoordinateV1Alpha1, ...]:
        keys = [(item.authority_class, item.grant_ref, item.scope_ref) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("participant authority coordinates must be unique")
        return tuple(sorted(value, key=lambda item: (item.authority_class.value, item.grant_ref, item.scope_ref)))

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        if self.participant_kind in {ParticipantKind.MODEL_AGENT, ParticipantKind.EXTERNAL_AGENT}:
            if self.definition_revision is None or self.role_binding is None:
                raise ValueError("agent participants require exact definition and role-binding coordinates")
        return self


class CompositionNodeV1Alpha1(CompositionContract):
    node_id: str
    node_kind: CompositionNodeKind
    composition_participant_id: str | None = None
    depends_on: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_NODES)
    input_contracts: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    output_contracts: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    validator_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    exit_criteria_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    required: bool = True

    @field_validator("node_id", "composition_participant_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("depends_on", "input_contracts", "output_contracts", "validator_refs", "exit_criteria_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(
            value, name=info.field_name, maximum=MAX_NODES if info.field_name == "depends_on" else MAX_REFERENCES
        )

    @model_validator(mode="after")
    def validate_participant(self) -> Self:
        participant_required = self.node_kind in {CompositionNodeKind.EXECUTION, CompositionNodeKind.HUMAN_GATE}
        if participant_required and self.composition_participant_id is None:
            raise ValueError(f"{self.node_kind.value} nodes require composition_participant_id")
        if self.node_kind == CompositionNodeKind.JOIN and self.composition_participant_id is not None:
            raise ValueError("join nodes are deterministic graph operations, not participant identities")
        return self


class TaskCompositionPlanV1Alpha1(CompositionContract):
    """Immutable task-time graph; deliberately distinct from Domain Activation Plan."""

    contract: Literal["ace.core.task-composition-plan/v1alpha1"] = TASK_COMPOSITION_PLAN_VERSION
    product_id: str
    actor_ref: str
    session_ref: str
    task_ref: str
    work_ref: str | None = None
    case_ref: str | None = None
    objective: str = Field(max_length=4_000)
    stage_id: str
    activation_lineage: DomainActivationLineageV1Alpha1 | None = None
    trigger_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=64)
    classifier_revision_ref: str
    routing_revision_ref: str
    policy_revision_ref: str
    composer_revision_ref: str
    participants: tuple[CompositionParticipantV1Alpha1, ...] = Field(max_length=MAX_PARTICIPANTS)
    nodes: tuple[CompositionNodeV1Alpha1, ...] = Field(min_length=1, max_length=MAX_NODES)
    orchestration_pattern: str
    expected_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    gate_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    allowed_next_stage_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    aggregate_budget: CompositionBudgetV1Alpha1
    context_request_ref: str
    candidate_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_REFERENCES,
    )
    context_receipts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_REFERENCES,
    )
    failure_policy_ref: str
    created_at: datetime
    expires_at: datetime | None = None
    composition_plan_id: str | None = None
    composition_plan_digest: str | None = None

    @field_validator(
        "product_id",
        "actor_ref",
        "session_ref",
        "task_ref",
        "work_ref",
        "case_ref",
        "stage_id",
        "classifier_revision_ref",
        "routing_revision_ref",
        "policy_revision_ref",
        "composer_revision_ref",
        "orchestration_pattern",
        "context_request_ref",
        "failure_policy_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator(
        "expected_output_contracts",
        "gate_refs",
        "allowed_next_stage_ids",
    )
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("trigger_artifacts", "candidate_receipts", "context_receipts")
    @classmethod
    def normalize_artifact_refs(
        cls,
        value: tuple[ExactArtifactReferenceV1Alpha1, ...],
        info,
    ) -> tuple[ExactArtifactReferenceV1Alpha1, ...]:
        identities = [(item.artifact_contract, item.artifact_id, item.artifact_digest) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError(f"{info.field_name} must contain unique exact artifacts")
        return tuple(sorted(value, key=lambda item: (item.artifact_contract, item.artifact_id)))

    @field_validator("participants")
    @classmethod
    def normalize_participants(
        cls,
        value: tuple[CompositionParticipantV1Alpha1, ...],
    ) -> tuple[CompositionParticipantV1Alpha1, ...]:
        return tuple(sorted(value, key=lambda item: item.composition_participant_id))

    @field_validator("nodes")
    @classmethod
    def normalize_nodes(cls, value: tuple[CompositionNodeV1Alpha1, ...]) -> tuple[CompositionNodeV1Alpha1, ...]:
        return tuple(sorted(value, key=lambda item: item.node_id))

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @field_validator("composition_plan_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="composition_plan_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_graph_and_identity(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("plan expiry must be later than creation")
        participant_ids = [item.composition_participant_id for item in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("plan participant IDs must be unique")
        node_ids = [item.node_id for item in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("plan node IDs must be unique")
        known_nodes = set(node_ids)
        known_participants = set(participant_ids)
        for participant in self.participants:
            if any(item.product_id != self.product_id for item in participant.authority):
                raise ValueError("participant authority coordinates must match the plan product")
        for node in self.nodes:
            if node.node_id in node.depends_on or not set(node.depends_on).issubset(known_nodes):
                raise ValueError("plan dependencies must reference other declared nodes")
            if (
                node.composition_participant_id is not None
                and node.composition_participant_id not in known_participants
            ):
                raise ValueError("plan nodes must reference declared participants")
        visiting: set[str] = set()
        visited: set[str] = set()
        dependencies = {item.node_id: set(item.depends_on) for item in self.nodes}

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("plan graph must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in dependencies[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)
        _derive_identity(
            self,
            prefix="task_composition_plan",
            id_field="composition_plan_id",
            digest_field="composition_plan_digest",
        )
        return self


class StageRunManifestV1Alpha1(CompositionContract):
    """Exact immutable contract for one participant invocation."""

    contract: Literal["ace.core.stage-run-manifest/v1alpha1"] = STAGE_RUN_MANIFEST_VERSION
    plan: ExactArtifactReferenceV1Alpha1
    product_id: str
    stage_id: str
    node_id: str
    composition_participant_id: str
    definition_revision: ExactArtifactReferenceV1Alpha1 | None = None
    role_binding: ExactArtifactReferenceV1Alpha1 | None = None
    task_ref: str
    invocation_key: str
    instruction_resolution: ExactArtifactReferenceV1Alpha1
    instruction_layer_refs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=16)
    context_manifest: ExactArtifactReferenceV1Alpha1
    tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    source_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    destination_scope_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    authority: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    execution_binding: ExactArtifactReferenceV1Alpha1
    input_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_REFERENCES
    )
    output_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    validator_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    exit_criteria_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    handoff_target_ref: str | None = None
    budget: CompositionBudgetV1Alpha1
    cancellation_ref: str
    retry_ref: str
    idempotency_key: str
    degraded_policy_ref: str
    escalation_policy_ref: str
    created_at: datetime
    expires_at: datetime | None = None
    manifest_id: str | None = None
    manifest_digest: str | None = None

    @field_validator(
        "product_id",
        "stage_id",
        "node_id",
        "composition_participant_id",
        "task_ref",
        "invocation_key",
        "handoff_target_ref",
        "cancellation_ref",
        "retry_ref",
        "idempotency_key",
        "degraded_policy_ref",
        "escalation_policy_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator(
        "tool_refs",
        "source_scope_refs",
        "destination_scope_refs",
        "output_contracts",
        "validator_refs",
        "exit_criteria_refs",
    )
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @field_validator("manifest_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="manifest_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("manifest expiry must be later than creation")
        if self.plan.artifact_contract != TASK_COMPOSITION_PLAN_VERSION or not self.plan.artifact_id.startswith(
            "task_composition_plan:"
        ):
            raise ValueError("manifest must reference an exact Task Composition Plan")
        if "provider-route" in self.execution_binding.artifact_contract:
            raise ValueError("provider routes are observed run facts, not manifest execution bindings")
        if any(item.product_id != self.product_id for item in self.authority):
            raise ValueError("manifest authority coordinates must match the manifest product")
        _derive_identity(
            self,
            prefix="stage_run_manifest",
            id_field="manifest_id",
            digest_field="manifest_digest",
        )
        return self


class UsageV1Alpha1(CompositionContract):
    items: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    calls: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost_microunits: int = Field(default=0, ge=0)
    external_effects: int = Field(default=0, ge=0)


class ContextUseState(StrEnum):
    ELIGIBLE = "eligible"
    AUTHORIZED = "authorized"
    SELECTED = "selected"
    INJECTED = "injected"
    REFLECTED = "reflected"
    DECISION_MATERIAL = "decision_material"


class StageRunReceiptV1Alpha1(CompositionContract):
    """Observed execution facts, separate from the intended manifest."""

    contract: Literal["ace.core.stage-run-receipt/v1alpha1"] = STAGE_RUN_RECEIPT_VERSION
    plan: ExactArtifactReferenceV1Alpha1
    manifest: ExactArtifactReferenceV1Alpha1
    product_id: str
    composition_participant_id: str
    attempt: int = Field(ge=1)
    state: RunState
    started_at: datetime | None = None
    ended_at: datetime
    actual_route: ExactArtifactReferenceV1Alpha1 | None = None
    usage: UsageV1Alpha1
    actual_tool_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    authority_exercised: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    output_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_REFERENCES
    )
    context_states: tuple[ContextUseState, ...] = Field(default_factory=tuple)
    omission_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    issue_codes: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    retry_of_receipt_ref: str | None = None
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "composition_participant_id", "retry_of_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("actual_tool_refs", "omission_refs", "issue_codes")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("context_states")
    @classmethod
    def normalize_context_states(cls, value: tuple[ContextUseState, ...]) -> tuple[ContextUseState, ...]:
        order = list(ContextUseState)
        if len(value) != len(set(value)):
            raise ValueError("context states must be unique")
        present = set(value)
        highest = max((order.index(item) for item in value), default=-1)
        if any(order[index] not in present for index in range(highest + 1)):
            raise ValueError("context states must preserve eligible-to-material lineage without gaps")
        return tuple(item for item in order if item in present)

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.started_at is not None and self.ended_at < self.started_at:
            raise ValueError("run receipt cannot end before it starts")
        if self.state == RunState.BLOCKED and self.started_at is not None:
            raise ValueError("blocked means execution never began")
        if self.plan.artifact_contract != TASK_COMPOSITION_PLAN_VERSION:
            raise ValueError("run receipt must reference a Task Composition Plan")
        if self.manifest.artifact_contract != STAGE_RUN_MANIFEST_VERSION:
            raise ValueError("run receipt must reference a Stage Run Manifest")
        if any(item.product_id != self.product_id for item in self.authority_exercised):
            raise ValueError("exercised authority must match the run product")
        _derive_identity(self, prefix="stage_run_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class StageHandoffContractV1Alpha1(CompositionContract):
    contract: Literal["ace.core.stage-handoff-contract/v1alpha1"] = STAGE_HANDOFF_CONTRACT_VERSION
    source_stage_id: str
    target_stage_id: str
    source_product_id: str
    target_product_id: str
    destination_kind: str
    accepted_contracts: tuple[str, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    required_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    required_policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    completion_policy_ref: str
    retry_policy_ref: str
    acknowledgment_policy_ref: str
    receiving_authority: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    allowed_next_stage_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    contract_id: str | None = None
    contract_digest: str | None = None

    @field_validator(
        "source_stage_id",
        "target_stage_id",
        "source_product_id",
        "target_product_id",
        "destination_kind",
        "completion_policy_ref",
        "retry_policy_ref",
        "acknowledgment_policy_ref",
    )
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("accepted_contracts", "required_evidence_refs", "required_policy_refs", "allowed_next_stage_ids")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("contract_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="contract_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if any(item.product_id != self.target_product_id for item in self.receiving_authority):
            raise ValueError("receiving authority coordinates must match the target product")
        _derive_identity(self, prefix="stage_handoff_contract", id_field="contract_id", digest_field="contract_digest")
        return self


class StageHandoffReceiptV1Alpha1(CompositionContract):
    contract: Literal["ace.core.stage-handoff-receipt/v1alpha1"] = STAGE_HANDOFF_RECEIPT_VERSION
    handoff_contract: ExactArtifactReferenceV1Alpha1
    source_plan: ExactArtifactReferenceV1Alpha1
    source_runs: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    target_ref: str
    artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    authority_used: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    approval_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    policy_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    state: HandoffState
    external_send_occurred: Literal[False] = False
    omitted_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    idempotency_key: str
    retry_of_receipt_ref: str | None = None
    occurred_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("target_ref", "idempotency_key", "retry_of_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("approval_refs", "policy_refs", "omitted_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _sorted_unique(value, name=info.field_name)

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.source_plan.artifact_contract != TASK_COMPOSITION_PLAN_VERSION:
            raise ValueError("handoff receipt must reference a Task Composition Plan")
        _derive_identity(self, prefix="stage_handoff_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class DeliveryReceiptV1Alpha1(CompositionContract):
    """Explicit destination transfer, separate from an internal stage handoff."""

    contract: Literal["ace.core.delivery-receipt/v1alpha1"] = DELIVERY_RECEIPT_VERSION
    source_handoff: ExactArtifactReferenceV1Alpha1
    destination_ref: str
    destination_contract_ref: str
    artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    authority_used: tuple[AuthorityCoordinateV1Alpha1, ...] = Field(min_length=1, max_length=32)
    state: HandoffState
    external_effect_occurred: bool
    acknowledgment_ref: str | None = None
    idempotency_key: str
    retry_of_receipt_ref: str | None = None
    occurred_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "destination_ref",
        "destination_contract_ref",
        "acknowledgment_ref",
        "idempotency_key",
        "retry_of_receipt_ref",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")

    @field_validator("receipt_digest")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="receipt_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_delivery_and_identity(self) -> Self:
        if self.state == HandoffState.PREPARED and self.external_effect_occurred:
            raise ValueError("prepared delivery cannot claim an external effect")
        if self.state == HandoffState.ACKNOWLEDGED and self.acknowledgment_ref is None:
            raise ValueError("acknowledged delivery requires an acknowledgment reference")
        _derive_identity(self, prefix="delivery_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


def validate_run_receipt_against_manifest(
    manifest: StageRunManifestV1Alpha1,
    receipt: StageRunReceiptV1Alpha1,
) -> None:
    """Validate observed execution as a subset of one immutable manifest."""

    if receipt.plan != manifest.plan:
        raise ValueError("run receipt plan coordinate does not match the manifest")
    expected_manifest = (str(manifest.manifest_id), str(manifest.manifest_digest), manifest.contract)
    actual_manifest = (
        receipt.manifest.artifact_id,
        receipt.manifest.artifact_digest,
        receipt.manifest.artifact_contract,
    )
    if actual_manifest != expected_manifest:
        raise ValueError("run receipt does not reference the exact manifest")
    if receipt.product_id != manifest.product_id:
        raise ValueError("run receipt product does not match the manifest")
    if receipt.composition_participant_id != manifest.composition_participant_id:
        raise ValueError("run receipt participant does not match the manifest")
    if not set(receipt.actual_tool_refs).issubset(set(manifest.tool_refs)):
        raise ValueError("run receipt reports tools outside the immutable manifest")
    allowed_authority = {
        (item.authority_class, item.grant_ref, item.scope_ref, item.policy_ref) for item in manifest.authority
    }
    actual_authority = {
        (item.authority_class, item.grant_ref, item.scope_ref, item.policy_ref) for item in receipt.authority_exercised
    }
    if not actual_authority.issubset(allowed_authority):
        raise ValueError("run receipt reports authority outside the immutable manifest")
    usage_to_budget = {
        "items": "max_items",
        "tokens": "max_tokens",
        "calls": "max_calls",
        "latency_ms": "max_latency_ms",
        "cost_microunits": "max_cost_microunits",
        "external_effects": "max_external_effects",
    }
    exceeded = [
        usage_field
        for usage_field, budget_field in usage_to_budget.items()
        if getattr(receipt.usage, usage_field) > getattr(manifest.budget, budget_field)
    ]
    if exceeded:
        raise ValueError(f"run receipt exceeds manifest budgets: {sorted(exceeded)}")


__all__ = [
    "DOMAIN_ACTIVATION_LINEAGE_VERSION",
    "AGENT_PRINCIPAL_VERSION",
    "AUTHORITY_COORDINATE_VERSION",
    "DELIVERY_RECEIPT_VERSION",
    "EXACT_ARTIFACT_REFERENCE_VERSION",
    "STAGE_HANDOFF_CONTRACT_VERSION",
    "STAGE_HANDOFF_RECEIPT_VERSION",
    "STAGE_RUN_MANIFEST_VERSION",
    "STAGE_RUN_RECEIPT_VERSION",
    "TASK_COMPOSITION_PLAN_VERSION",
    "DomainActivationLineageV1Alpha1",
    "AgentPrincipalV1Alpha1",
    "AuthorityClass",
    "AuthorityCoordinateV1Alpha1",
    "CompositionBudgetV1Alpha1",
    "CompositionContract",
    "CompositionNodeKind",
    "CompositionNodeV1Alpha1",
    "CompositionParticipantV1Alpha1",
    "ContextUseState",
    "DeliveryReceiptV1Alpha1",
    "ExactArtifactReferenceV1Alpha1",
    "HandoffState",
    "ParticipantKind",
    "PrincipalKind",
    "PrincipalLifecycle",
    "RunState",
    "StageHandoffContractV1Alpha1",
    "StageHandoffReceiptV1Alpha1",
    "StageRunManifestV1Alpha1",
    "StageRunReceiptV1Alpha1",
    "TaskCompositionPlanV1Alpha1",
    "UsageV1Alpha1",
    "validate_run_receipt_against_manifest",
]
