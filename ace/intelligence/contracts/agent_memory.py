"""Intelligence-owned Agent Memory families and reconciliation proposals.

Source capture, scope, time, and lifecycle remain Core mechanics. This module
adds semantic family and epistemic meaning without granting a model, telemetry,
or repeated material authority to promote itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, Self, runtime_checkable

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    SourceProvenanceV1Alpha1,
    TemporalQueryV1Alpha1,
    WorldTimeV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash, stable_id
from ace.core.records import AppendOnlyTransactionReceiptV1, AppendOnlyTransactionRequestV1
from ace.core.state import ResolvedApprovalReceiptV1, ResolvedAuthorityGrantV1
from ace.intelligence.contracts.common import parse_json_strict, validate_reference

MEMORY_ASSERTION_VERSION = "ace.intelligence.memory-assertion/v1alpha1"
RECONCILIATION_PROPOSAL_VERSION = "ace.intelligence.memory-reconciliation-proposal/v1alpha1"
EVOLUTION_PROPOSAL_VERSION = "ace.intelligence.memory-evolution-proposal/v1alpha1"
MEMORY_QUERY_VERSION = "ace.intelligence.agent-memory-query/v1alpha1"
CANDIDATE_RECEIPT_VERSION = "ace.intelligence.memory-candidate-receipt/v1alpha1"
MEMORY_CONTEXT_LINEAGE_VERSION = "ace.intelligence.memory-context-lineage/v1alpha1"

MAX_PROVENANCE = 64
MAX_REFS = 256
MAX_CANDIDATES = 200


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


def _refs(value: Any, *, name: str, maximum: int = MAX_REFS) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain stable references")
    refs = tuple(sorted(set(value)))
    if len(refs) > maximum:
        raise ValueError(f"{name} exceeds the {maximum}-item bound")
    for ref in refs:
        validate_reference(ref, name=name)
    return refs


class MemorySemanticFamily(StrEnum):
    EPISODIC_EXPERIENCE = "episodic_experience"
    IDENTITY_ASSERTION = "identity_assertion"
    LEARNED_FACT = "learned_fact"
    ACTIVE_CONTEXT = "active_context"
    PREFERENCE = "preference"
    INSTRUCTION_POLICY = "instruction_policy"
    UNCERTAINTY = "uncertainty"
    CORRECTION = "correction"
    DURABLE_COGNITIVE_MEMORY = "durable_cognitive_memory"


class MemoryEpistemicState(StrEnum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class AssertionOriginKind(StrEnum):
    USER = "user"
    SYSTEM_POLICY = "system_policy"
    PRODUCT_OPERATOR = "product_operator"
    MODEL_PROPOSAL = "model_proposal"
    EXTERNAL_SOURCE = "external_source"
    TELEMETRY = "telemetry"


class MemoryEvolutionKind(StrEnum):
    ELABORATION = "elaboration"
    CONSOLIDATION = "consolidation"
    REFLECTION = "reflection"
    RANK_POLICY = "rank_policy"
    RELIABILITY_POLICY = "reliability_policy"
    LIFECYCLE_POLICY = "lifecycle_policy"


class AssertionAuthorityV1Alpha1(_StrictFrozenContract):
    """Origin is evidence; resolved approval and authority are separate."""

    origin_kind: AssertionOriginKind
    actor_ref: str
    resolved_grant: ResolvedAuthorityGrantV1 | None = None
    resolved_approval: ResolvedApprovalReceiptV1 | None = None

    @field_validator("actor_ref")
    @classmethod
    def validate_actor_ref(cls, value: str) -> str:
        return validate_reference(value, name="actor_ref")


class AgentMemoryQueryV1Alpha1(_StrictFrozenContract):
    """Intelligence-owned semantic recall request over a Core-authenticated scope."""

    contract: Literal["ace.intelligence.agent-memory-query/v1alpha1"] = MEMORY_QUERY_VERSION
    scope: AgentMemoryScopeV1Alpha1
    query_digest: str
    temporal: TemporalQueryV1Alpha1 = Field(default_factory=TemporalQueryV1Alpha1)
    eligible_families: tuple[MemorySemanticFamily, ...]
    eligible_states: tuple[MemoryEpistemicState, ...]
    receiver_ref: str
    policy_ref: str
    limit: int = Field(default=50, ge=1, le=MAX_CANDIDATES)
    query_id: str | None = None

    @field_validator("query_digest")
    @classmethod
    def validate_query_digest(cls, value: str) -> str:
        if len(value) != 71 or not value.startswith("sha256:"):
            raise ValueError("query_digest must use lowercase sha256:<64-hex> syntax")
        try:
            int(value[7:], 16)
        except ValueError as exc:
            raise ValueError("query_digest must use lowercase sha256:<64-hex> syntax") from exc
        if value != value.lower():
            raise ValueError("query_digest must use lowercase sha256:<64-hex> syntax")
        return value

    @field_validator("eligible_families", "eligible_states", mode="after")
    @classmethod
    def normalize_eligibility(cls, value: tuple[Any, ...], info) -> tuple[Any, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be non-empty and unique")
        return tuple(sorted(value, key=lambda item: item.value))

    @field_validator("receiver_ref", "policy_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_query_id(self) -> Self:
        material = self.model_dump(mode="json", exclude={"query_id"})
        expected = stable_id("agent_memory_query", material)
        if self.query_id is not None and self.query_id != expected:
            raise ValueError("query_id does not match exact semantic query material")
        object.__setattr__(self, "query_id", expected)
        return self


class CandidateSignalContributionV1Alpha1(_StrictFrozenContract):
    signal_ref: str
    available: bool
    score: float | None = Field(default=None, ge=-1, le=1)
    detail_ref: str | None = None

    @field_validator("signal_ref", "detail_ref")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available != (self.score is not None):
            raise ValueError("available ranking signals require a score and unavailable signals forbid one")
        return self


class CandidateRecordV1Alpha1(_StrictFrozenContract):
    assertion_ref: str
    family: MemorySemanticFamily
    epistemic_state: MemoryEpistemicState
    source_id: str
    source_version_id: str
    selected: bool
    aggregate_score: float | None = Field(default=None, ge=-1, le=1)
    signals: tuple[CandidateSignalContributionV1Alpha1, ...] = ()
    omission_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("assertion_ref", "source_id", "source_version_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        signal_refs = [item.signal_ref for item in self.signals]
        if len(signal_refs) != len(set(signal_refs)):
            raise ValueError("candidate ranking signals must be unique")
        object.__setattr__(self, "signals", tuple(sorted(self.signals, key=lambda item: item.signal_ref)))
        if self.selected and self.omission_reason is not None:
            raise ValueError("selected candidates cannot have an omission reason")
        if not self.selected and self.omission_reason is None:
            raise ValueError("omitted candidates require an omission reason")
        return self


class CandidateReceiptV1Alpha1(_StrictFrozenContract):
    """Inspectable authorized retrieval evidence; it does not prove later use."""

    contract: Literal["ace.intelligence.memory-candidate-receipt/v1alpha1"] = CANDIDATE_RECEIPT_VERSION
    query_id: str
    scope_id: str
    policy_ref: str
    authorization_filter_receipt_ref: str
    lifecycle_snapshot_ref: str
    index_snapshot_refs: tuple[str, ...] = ()
    candidates: tuple[CandidateRecordV1Alpha1, ...] = ()
    degraded_reasons: tuple[str, ...] = ()
    generated_at: datetime
    receipt_id: str | None = None

    @field_validator(
        "query_id",
        "scope_id",
        "policy_ref",
        "authorization_filter_receipt_ref",
        "lifecycle_snapshot_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("index_snapshot_refs", mode="before")
    @classmethod
    def normalize_index_refs(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, name="index_snapshot_refs")

    @field_validator("degraded_reasons", mode="before")
    @classmethod
    def normalize_degraded_reasons(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("degraded_reasons must be a collection")
        reasons = tuple(sorted(set(value)))
        if len(reasons) > 32 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 500 for item in reasons
        ):
            raise ValueError("degraded_reasons must contain bounded non-empty strings")
        return reasons

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        refs = [item.assertion_ref for item in self.candidates]
        if len(self.candidates) > MAX_CANDIDATES or len(refs) != len(set(refs)):
            raise ValueError("candidate receipt must contain bounded unique assertions")
        object.__setattr__(self, "candidates", tuple(sorted(self.candidates, key=lambda item: item.assertion_ref)))
        material = self.model_dump(mode="json", exclude={"receipt_id"})
        expected = stable_id("memory_candidate_receipt", material)
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("receipt_id does not match exact candidate material")
        object.__setattr__(self, "receipt_id", expected)
        return self


class MemoryContextLineageV1Alpha1(_StrictFrozenContract):
    """References Context Manifest and I3 evidence without duplicating either receipt family."""

    contract: Literal["ace.intelligence.memory-context-lineage/v1alpha1"] = MEMORY_CONTEXT_LINEAGE_VERSION
    scope: AgentMemoryScopeV1Alpha1
    candidate_receipt_id: str
    assertion_ref: str
    context_manifest_contract: Literal["ace.context.manifest/v1"] = "ace.context.manifest/v1"
    context_manifest_id: str
    context_item_ref: str
    context_item_source_receipt_ref: str
    intelligence_use_contract: Literal["intelligence-use-receipt-v1"] = "intelligence-use-receipt-v1"
    intelligence_use_receipt_ref: str | None = None
    decision_ref: str | None = None
    recorded_at: datetime
    lineage_id: str | None = None

    @field_validator(
        "candidate_receipt_id",
        "assertion_ref",
        "context_manifest_id",
        "context_item_ref",
        "context_item_source_receipt_ref",
        "intelligence_use_receipt_ref",
        "decision_ref",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return _aware(value, name="recorded_at")

    @model_validator(mode="after")
    def validate_lineage(self) -> Self:
        if self.decision_ref is not None and self.intelligence_use_receipt_ref is None:
            raise ValueError("decision lineage requires an exact I3 intelligence-use receipt")
        material = self.model_dump(mode="json", exclude={"lineage_id"})
        expected = stable_id("memory_context_lineage", material)
        if self.lineage_id is not None and self.lineage_id != expected:
            raise ValueError("lineage_id does not match exact manifest and I3 references")
        object.__setattr__(self, "lineage_id", expected)
        return self


class MemoryAssertionV1Alpha1(_StrictFrozenContract):
    """A source-grounded assertion whose state never follows from capture alone."""

    contract: Literal["ace.intelligence.memory-assertion/v1alpha1"] = MEMORY_ASSERTION_VERSION
    scope: AgentMemoryScopeV1Alpha1
    family: MemorySemanticFamily
    statement: str = Field(min_length=1, max_length=8_000)
    payload_json: str = Field(default="{}", min_length=2, max_length=32_000)
    provenance: tuple[SourceProvenanceV1Alpha1, ...]
    authority: AssertionAuthorityV1Alpha1
    epistemic_state: MemoryEpistemicState
    knowledge_time: KnowledgeTimeV1Alpha1
    world_time: WorldTimeV1Alpha1
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_method_ref: str | None = None
    conflicts_with: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    reconciliation_decision_ref: str | None = None
    assertion_id: str | None = None
    assertion_digest: str | None = None

    @field_validator("payload_json")
    @classmethod
    def validate_payload_json(cls, value: str) -> str:
        parse_json_strict(value)
        return value

    @field_validator("confidence_method_ref", "reconciliation_decision_ref")
    @classmethod
    def validate_optional_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("conflicts_with", "supersedes", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_assertion(self) -> Self:
        if not self.provenance or len(self.provenance) > MAX_PROVENANCE:
            raise ValueError("memory assertions require bounded source provenance")
        provenance_keys = [(item.source_id, item.source_version_id, repr(item.span)) for item in self.provenance]
        if len(provenance_keys) != len(set(provenance_keys)):
            raise ValueError("memory assertion provenance must be unique")
        ordered = tuple(
            sorted(self.provenance, key=lambda item: (item.source_id, item.source_version_id, repr(item.span)))
        )
        object.__setattr__(self, "provenance", ordered)
        if self.scope.source_id is not None and any(item.source_id != self.scope.source_id for item in self.provenance):
            raise ValueError("assertion provenance must remain within authenticated source scope")
        if (self.confidence is None) != (self.confidence_method_ref is None):
            raise ValueError("confidence and confidence_method_ref must be supplied together")
        if self.epistemic_state is MemoryEpistemicState.UNKNOWN and self.confidence is not None:
            raise ValueError("unknown epistemic state cannot carry fabricated confidence")
        decided_states = {
            MemoryEpistemicState.ACCEPTED,
            MemoryEpistemicState.REJECTED,
            MemoryEpistemicState.SUPERSEDED,
        }
        if (self.epistemic_state in decided_states) != (self.reconciliation_decision_ref is not None):
            raise ValueError("decided epistemic states require exactly one reconciliation decision")
        if self.epistemic_state is MemoryEpistemicState.ACCEPTED:
            grant = self.authority.resolved_grant
            approval = self.authority.resolved_approval
            if grant is None or approval is None:
                raise ValueError("accepted memory requires resolved authority and approval")
            if grant.product_id != self.scope.product_id or approval.product_id != self.scope.product_id:
                raise ValueError("accepted memory authority must resolve in the exact product scope")
        if (
            self.authority.resolved_grant is not None
            and self.authority.resolved_grant.product_id != self.scope.product_id
        ):
            raise ValueError("authority grant must remain within authenticated product scope")
        if (
            self.authority.resolved_approval is not None
            and self.authority.resolved_approval.product_id != self.scope.product_id
        ):
            raise ValueError("approval must remain within authenticated product scope")
        material = self.model_dump(mode="json", exclude={"assertion_id", "assertion_digest"})
        digest = canonical_hash(material)
        expected_id = stable_id("memory_assertion", material)
        expected_digest = f"sha256:{digest}"
        if self.assertion_id is not None and self.assertion_id != expected_id:
            raise ValueError("assertion_id does not match exact assertion material")
        if self.assertion_digest is not None and self.assertion_digest != expected_digest:
            raise ValueError("assertion_digest does not match exact assertion material")
        object.__setattr__(self, "assertion_id", expected_id)
        object.__setattr__(self, "assertion_digest", expected_digest)
        if expected_id in self.conflicts_with or expected_id in self.supersedes:
            raise ValueError("memory assertions cannot conflict with or supersede themselves")
        return self


class ReconciliationProposalV1Alpha1(_StrictFrozenContract):
    """A reviewable proposal; it cannot activate its requested state itself."""

    contract: Literal["ace.intelligence.memory-reconciliation-proposal/v1alpha1"] = RECONCILIATION_PROPOSAL_VERSION
    scope: AgentMemoryScopeV1Alpha1
    assertion_refs: tuple[str, ...]
    requested_state: MemoryEpistemicState
    policy_ref: str
    policy_version: str
    evidence_refs: tuple[str, ...]
    conflict_refs: tuple[str, ...] = ()
    required_authority: str
    generated_by: AssertionOriginKind
    reason: str = Field(min_length=1, max_length=4_000)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("assertion_refs", "evidence_refs", "conflict_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name)

    @field_validator("policy_ref", "required_authority")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if not value or len(value) > 120 or value != value.strip():
            raise ValueError("policy_version must be bounded and explicit")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        if not self.assertion_refs or not self.evidence_refs:
            raise ValueError("reconciliation proposals require assertions and evidence")
        if self.requested_state in {MemoryEpistemicState.OBSERVED, MemoryEpistemicState.PROPOSED}:
            raise ValueError("reconciliation must request a reviewed epistemic disposition")
        material = self.model_dump(mode="json", exclude={"proposal_id", "proposal_digest"})
        digest = canonical_hash(material)
        expected_id = stable_id("memory_reconciliation_proposal", material)
        expected_digest = f"sha256:{digest}"
        if self.proposal_id is not None and self.proposal_id != expected_id:
            raise ValueError("proposal_id does not match exact proposal material")
        if self.proposal_digest is not None and self.proposal_digest != expected_digest:
            raise ValueError("proposal_digest does not match exact proposal material")
        object.__setattr__(self, "proposal_id", expected_id)
        object.__setattr__(self, "proposal_digest", expected_digest)
        return self


class MemoryEvolutionProposalV1Alpha1(_StrictFrozenContract):
    """Derived material proposed for review without activation authority."""

    contract: Literal["ace.intelligence.memory-evolution-proposal/v1alpha1"] = EVOLUTION_PROPOSAL_VERSION
    scope: AgentMemoryScopeV1Alpha1
    kind: MemoryEvolutionKind
    input_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    proposed_payload_contract: str
    proposed_payload_json: str = Field(min_length=2, max_length=32_000)
    policy_ref: str
    policy_version: str
    required_authority: str
    generated_by: AssertionOriginKind
    reason: str = Field(min_length=1, max_length=4_000)
    created_at: datetime
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("input_refs", "evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name)

    @field_validator("proposed_payload_contract", "policy_ref", "required_authority")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("proposed_payload_json")
    @classmethod
    def validate_payload_json(cls, value: str) -> str:
        parse_json_strict(value)
        return value

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if not value or len(value) > 120 or value != value.strip():
            raise ValueError("policy_version must be bounded and explicit")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, name="created_at")

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        if not self.input_refs or not self.evidence_refs:
            raise ValueError("evolution proposals require inputs and evidence")
        material = self.model_dump(mode="json", exclude={"proposal_id", "proposal_digest"})
        digest = canonical_hash(material)
        expected_id = stable_id("memory_evolution_proposal", material)
        expected_digest = f"sha256:{digest}"
        if self.proposal_id is not None and self.proposal_id != expected_id:
            raise ValueError("proposal_id does not match exact evolution material")
        if self.proposal_digest is not None and self.proposal_digest != expected_digest:
            raise ValueError("proposal_digest does not match exact evolution material")
        object.__setattr__(self, "proposal_id", expected_id)
        object.__setattr__(self, "proposal_digest", expected_digest)
        return self


@runtime_checkable
class MemoryReconciliationRepository(Protocol):
    """Persist and inspect proposals while Core retains opaque ledger authority."""

    async def load_assertions(
        self,
        assertion_refs: tuple[str, ...],
        *,
        scope: AgentMemoryScopeV1Alpha1,
        policy_ref: str,
    ) -> tuple[MemoryAssertionV1Alpha1, ...]: ...

    async def append_proposal(
        self,
        proposal: ReconciliationProposalV1Alpha1,
        *,
        transaction: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1: ...


@runtime_checkable
class MemoryGraphProjectionRepository(Protocol):
    """Rebuildable semantic projection; graph state never replaces ledger truth."""

    async def expand(
        self,
        request: AgentMemoryQueryV1Alpha1,
        *,
        seed_assertion_refs: tuple[str, ...],
        max_depth: int,
        max_nodes: int,
    ) -> CandidateReceiptV1Alpha1: ...

    async def rebuild(
        self,
        *,
        scope: AgentMemoryScopeV1Alpha1,
        through: LedgerCoordinateV1Alpha1,
    ) -> str: ...


@runtime_checkable
class MemoryQueryRepository(Protocol):
    """Authorized semantic candidate production; retrieval is not later use."""

    async def retrieve(self, request: AgentMemoryQueryV1Alpha1) -> CandidateReceiptV1Alpha1: ...


@runtime_checkable
class MemoryContextCompositionRepository(Protocol):
    """Compose through the existing Context Manifest and link its I3 evidence."""

    async def compose(
        self,
        *,
        request: AgentMemoryQueryV1Alpha1,
        candidates: CandidateReceiptV1Alpha1,
        context_manifest_id: str,
    ) -> tuple[MemoryContextLineageV1Alpha1, ...]: ...


__all__ = [
    "MEMORY_ASSERTION_VERSION",
    "RECONCILIATION_PROPOSAL_VERSION",
    "EVOLUTION_PROPOSAL_VERSION",
    "MEMORY_QUERY_VERSION",
    "CANDIDATE_RECEIPT_VERSION",
    "MEMORY_CONTEXT_LINEAGE_VERSION",
    "AgentMemoryQueryV1Alpha1",
    "AssertionAuthorityV1Alpha1",
    "AssertionOriginKind",
    "CandidateReceiptV1Alpha1",
    "CandidateRecordV1Alpha1",
    "CandidateSignalContributionV1Alpha1",
    "MemoryAssertionV1Alpha1",
    "MemoryEpistemicState",
    "MemoryEvolutionKind",
    "MemoryEvolutionProposalV1Alpha1",
    "MemoryContextLineageV1Alpha1",
    "MemoryContextCompositionRepository",
    "MemoryGraphProjectionRepository",
    "MemoryQueryRepository",
    "MemoryReconciliationRepository",
    "MemorySemanticFamily",
    "ReconciliationProposalV1Alpha1",
]
