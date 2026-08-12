"""AM3 authorized-recall, Context Planner, manifest, and material-use contracts.

These contracts are content addressed and provider neutral.  Public receipts
carry identities, scores, omissions, and telemetry only.  Private query and
context bodies remain confined to authenticated application channels.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory import AgentMemoryScopeV1Alpha1, TemporalQueryV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.agent_memory_assertions import (
    ActivatedMemoryConstraintsV1Alpha1,
    AssertionFamilyV1Alpha1,
    AssertionLifecycle,
)
from ace.intelligence.contracts.common import validate_reference

RECEIVING_COORDINATES_VERSION = "ace.intelligence.memory-receiving-coordinates/v1alpha1"
RECALL_REQUEST_VERSION = "ace.intelligence.memory-recall-request/v1alpha1"
RETRIEVAL_POLICY_VERSION = "ace.intelligence.memory-fused-rank-policy/v1alpha1"
RETRIEVAL_SNAPSHOT_VERSION = "ace.intelligence.memory-retrieval-snapshot/v1alpha1"
SIGNAL_SCORE_VERSION = "ace.intelligence.memory-signal-score/v1alpha1"
CANDIDATE_EVIDENCE_VERSION = "ace.intelligence.memory-authorized-candidate/v1alpha1"
RECALL_RECEIPT_VERSION = "ace.intelligence.memory-recall-receipt/v1alpha1"
INSTRUCTION_REQUEST_VERSION = "ace.intelligence.memory-instruction-policy-request/v1alpha1"
INSTRUCTION_RECEIPT_VERSION = "ace.intelligence.memory-instruction-policy-resolution/v1alpha1"
CONTEXT_PLANNER_REQUEST_VERSION = "ace.intelligence.context-planner-request/v1alpha1"
CONTEXT_PLANNER_RESULT_VERSION = "ace.intelligence.context-planner-result/v1alpha1"
CONTEXT_MANIFEST_VERSION = "ace.context.manifest/v1"
CONTEXT_INJECTION_VERSION = "ace.intelligence.memory-context-injection-receipt/v1alpha1"
CONTEXT_REFLECTION_VERSION = "ace.intelligence.memory-context-reflection-receipt/v1alpha1"
DECISION_MATERIAL_VERSION = "ace.intelligence.memory-decision-material-receipt/v1alpha1"
CONTEXT_USE_VERSION = "ace.intelligence.memory-context-use-receipt/v1alpha1"
CONDITION_ASSIGNMENT_VERSION = "ace.intelligence.memory-condition-assignment/v1alpha1"
MATERIALITY_COMPARISON_VERSION = "ace.intelligence.memory-materiality-comparison/v1alpha1"
QUERY_AID_VERSION = "ace.intelligence.memory-query-aid-receipt/v1alpha1"

MAX_CANDIDATES = 200
MAX_BLOCKS = 64
MAX_SIGNALS = 16
MAX_REASONS = 128


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


def _ref(value: str, name: str) -> str:
    return validate_reference(value, name=name)


def _refs(value: Any, name: str, *, required: bool = False, limit: int = MAX_REASONS) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain stable references")
    result = tuple(sorted(set(value)))
    if required and not result:
        raise ValueError(f"{name} must not be empty")
    if len(result) > limit:
        raise ValueError(f"{name} exceeds the {limit}-item bound")
    for item in result:
        _ref(item, name)
    return result


def _strings(value: Any, name: str, *, limit: int = MAX_REASONS) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    result = tuple(sorted(set(value)))
    if len(result) > limit or any(
        not isinstance(item, str) or not item or item != item.strip() or len(item) > 240 for item in result
    ):
        raise ValueError(f"{name} must contain bounded non-empty values")
    return result


class _ContentAddressed(_StrictFrozen):
    identity_prefix: ClassVar[str]
    artifact_id: str | None = None
    artifact_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"artifact_id", "artifact_digest"})
        digest = canonical_hash(material)
        expected_id = f"{self.identity_prefix}:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.artifact_id not in (None, expected_id):
            raise ValueError("artifact_id does not match exact canonical material")
        if self.artifact_digest not in (None, expected_digest):
            raise ValueError("artifact_digest does not match exact canonical material")
        object.__setattr__(self, "artifact_id", expected_id)
        object.__setattr__(self, "artifact_digest", expected_digest)
        return self


class StructuredQuestionKind(StrEnum):
    NONE = "none"
    EXACT_IDENTITY = "exact_identity"
    ADMITTED_INSTRUCTION_REFERENCE = "admitted_instruction_reference"
    CURRENT_CORRECTION = "current_correction"
    UNCERTAINTY = "uncertainty"
    CURRENT_STATE = "current_state"


class RetrievalTier(StrEnum):
    EXACT_PROJECTION = "exact_projection"
    RESPONSE_REUSE = "response_reuse"
    STRUCTURED_LOOKUP = "structured_lookup"
    FUSED_RETRIEVAL = "fused_retrieval"
    GRAPH_EXPANSION = "graph_expansion"
    COMPACT_SYNTHESIS = "compact_synthesis"


class RetrievalSignal(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    EXACT_ENTITY = "exact_entity"
    TEMPORAL = "temporal"
    GRAPH = "graph"
    SOURCE_DIVERSITY = "source_diversity"
    GOVERNED_RELIABILITY = "governed_reliability"
    LIFECYCLE_PRIORITY = "lifecycle_priority"
    PERSONALIZED = "personalized"
    SPATIAL = "spatial"
    PRIOR_USE = "prior_use"


class ContextBlockKind(StrEnum):
    PROFILE = "profile"
    INSTRUCTION = "instruction"
    FACT = "fact"
    UNCERTAINTY = "uncertainty"
    DECISION = "decision"
    COGNITION = "cognition"
    DOCUMENT = "document"
    CODE = "code"


class ConditionKind(StrEnum):
    MEMORY = "memory"
    NO_MEMORY = "no_memory"


class EvidenceState(StrEnum):
    NOT_ESTABLISHED = "not_established"
    ESTABLISHED = "established"


class ReceivingCoordinatesV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_receiver"
    contract: Literal["ace.intelligence.memory-receiving-coordinates/v1alpha1"] = RECEIVING_COORDINATES_VERSION
    product_id: str
    task_ref: str
    composition_plan_ref: str
    composition_plan_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    stage_ref: str
    participant_ref: str
    run_manifest_ref: str
    run_manifest_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator(
        "product_id", "task_ref", "composition_plan_ref", "stage_ref", "participant_ref", "run_manifest_ref"
    )
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)


class AuthenticatedRecallRequestV1Alpha1(_ContentAddressed):
    """Private request; public receipts retain only its identity and digest."""

    identity_prefix = "memory_recall_request"
    contract: Literal["ace.intelligence.memory-recall-request/v1alpha1"] = RECALL_REQUEST_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    scope: AgentMemoryScopeV1Alpha1
    receiver: ReceivingCoordinatesV1Alpha1
    query_text: str = Field(min_length=1, max_length=8_000)
    structured_question: StructuredQuestionKind = StructuredQuestionKind.NONE
    semantic_target_ref: str | None = None
    assertion_refs: tuple[str, ...] = ()
    eligible_families: tuple[AssertionFamilyV1Alpha1, ...] = Field(min_length=1)
    temporal: TemporalQueryV1Alpha1
    requested_at: datetime

    @field_validator("semantic_target_ref")
    @classmethod
    def optional_target(cls, value: str | None) -> str | None:
        return _ref(value, "semantic_target_ref") if value is not None else None

    @field_validator("assertion_refs", mode="before")
    @classmethod
    def normalize_assertions(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "assertion_refs", limit=MAX_CANDIDATES)

    @field_validator("eligible_families")
    @classmethod
    def normalize_families(cls, value: tuple[AssertionFamilyV1Alpha1, ...]) -> tuple[AssertionFamilyV1Alpha1, ...]:
        if len(value) != len(set(value)):
            raise ValueError("eligible_families must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("requested_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "requested_at")

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (
            self.authenticated_context.product_id != self.scope.product_id
            or self.authenticated_context.actor_ref != self.scope.actor_id
            or self.receiver.product_id != self.scope.product_id
        ):
            raise ValueError("recall request crossed authenticated receiver scope")
        if self.structured_question is not StructuredQuestionKind.NONE and self.semantic_target_ref is None:
            raise ValueError("structured lookup requires an exact semantic target")
        return self


class RetrievalStateSnapshotV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_retrieval_snapshot"
    contract: Literal["ace.intelligence.memory-retrieval-snapshot/v1alpha1"] = RETRIEVAL_SNAPSHOT_VERSION
    policy_ref: str
    policy_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    index_refs: tuple[str, ...]
    projection_ref: str
    projection_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    canonical_head_refs: tuple[str, ...]
    cache_dependency_refs: tuple[str, ...] = ()
    captured_at: datetime

    @field_validator("policy_ref", "projection_ref")
    @classmethod
    def single_refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("index_refs", "canonical_head_refs", "cache_dependency_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, required=info.field_name != "cache_dependency_refs")

    @field_validator("captured_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "captured_at")


class FusedRankPolicyV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_fused_rank_policy"
    contract: Literal["ace.intelligence.memory-fused-rank-policy/v1alpha1"] = RETRIEVAL_POLICY_VERSION
    policy_ref: str
    policy_version: str
    signal_weights: dict[RetrievalSignal, float]
    deterministic_tie_break: Literal["aggregate_desc_candidate_ref_asc"] = "aggregate_desc_candidate_ref_asc"
    max_candidates: int = Field(default=200, ge=1, le=MAX_CANDIDATES)
    max_selected: int = Field(default=16, ge=1, le=MAX_BLOCKS)
    max_graph_depth: int = Field(default=2, ge=0, le=4)
    max_graph_nodes: int = Field(default=64, ge=1, le=256)
    max_context_tokens: int = Field(default=4_096, ge=1, le=64_000)
    max_context_bytes: int = Field(default=32_000, ge=1, le=1_000_000)
    minimum_score: float = Field(default=0.0, ge=-1, le=1)

    @field_validator("policy_ref")
    @classmethod
    def policy(cls, value: str) -> str:
        return _ref(value, "policy_ref")

    @model_validator(mode="after")
    def weights(self) -> Self:
        required = {
            RetrievalSignal.LEXICAL,
            RetrievalSignal.VECTOR,
            RetrievalSignal.EXACT_ENTITY,
            RetrievalSignal.TEMPORAL,
            RetrievalSignal.GRAPH,
            RetrievalSignal.SOURCE_DIVERSITY,
            RetrievalSignal.GOVERNED_RELIABILITY,
            RetrievalSignal.LIFECYCLE_PRIORITY,
        }
        if not required <= set(self.signal_weights):
            raise ValueError("fused policy must name every mandatory AM3 signal")
        if len(self.signal_weights) > MAX_SIGNALS or any(
            value < 0 or value > 1 for value in self.signal_weights.values()
        ):
            raise ValueError("signal weights must be bounded")
        if not any(self.signal_weights.values()):
            raise ValueError("fused policy requires a positive signal weight")
        return self


class RetrievalTelemetryV1Alpha1(_StrictFrozen):
    latency_ms: int | None = Field(default=None, ge=0)
    calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)
    unknown_fields: tuple[str, ...] = ()

    @field_validator("unknown_fields", mode="before")
    @classmethod
    def unknown(cls, value: Any) -> tuple[str, ...]:
        return _strings(value, "unknown_fields", limit=5)

    @model_validator(mode="after")
    def complete_accounting(self) -> Self:
        values = {
            "latency_ms": self.latency_ms,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_microunits": self.cost_microunits,
        }
        unknown = set(self.unknown_fields)
        if unknown - set(values):
            raise ValueError("unknown telemetry fields must name exact supported metrics")
        if any((value is None) == (name not in unknown) for name, value in values.items()):
            raise ValueError("every telemetry field must be measured or explicitly unknown")
        return self


class CandidateSignalScoreV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_signal_score"
    contract: Literal["ace.intelligence.memory-signal-score/v1alpha1"] = SIGNAL_SCORE_VERSION
    candidate_ref: str
    signal: RetrievalSignal
    available: bool
    score: float | None = Field(default=None, ge=-1, le=1)
    snapshot_ref: str | None = None
    authorization_receipt_ref: str
    unavailable_reason: str | None = Field(default=None, min_length=1, max_length=240)
    telemetry: RetrievalTelemetryV1Alpha1

    @field_validator("candidate_ref", "snapshot_ref", "authorization_receipt_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return _ref(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def availability(self) -> Self:
        if self.available:
            if self.score is None or self.snapshot_ref is None or self.unavailable_reason is not None:
                raise ValueError("available signal requires score and snapshot only")
        elif self.score is not None or self.snapshot_ref is not None or self.unavailable_reason is None:
            raise ValueError("unavailable signal requires only an explicit reason")
        return self


class AuthorizedCandidateEvidenceV1Alpha1(_ContentAddressed):
    """Bounded content-free candidate and omission evidence."""

    identity_prefix = "memory_authorized_candidate"
    contract: Literal["ace.intelligence.memory-authorized-candidate/v1alpha1"] = CANDIDATE_EVIDENCE_VERSION
    candidate_ref: str
    candidate_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_id: str
    source_version_id: str
    semantic_target_ref: str
    family: AssertionFamilyV1Alpha1
    lifecycle: AssertionLifecycle
    signal_scores: tuple[CandidateSignalScoreV1Alpha1, ...]
    aggregate_score: float = Field(ge=-1, le=1)
    selected: bool
    omission_reason: str | None = Field(default=None, min_length=1, max_length=240)
    rank: int | None = Field(default=None, ge=1, le=MAX_CANDIDATES)

    @field_validator("candidate_ref", "source_id", "source_version_id", "semantic_target_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @model_validator(mode="after")
    def disposition(self) -> Self:
        signals = [item.signal for item in self.signal_scores]
        if not signals or len(signals) != len(set(signals)) or len(signals) > MAX_SIGNALS:
            raise ValueError("candidate signal evidence must be bounded and unique")
        if tuple(signals) != tuple(sorted(signals)):
            raise ValueError("candidate signal evidence must use deterministic signal order")
        if self.selected != (self.omission_reason is None and self.rank is not None):
            raise ValueError("selected candidates require rank; omissions require a reason")
        return self


class RecallReceiptV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_recall_receipt"
    contract: Literal["ace.intelligence.memory-recall-receipt/v1alpha1"] = RECALL_RECEIPT_VERSION
    request_ref: str
    request_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    receiver_ref: str
    policy_ref: str
    policy_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    snapshot: RetrievalStateSnapshotV1Alpha1
    route: tuple[RetrievalTier, ...]
    candidates: tuple[AuthorizedCandidateEvidenceV1Alpha1, ...]
    selected_refs: tuple[str, ...]
    omitted_refs: tuple[str, ...]
    degraded_reasons: tuple[str, ...] = ()
    budget_exhausted: bool = False
    generated_at: datetime

    @field_validator("request_ref", "receiver_ref", "policy_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("selected_refs", "omitted_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, limit=MAX_CANDIDATES)

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def reasons(cls, value: Any) -> tuple[str, ...]:
        return _strings(value, "degraded_reasons")

    @field_validator("generated_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "generated_at")

    @model_validator(mode="after")
    def exact_candidates(self) -> Self:
        refs = [item.candidate_ref for item in self.candidates]
        if len(refs) != len(set(refs)) or len(refs) > MAX_CANDIDATES:
            raise ValueError("recall candidates must be bounded and unique")
        selected = {item.candidate_ref for item in self.candidates if item.selected}
        omitted = {item.candidate_ref for item in self.candidates if not item.selected}
        if selected != set(self.selected_refs) or omitted != set(self.omitted_refs):
            raise ValueError("recall receipt disposition does not bind exact candidate evidence")
        if not self.route:
            raise ValueError("recall route must name at least one progressive-resolution tier")
        return self


class InstructionPolicyResolutionRequestV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_instruction_request"
    contract: Literal["ace.intelligence.memory-instruction-policy-request/v1alpha1"] = INSTRUCTION_REQUEST_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    scope: AgentMemoryScopeV1Alpha1
    receiver: ReceivingCoordinatesV1Alpha1
    admitted_policy_refs: tuple[str, ...]
    instruction_channel_ref: str
    requested_at: datetime

    @field_validator("admitted_policy_refs", mode="before")
    @classmethod
    def policies(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "admitted_policy_refs", limit=64)

    @field_validator("instruction_channel_ref")
    @classmethod
    def channel(cls, value: str) -> str:
        return _ref(value, "instruction_channel_ref")

    @field_validator("requested_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "requested_at")

    @model_validator(mode="after")
    def scope_match(self) -> Self:
        if (
            self.authenticated_context.product_id != self.scope.product_id
            or self.authenticated_context.actor_ref != self.scope.actor_id
            or self.receiver.product_id != self.scope.product_id
        ):
            raise ValueError("instruction request crossed authenticated receiver scope")
        return self


class InstructionPolicyResolutionReceiptV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_instruction_resolution"
    contract: Literal["ace.intelligence.memory-instruction-policy-resolution/v1alpha1"] = INSTRUCTION_RECEIPT_VERSION
    request_ref: str
    instruction_channel_ref: str
    authorization_receipt_ref: str
    resolved_policy_refs: tuple[str, ...]
    omitted_policy_refs: tuple[str, ...] = ()
    current_head_refs: tuple[str, ...]
    blocked: bool
    degraded_reasons: tuple[str, ...] = ()
    resolved_at: datetime

    @field_validator("request_ref", "instruction_channel_ref", "authorization_receipt_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("resolved_policy_refs", "omitted_policy_refs", "current_head_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, required=info.field_name == "current_head_refs", limit=64)

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def reasons(cls, value: Any) -> tuple[str, ...]:
        return _strings(value, "degraded_reasons")

    @field_validator("resolved_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "resolved_at")

    @model_validator(mode="after")
    def disjoint(self) -> Self:
        if set(self.resolved_policy_refs) & set(self.omitted_policy_refs):
            raise ValueError("instruction policies cannot be both resolved and omitted")
        if self.blocked and self.resolved_policy_refs:
            raise ValueError("blocked instruction resolution cannot supply policy")
        return self


class ContextPlannerBudgetV1Alpha1(_StrictFrozen):
    max_candidates: int = Field(ge=1, le=MAX_CANDIDATES)
    max_blocks: int = Field(ge=1, le=MAX_BLOCKS)
    max_tokens: int = Field(ge=1, le=64_000)
    max_bytes: int = Field(ge=1, le=1_000_000)
    max_latency_ms: int = Field(ge=1, le=600_000)
    max_calls: int = Field(ge=0, le=1_000)


class ContextPlannerRequestV1Alpha1(_ContentAddressed):
    identity_prefix = "context_planner_request"
    contract: Literal["ace.intelligence.context-planner-request/v1alpha1"] = CONTEXT_PLANNER_REQUEST_VERSION
    recall_request: AuthenticatedRecallRequestV1Alpha1
    instruction_request: InstructionPolicyResolutionRequestV1Alpha1
    expected_snapshot: RetrievalStateSnapshotV1Alpha1
    policy: FusedRankPolicyV1Alpha1
    budget: ContextPlannerBudgetV1Alpha1
    activated_constraints: ActivatedMemoryConstraintsV1Alpha1

    @model_validator(mode="after")
    def bind_exact_channels(self) -> Self:
        if self.recall_request.receiver != self.instruction_request.receiver:
            raise ValueError("relevance and instruction channels must target the exact same receiver")
        if self.policy.policy_ref != self.expected_snapshot.policy_ref:
            raise ValueError("planner policy differs from expected retrieval snapshot")
        if self.policy.artifact_digest != self.expected_snapshot.policy_digest:
            raise ValueError("planner policy digest differs from expected retrieval snapshot")
        return self


class ContextBlockEvidenceV1Alpha1(_ContentAddressed):
    """Content-free public evidence for a privately assembled context body."""

    identity_prefix = "context_block"
    contract: Literal["ace.intelligence.memory-context-block/v1alpha1"] = (
        "ace.intelligence.memory-context-block/v1alpha1"
    )
    kind: ContextBlockKind
    candidate_ref: str | None = None
    instruction_policy_ref: str | None = None
    source_id: str
    source_version_id: str
    source_span_ref: str
    lifecycle: str
    uncertainty_ref: str | None = None
    freshness_signal_ref: str | None = None
    body_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    token_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)
    receiving_stage_ref: str
    authorization_receipt_ref: str

    @field_validator(
        "candidate_ref",
        "instruction_policy_ref",
        "source_id",
        "source_version_id",
        "source_span_ref",
        "uncertainty_ref",
        "freshness_signal_ref",
        "receiving_stage_ref",
        "authorization_receipt_ref",
    )
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return _ref(value, info.field_name) if value is not None else None

    @model_validator(mode="after")
    def exact_channel(self) -> Self:
        if (self.kind is ContextBlockKind.INSTRUCTION) != (self.instruction_policy_ref is not None):
            raise ValueError("instruction blocks require only the separately resolved policy coordinate")
        if self.kind is not ContextBlockKind.INSTRUCTION and self.candidate_ref is None:
            raise ValueError("ordinary context blocks require an authorized candidate coordinate")
        return self


class CanonicalContextManifestV1(_ContentAddressed):
    identity_prefix = "context_manifest"
    contract: Literal["ace.context.manifest/v1"] = CONTEXT_MANIFEST_VERSION
    planner_request_ref: str
    receiver: ReceivingCoordinatesV1Alpha1
    recall_receipt_ref: str
    instruction_resolution_ref: str
    snapshot_ref: str
    selected_candidate_refs: tuple[str, ...]
    omitted_candidate_refs: tuple[str, ...]
    blocks: tuple[ContextBlockEvidenceV1Alpha1, ...]
    total_tokens: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    omissions: tuple[str, ...] = ()
    degraded_reasons: tuple[str, ...] = ()
    generated_at: datetime
    execution_authority: Literal[False] = False

    @field_validator("planner_request_ref", "recall_receipt_ref", "instruction_resolution_ref", "snapshot_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("selected_candidate_refs", "omitted_candidate_refs", mode="before")
    @classmethod
    def candidate_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, limit=MAX_CANDIDATES)

    @field_validator("omissions", "degraded_reasons", mode="before")
    @classmethod
    def reasons(cls, value: Any, info) -> tuple[str, ...]:
        return _strings(value, info.field_name)

    @field_validator("generated_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "generated_at")

    @model_validator(mode="after")
    def bounded_manifest(self) -> Self:
        if len(self.blocks) > MAX_BLOCKS:
            raise ValueError("context manifest exceeds bounded blocks")
        ids = [item.artifact_id for item in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("context manifest blocks must be unique")
        if set(self.selected_candidate_refs) & set(self.omitted_candidate_refs):
            raise ValueError("manifest candidate selection and omission must be disjoint")
        if self.total_tokens != sum(item.token_count for item in self.blocks):
            raise ValueError("manifest token total differs from exact blocks")
        if self.total_bytes != sum(item.byte_count for item in self.blocks):
            raise ValueError("manifest byte total differs from exact blocks")
        return self


class ContextPlannerResultV1Alpha1(_ContentAddressed):
    identity_prefix = "context_planner_result"
    contract: Literal["ace.intelligence.context-planner-result/v1alpha1"] = CONTEXT_PLANNER_RESULT_VERSION
    planner_request_ref: str
    recall_receipt_ref: str
    instruction_resolution_ref: str
    manifest_ref: str
    manifest_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    stopped_at_tier: RetrievalTier
    degraded_reasons: tuple[str, ...] = ()
    generated_at: datetime

    @field_validator("planner_request_ref", "recall_receipt_ref", "instruction_resolution_ref", "manifest_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def reasons(cls, value: Any) -> tuple[str, ...]:
        return _strings(value, "degraded_reasons")

    @field_validator("generated_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "generated_at")


class QueryAidReceiptV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_query_aid"
    contract: Literal["ace.intelligence.memory-query-aid-receipt/v1alpha1"] = QUERY_AID_VERSION
    request_ref: str
    aid_kind: Literal["query_expansion", "compact_synthesis"]
    input_refs: tuple[str, ...]
    output_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    provider_ref: str | None = None
    authority_granted: Literal[False] = False
    identities_minted: Literal[False] = False
    generated_at: datetime

    @field_validator("request_ref", "provider_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return _ref(value, info.field_name) if value is not None else None

    @field_validator("input_refs", mode="before")
    @classmethod
    def inputs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "input_refs", required=True)

    @field_validator("generated_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "generated_at")


class _UseEvidence(_ContentAddressed):
    manifest_ref: str
    receiver_ref: str
    candidate_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    observed_at: datetime

    @field_validator("manifest_ref", "receiver_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("candidate_refs", "evidence_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, required=info.field_name == "evidence_refs", limit=MAX_CANDIDATES)

    @field_validator("observed_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "observed_at")


class ContextInjectionReceiptV1Alpha1(_UseEvidence):
    identity_prefix = "context_injection_receipt"
    contract: Literal["ace.intelligence.memory-context-injection-receipt/v1alpha1"] = CONTEXT_INJECTION_VERSION


class ContextReflectionReceiptV1Alpha1(_UseEvidence):
    identity_prefix = "context_reflection_receipt"
    contract: Literal["ace.intelligence.memory-context-reflection-receipt/v1alpha1"] = CONTEXT_REFLECTION_VERSION
    reflection_method: Literal["bounded_attribution", "structured_field_attribution", "declared_field_attribution"]


class DecisionMaterialReceiptV1Alpha1(_UseEvidence):
    identity_prefix = "decision_material_receipt"
    contract: Literal["ace.intelligence.memory-decision-material-receipt/v1alpha1"] = DECISION_MATERIAL_VERSION
    comparison_ref: str
    changed_fields: tuple[str, ...]
    benefit: Literal["unknown"] = "unknown"

    @field_validator("comparison_ref")
    @classmethod
    def comparison(cls, value: str) -> str:
        return _ref(value, "comparison_ref")

    @field_validator("changed_fields", mode="before")
    @classmethod
    def fields(cls, value: Any) -> tuple[str, ...]:
        return _strings(value, "changed_fields", limit=64)

    @model_validator(mode="after")
    def material_delta(self) -> Self:
        if not self.candidate_refs or not self.changed_fields:
            raise ValueError("decision-material evidence requires candidates and a bounded field delta")
        return self


class ContextUseReceiptV1Alpha1(_ContentAddressed):
    identity_prefix = "context_use_receipt"
    contract: Literal["ace.intelligence.memory-context-use-receipt/v1alpha1"] = CONTEXT_USE_VERSION
    manifest_ref: str
    receiver_ref: str
    selected_candidate_refs: tuple[str, ...]
    injected_candidate_refs: tuple[str, ...]
    reflected_candidate_refs: tuple[str, ...]
    decision_material_candidate_refs: tuple[str, ...]
    injection_receipt_ref: str | None = None
    reflection_receipt_ref: str | None = None
    decision_material_receipt_ref: str | None = None
    intelligence_use_receipt_ref: str | None = None
    recorded_at: datetime
    benefit: Literal["unknown"] = "unknown"

    @field_validator(
        "manifest_ref",
        "receiver_ref",
        "injection_receipt_ref",
        "reflection_receipt_ref",
        "decision_material_receipt_ref",
        "intelligence_use_receipt_ref",
    )
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return _ref(value, info.field_name) if value is not None else None

    @field_validator(
        "selected_candidate_refs",
        "injected_candidate_refs",
        "reflected_candidate_refs",
        "decision_material_candidate_refs",
        mode="before",
    )
    @classmethod
    def candidate_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, info.field_name, limit=MAX_CANDIDATES)

    @field_validator("recorded_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "recorded_at")

    @model_validator(mode="after")
    def monotonic_use(self) -> Self:
        selected = set(self.selected_candidate_refs)
        injected = set(self.injected_candidate_refs)
        reflected = set(self.reflected_candidate_refs)
        material = set(self.decision_material_candidate_refs)
        if not material <= reflected <= injected <= selected:
            raise ValueError("context use must progress selected → injected → reflected → decision-material")
        if bool(injected) != (self.injection_receipt_ref is not None):
            raise ValueError("injection evidence must be explicit")
        if bool(reflected) != (self.reflection_receipt_ref is not None):
            raise ValueError("reflection evidence must be explicit")
        if bool(material) != (
            self.decision_material_receipt_ref is not None and self.intelligence_use_receipt_ref is not None
        ):
            raise ValueError("decision-material evidence requires exact comparison and I3 receipts")
        return self


class MatchedConditionAssignmentV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_condition_assignment"
    contract: Literal["ace.intelligence.memory-condition-assignment/v1alpha1"] = CONDITION_ASSIGNMENT_VERSION
    comparison_group_ref: str
    condition: ConditionKind
    invocation_ref: str
    task_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    prompt_contract_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    provider_ref: str
    model_ref: str
    configuration_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    decision_schema_ref: str
    toolset_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    manifest_ref: str | None = None
    assigned_at: datetime

    @field_validator(
        "comparison_group_ref", "invocation_ref", "provider_ref", "model_ref", "decision_schema_ref", "manifest_ref"
    )
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return _ref(value, info.field_name) if value is not None else None

    @field_validator("assigned_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "assigned_at")

    @model_validator(mode="after")
    def condition_manifest(self) -> Self:
        if (self.condition is ConditionKind.MEMORY) != (self.manifest_ref is not None):
            raise ValueError("only the memory condition may bind a Context Manifest")
        return self


class MaterialityComparisonV1Alpha1(_ContentAddressed):
    identity_prefix = "memory_materiality_comparison"
    contract: Literal["ace.intelligence.memory-materiality-comparison/v1alpha1"] = MATERIALITY_COMPARISON_VERSION
    comparison_group_ref: str
    memory_assignment_ref: str
    no_memory_assignment_ref: str
    target_candidate_refs: tuple[str, ...]
    held_constant_fields: tuple[str, ...]
    changed_fields: tuple[str, ...]
    memory_output_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    no_memory_output_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    material_influence: bool
    benefit: Literal["unknown"] = "unknown"
    compared_at: datetime

    @field_validator("comparison_group_ref", "memory_assignment_ref", "no_memory_assignment_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return _ref(value, info.field_name)

    @field_validator("target_candidate_refs", mode="before")
    @classmethod
    def targets(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, "target_candidate_refs", limit=MAX_CANDIDATES)

    @field_validator("held_constant_fields", "changed_fields", mode="before")
    @classmethod
    def fields(cls, value: Any, info) -> tuple[str, ...]:
        return _strings(value, info.field_name, limit=64)

    @field_validator("compared_at")
    @classmethod
    def time(cls, value: datetime) -> datetime:
        return _aware(value, "compared_at")

    @model_validator(mode="after")
    def exact_materiality(self) -> Self:
        expected = bool(self.changed_fields and self.memory_output_digest != self.no_memory_output_digest)
        if self.material_influence != expected:
            raise ValueError("material influence must equal the bounded matched output delta")
        if self.material_influence and not self.target_candidate_refs:
            raise ValueError("material influence requires exact target candidates")
        return self


__all__ = [
    "CANDIDATE_EVIDENCE_VERSION",
    "CONDITION_ASSIGNMENT_VERSION",
    "CONTEXT_INJECTION_VERSION",
    "CONTEXT_MANIFEST_VERSION",
    "CONTEXT_PLANNER_REQUEST_VERSION",
    "CONTEXT_PLANNER_RESULT_VERSION",
    "CONTEXT_REFLECTION_VERSION",
    "CONTEXT_USE_VERSION",
    "DECISION_MATERIAL_VERSION",
    "INSTRUCTION_RECEIPT_VERSION",
    "INSTRUCTION_REQUEST_VERSION",
    "MATERIALITY_COMPARISON_VERSION",
    "QUERY_AID_VERSION",
    "RECALL_RECEIPT_VERSION",
    "RECALL_REQUEST_VERSION",
    "RECEIVING_COORDINATES_VERSION",
    "RETRIEVAL_POLICY_VERSION",
    "RETRIEVAL_SNAPSHOT_VERSION",
    "SIGNAL_SCORE_VERSION",
    "AuthenticatedRecallRequestV1Alpha1",
    "AuthorizedCandidateEvidenceV1Alpha1",
    "CandidateSignalScoreV1Alpha1",
    "CanonicalContextManifestV1",
    "ConditionKind",
    "ContextBlockEvidenceV1Alpha1",
    "ContextBlockKind",
    "ContextInjectionReceiptV1Alpha1",
    "ContextPlannerBudgetV1Alpha1",
    "ContextPlannerRequestV1Alpha1",
    "ContextPlannerResultV1Alpha1",
    "ContextReflectionReceiptV1Alpha1",
    "ContextUseReceiptV1Alpha1",
    "DecisionMaterialReceiptV1Alpha1",
    "EvidenceState",
    "FusedRankPolicyV1Alpha1",
    "InstructionPolicyResolutionReceiptV1Alpha1",
    "InstructionPolicyResolutionRequestV1Alpha1",
    "MatchedConditionAssignmentV1Alpha1",
    "MaterialityComparisonV1Alpha1",
    "QueryAidReceiptV1Alpha1",
    "RecallReceiptV1Alpha1",
    "ReceivingCoordinatesV1Alpha1",
    "RetrievalSignal",
    "RetrievalStateSnapshotV1Alpha1",
    "RetrievalTelemetryV1Alpha1",
    "RetrievalTier",
    "StructuredQuestionKind",
]
