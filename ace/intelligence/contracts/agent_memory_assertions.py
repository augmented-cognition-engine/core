"""AM2 typed assertion, reconciliation, temporal, and graph contracts.

These contracts keep extraction inert.  Source material, model output, repeated
claims, and reconciliation popularity cannot mint truth, lifecycle authority,
or instruction policy.  Core continues to own authenticated scope, immutable
records, commit time, and governed admission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_memory import (
    AgentMemoryScopeV1Alpha1,
    KnowledgeTimeV1Alpha1,
    LedgerCoordinateV1Alpha1,
    SourceSpanV1Alpha1,
    TemporalQueryV1Alpha1,
    WorldTimeV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash, stable_id
from ace.intelligence.contracts.common import validate_reference

ASSERTION_FAMILY_VERSION = "ace.intelligence.memory-assertion-family/v1alpha1"
SOURCE_ENVELOPE_VERSION = "ace.intelligence.memory-source-envelope/v1alpha1"
SEMANTIC_TARGET_VERSION = "ace.intelligence.memory-semantic-target/v1alpha1"
ASSERTION_CANDIDATE_VERSION = "ace.intelligence.memory-assertion-candidate/v1alpha1"
EXTRACTION_REQUEST_VERSION = "ace.intelligence.memory-extraction-request/v1alpha1"
EXTRACTION_RECEIPT_VERSION = "ace.intelligence.memory-extraction-receipt/v1alpha1"
RECONCILIATION_POLICY_VERSION = "ace.intelligence.memory-reconciliation-policy/v1alpha1"
RECONCILIATION_DECISION_VERSION = "ace.intelligence.memory-reconciliation-decision/v1alpha1"
RECONCILIATION_RECEIPT_VERSION = "ace.intelligence.memory-reconciliation-receipt/v1alpha1"
ASSERTION_QUERY_VERSION = "ace.intelligence.memory-assertion-query/v1alpha1"
ASSERTION_QUERY_RECEIPT_VERSION = "ace.intelligence.memory-assertion-query-receipt/v1alpha1"
GRAPH_PROJECTION_VERSION = "ace.intelligence.memory-graph-projection/v1alpha1"
GRAPH_QUERY_RECEIPT_VERSION = "ace.intelligence.memory-graph-query-receipt/v1alpha1"
PROMOTION_RECEIPT_VERSION = "ace.intelligence.memory-promotion-receipt/v1alpha1"
ACTIVATED_CONSTRAINTS_VERSION = "ace.intelligence.memory-activated-constraints/v1alpha1"

MAX_REFS = 256
MAX_ITEMS = 200


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


def _refs(value: Any, *, name: str, required: bool = False, maximum: int = MAX_REFS) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain stable references")
    result = tuple(sorted(set(value)))
    if required and not result:
        raise ValueError(f"{name} must not be empty")
    if len(result) > maximum:
        raise ValueError(f"{name} exceeds the {maximum}-item bound")
    for item in result:
        validate_reference(item, name=name)
    return result


def _derive(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in (None, expected_id):
        raise ValueError(f"{id_field} does not match exact canonical material")
    if getattr(instance, digest_field) not in (None, expected_digest):
        raise ValueError(f"{digest_field} does not match exact canonical material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class AssertionFamilyV1Alpha1(StrEnum):
    IDENTITY = "identity"
    LEARNED_FACT = "learned_fact"
    ACTIVE_CONTEXT = "active_context"
    PREFERENCE = "preference"
    INSTRUCTION_POLICY_PROPOSAL = "instruction_policy_proposal"
    UNCERTAINTY = "uncertainty"
    CORRECTION = "correction"


class AssertionSourceKind(StrEnum):
    AM1_TURN = "am1_turn"
    AM1_EVENT = "am1_event"
    DOCUMENT = "document"
    EXPLICIT_CAPTURE = "explicit_capture"
    REFLECTION_PROPOSAL = "reflection_proposal"
    ELABORATION_PROPOSAL = "elaboration_proposal"
    CONSOLIDATION_PROPOSAL = "consolidation_proposal"


class SourceAuthorityKind(StrEnum):
    AUTHENTICATED_PRINCIPAL = "authenticated_principal"
    GOVERNED_POLICY = "governed_policy"
    ASSISTANT_CONTENT = "assistant_content"
    SYSTEM_CONTENT = "system_content"
    TOOL_CONTENT = "tool_content"
    EXTERNAL_CONTENT = "external_content"
    MODEL_EXTRACTION = "model_extraction"
    UNKNOWN = "unknown"


class EvidenceStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class SourceIndependence(StrEnum):
    INDEPENDENT = "independent"
    SYNDICATED = "syndicated"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class EntityResolution(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class AssertionLifecycle(StrEnum):
    PROPOSED = "proposed"
    UNCERTAINTY = "uncertainty"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CORRECTION_ADMITTED = "correction_admitted"
    INSTRUCTION_POLICY_ADMITTED = "instruction_policy_admitted"


class ReconciliationDisposition(StrEnum):
    NEW_PROPOSAL = "new_proposal"
    EXACT_DUPLICATE = "exact_duplicate"
    SAME_SOURCE_UPDATE = "same_source_update"
    CROSS_SOURCE_AGREEMENT = "cross_source_agreement"
    CROSS_SOURCE_DISAGREEMENT = "cross_source_disagreement"
    UNRESOLVED_IDENTITY = "unresolved_identity"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CORRECTION_PROPOSAL = "correction_proposal"
    INSTRUCTION_ISOLATED = "instruction_isolated"


class ActivatedMemoryConstraintsV1Alpha1(_StrictFrozenContract):
    """Exact inert Pack/Overlay coordinates; these are constraints, never authority."""

    contract: Literal["ace.intelligence.memory-activated-constraints/v1alpha1"] = ACTIVATED_CONSTRAINTS_VERSION
    activation_ref: str
    pack_ref: str | None = None
    pack_version: str | None = None
    pack_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    overlay_ref: str | None = None
    overlay_version: str | None = None
    overlay_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("activation_ref", "pack_ref", "overlay_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def exact_pairs(self) -> Self:
        pack = (self.pack_ref, self.pack_version, self.pack_digest)
        overlay = (self.overlay_ref, self.overlay_version, self.overlay_digest)
        if any(pack) and not all(pack):
            raise ValueError("Pack constraints require exact ref, version, and digest")
        if any(overlay) and not all(overlay):
            raise ValueError("Overlay constraints require exact ref, version, and digest")
        return self


class GovernedEvidenceV1Alpha1(_StrictFrozenContract):
    status: EvidenceStatus
    value: float | None = Field(default=None, ge=0, le=1)
    policy_ref: str | None = None
    evidence_receipt_ref: str | None = None
    unknown_reason_ref: str | None = None

    @field_validator("policy_ref", "evidence_receipt_ref", "unknown_reason_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def meaning(self) -> Self:
        if self.status is EvidenceStatus.KNOWN:
            if self.value is None or self.policy_ref is None or self.evidence_receipt_ref is None:
                raise ValueError("known evidence requires value, policy, and governed receipt")
            if self.unknown_reason_ref is not None:
                raise ValueError("known evidence forbids an unknown reason")
        elif self.value is not None or self.policy_ref is not None or self.evidence_receipt_ref is not None:
            raise ValueError("unknown evidence cannot fabricate a value, policy, or receipt")
        elif self.unknown_reason_ref is None:
            raise ValueError("unknown evidence requires a bounded reason reference")
        return self


class AssertionSourceEnvelopeV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-source-envelope/v1alpha1"] = SOURCE_ENVELOPE_VERSION
    source_kind: AssertionSourceKind
    source_id: str
    source_version_id: str
    span: SourceSpanV1Alpha1
    source_authority: SourceAuthorityKind
    reliability: GovernedEvidenceV1Alpha1
    freshness: GovernedEvidenceV1Alpha1
    independence: SourceIndependence
    origin_ref: str | None = None
    acquisition_receipt_ref: str
    knowledge_time: KnowledgeTimeV1Alpha1
    knowledge_revision_at: datetime
    world_time: WorldTimeV1Alpha1
    session_ref: str | None = None
    turn_ref: str | None = None
    event_ref: str | None = None
    derivation_lineage: tuple[str, ...] = ()
    envelope_id: str | None = None
    envelope_digest: str | None = None

    @field_validator(
        "source_id",
        "source_version_id",
        "origin_ref",
        "acquisition_receipt_ref",
        "session_ref",
        "turn_ref",
        "event_ref",
    )
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("derivation_lineage", mode="before")
    @classmethod
    def lineage(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, name="derivation_lineage")

    @field_validator("knowledge_revision_at")
    @classmethod
    def revision_time(cls, value: datetime) -> datetime:
        return _aware(value, name="knowledge_revision_at")

    @model_validator(mode="after")
    def bind_source(self) -> Self:
        if self.span.source_version_id != self.source_version_id:
            raise ValueError("source span must bind the exact source version")
        if self.independence in {SourceIndependence.SYNDICATED, SourceIndependence.DUPLICATE}:
            if self.origin_ref is None:
                raise ValueError("syndicated or duplicate sources require an exact origin")
        elif self.origin_ref is not None:
            raise ValueError("only syndicated or duplicate sources may name an origin")
        if self.source_kind is AssertionSourceKind.AM1_TURN and (self.session_ref is None or self.turn_ref is None):
            raise ValueError("AM1 turn sources require exact session and turn coordinates")
        if self.source_kind is AssertionSourceKind.AM1_EVENT and (self.session_ref is None or self.event_ref is None):
            raise ValueError("AM1 event sources require exact session and event coordinates")
        if (
            self.source_kind
            in {
                AssertionSourceKind.REFLECTION_PROPOSAL,
                AssertionSourceKind.ELABORATION_PROPOSAL,
                AssertionSourceKind.CONSOLIDATION_PROPOSAL,
            }
            and not self.derivation_lineage
        ):
            raise ValueError("derived proposal sources require exact derivation lineage")
        if (
            self.knowledge_time.first_known_at is not None
            and self.knowledge_revision_at < self.knowledge_time.first_known_at
        ):
            raise ValueError("source knowledge revision cannot precede immutable first-known time")
        _derive(self, prefix="memory_source_envelope", id_field="envelope_id", digest_field="envelope_digest")
        return self


class SemanticTargetV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-semantic-target/v1alpha1"] = SEMANTIC_TARGET_VERSION
    entity_resolution: EntityResolution
    entity_ref: str | None = None
    unresolved_entity_ref: str | None = None
    predicate_ref: str
    target_ref: str | None = None
    coordinate_id: str | None = None

    @field_validator("entity_ref", "unresolved_entity_ref", "predicate_ref", "target_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def exact_resolution(self) -> Self:
        if self.entity_resolution is EntityResolution.RESOLVED:
            if self.entity_ref is None or self.unresolved_entity_ref is not None:
                raise ValueError("resolved targets require only entity_ref")
        elif self.unresolved_entity_ref is None or self.entity_ref is not None:
            raise ValueError("unresolved targets require only unresolved_entity_ref")
        material = self.model_dump(mode="json", exclude={"coordinate_id"})
        expected = stable_id("memory_semantic_target", material)
        if self.coordinate_id not in (None, expected):
            raise ValueError("coordinate_id does not match exact semantic target")
        object.__setattr__(self, "coordinate_id", expected)
        return self


class MemoryAssertionCandidateV1Alpha1(_StrictFrozenContract):
    """Private source-grounded proposal; identity excludes no semantic material."""

    contract: Literal["ace.intelligence.memory-assertion-candidate/v1alpha1"] = ASSERTION_CANDIDATE_VERSION
    family_contract: Literal["ace.intelligence.memory-assertion-family/v1alpha1"] = ASSERTION_FAMILY_VERSION
    scope: AgentMemoryScopeV1Alpha1
    family: AssertionFamilyV1Alpha1
    semantic_target: SemanticTargetV1Alpha1
    statement: str = Field(min_length=1, max_length=8_000)
    statement_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source: AssertionSourceEnvelopeV1Alpha1
    knowledge_time: KnowledgeTimeV1Alpha1
    knowledge_revision_at: datetime
    world_time: WorldTimeV1Alpha1
    confidence: GovernedEvidenceV1Alpha1
    correction_target_ref: str | None = None
    lifecycle: Literal[AssertionLifecycle.PROPOSED] = AssertionLifecycle.PROPOSED
    candidate_id: str | None = None
    candidate_digest: str | None = None

    @field_validator("knowledge_revision_at")
    @classmethod
    def revision_time(cls, value: datetime) -> datetime:
        return _aware(value, name="knowledge_revision_at")

    @field_validator("correction_target_ref")
    @classmethod
    def correction_ref(cls, value: str | None) -> str | None:
        return validate_reference(value, name="correction_target_ref") if value is not None else None

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        expected_statement = f"sha256:{canonical_hash(self.statement)}"
        if self.statement_digest != expected_statement:
            raise ValueError("statement_digest must bind exact private statement material")
        if self.scope.source_id is not None and self.scope.source_id != self.source.source_id:
            raise ValueError("candidate source crossed authenticated source scope")
        if (
            self.knowledge_time.first_known_at is not None
            and self.knowledge_revision_at < self.knowledge_time.first_known_at
        ):
            raise ValueError("knowledge revision cannot precede immutable first-known time")
        if self.family is AssertionFamilyV1Alpha1.CORRECTION:
            if self.correction_target_ref is None:
                raise ValueError("correction proposals require an exact prior assertion target")
        elif self.correction_target_ref is not None:
            raise ValueError("only correction proposals may target a prior assertion")
        _derive(self, prefix="memory_assertion_candidate", id_field="candidate_id", digest_field="candidate_digest")
        return self


class MemoryExtractionRequestV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-extraction-request/v1alpha1"] = EXTRACTION_REQUEST_VERSION
    scope: AgentMemoryScopeV1Alpha1
    source_envelopes: tuple[AssertionSourceEnvelopeV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ITEMS)
    adapter_ref: str
    adapter_version: str
    adapter_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    constraints: ActivatedMemoryConstraintsV1Alpha1
    idempotency_ref: str
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("adapter_ref", "idempotency_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("requested_at")
    @classmethod
    def requested(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        ids = [item.envelope_id for item in self.source_envelopes]
        if len(ids) != len(set(ids)):
            raise ValueError("extraction sources must be unique")
        if any(
            self.scope.source_id is not None and item.source_id != self.scope.source_id
            for item in self.source_envelopes
        ):
            raise ValueError("extraction request crossed authenticated source scope")
        _derive(self, prefix="memory_extraction_request", id_field="request_id", digest_field="request_digest")
        return self


class MemoryExtractionReceiptV1Alpha1(_StrictFrozenContract):
    """Bounded content-free extraction evidence; preview never proves a write."""

    contract: Literal["ace.intelligence.memory-extraction-receipt/v1alpha1"] = EXTRACTION_RECEIPT_VERSION
    request_id: str
    request_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    preview: bool
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    source_envelope_refs: tuple[str, ...]
    candidate_refs: tuple[str, ...]
    candidate_digests: tuple[str, ...]
    generated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("request_id", "authorization_receipt_ref", "lifecycle_snapshot_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("source_envelope_refs", "candidate_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name, required=True, maximum=MAX_ITEMS)

    @field_validator("candidate_digests", mode="before")
    @classmethod
    def digests(cls, value: Any) -> tuple[str, ...]:
        result = tuple(sorted(set(value)))
        if (
            not result
            or len(result) > MAX_ITEMS
            or any(not isinstance(item, str) or len(item) != 71 or not item.startswith("sha256:") for item in result)
        ):
            raise ValueError("candidate_digests must be bounded sha256 digests")
        return result

    @field_validator("generated_at")
    @classmethod
    def generated(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        if len(self.candidate_refs) != len(self.candidate_digests):
            raise ValueError("candidate references and digests must be one-to-one")
        _derive(self, prefix="memory_extraction_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class MemoryReconciliationPolicyV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-reconciliation-policy/v1alpha1"] = RECONCILIATION_POLICY_VERSION
    policy_ref: str
    policy_version: str
    policy_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    minimum_confidence: float = Field(ge=0, le=1)
    require_known_reliability: bool = True
    require_known_freshness: bool = True
    require_known_world_time: bool = True

    @field_validator("policy_ref")
    @classmethod
    def ref(cls, value: str) -> str:
        return validate_reference(value, name="policy_ref")


class MemoryReconciliationDecisionV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-reconciliation-decision/v1alpha1"] = RECONCILIATION_DECISION_VERSION
    candidate: MemoryAssertionCandidateV1Alpha1
    disposition: ReconciliationDisposition
    lifecycle: AssertionLifecycle
    duplicate_of: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    agrees_with: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    uncertainty_ref: str | None = None
    policy_ref: str
    policy_version: str
    evidence_refs: tuple[str, ...]
    ledger_coordinate: LedgerCoordinateV1Alpha1
    decided_at: datetime
    decision_id: str | None = None
    decision_digest: str | None = None

    @field_validator("duplicate_of", "supersedes", "agrees_with", "conflicts_with", "evidence_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name, required=info.field_name == "evidence_refs")

    @field_validator("uncertainty_ref", "policy_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("decided_at")
    @classmethod
    def decided(cls, value: datetime) -> datetime:
        return _aware(value, name="decided_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.ledger_coordinate.committed_at != self.decided_at:
            raise ValueError("ledger commit clock must equal immutable reconciliation commit time")
        material = self.model_dump(mode="json", exclude={"decision_id", "decision_digest", "ledger_coordinate"})
        digest = canonical_hash(material)
        expected_id = f"memory_reconciliation_decision:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.ledger_coordinate.event_ref != expected_id:
            raise ValueError("ledger coordinate must name the exact reconciliation decision")
        if self.decision_id not in (None, expected_id) or self.decision_digest not in (None, expected_digest):
            raise ValueError("decision identity does not match exact reconciliation material")
        object.__setattr__(self, "decision_id", expected_id)
        object.__setattr__(self, "decision_digest", expected_digest)
        return self


class MemoryReconciliationReceiptV1Alpha1(_StrictFrozenContract):
    """Content-free exact reconciliation receipt."""

    contract: Literal["ace.intelligence.memory-reconciliation-receipt/v1alpha1"] = RECONCILIATION_RECEIPT_VERSION
    idempotency_ref: str
    request_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    extraction_receipt_ref: str
    decision_refs: tuple[str, ...]
    decision_digests: tuple[str, ...]
    ledger_coordinates: tuple[LedgerCoordinateV1Alpha1, ...]
    committed_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("idempotency_ref", "authorization_receipt_ref", "lifecycle_snapshot_ref", "extraction_receipt_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("decision_refs", mode="before")
    @classmethod
    def decisions(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, name="decision_refs", required=True, maximum=MAX_ITEMS)

    @field_validator("committed_at")
    @classmethod
    def committed(cls, value: datetime) -> datetime:
        return _aware(value, name="committed_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        if not (len(self.decision_refs) == len(self.decision_digests) == len(self.ledger_coordinates)) or any(
            item.committed_at != self.committed_at for item in self.ledger_coordinates
        ):
            raise ValueError("reconciliation receipt must bind one exact coordinate per decision")
        _derive(self, prefix="memory_reconciliation_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class MemoryAssertionQueryV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-assertion-query/v1alpha1"] = ASSERTION_QUERY_VERSION
    scope: AgentMemoryScopeV1Alpha1
    temporal: TemporalQueryV1Alpha1
    semantic_target_ref: str | None = None
    assertion_refs: tuple[str, ...] = ()
    include_superseded: bool = False
    limit: int = Field(default=50, ge=1, le=MAX_ITEMS)
    query_id: str | None = None

    @field_validator("semantic_target_ref")
    @classmethod
    def target(cls, value: str | None) -> str | None:
        return validate_reference(value, name="semantic_target_ref") if value is not None else None

    @field_validator("assertion_refs", mode="before")
    @classmethod
    def assertions(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, name="assertion_refs", maximum=MAX_ITEMS)

    @model_validator(mode="after")
    def identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"query_id"})
        expected = stable_id("memory_assertion_query", material)
        if self.query_id not in (None, expected):
            raise ValueError("query_id does not match exact temporal assertion query")
        object.__setattr__(self, "query_id", expected)
        return self


class MemoryAssertionQueryReceiptV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-assertion-query-receipt/v1alpha1"] = ASSERTION_QUERY_RECEIPT_VERSION
    query_id: str
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    assertion_refs: tuple[str, ...]
    decision_refs: tuple[str, ...]
    omitted_count: int = Field(ge=0)
    generated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("query_id", "authorization_receipt_ref", "lifecycle_snapshot_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("assertion_refs", "decision_refs", mode="before")
    @classmethod
    def ref_sets(cls, value: Any, info) -> tuple[str, ...]:
        return _refs(value, name=info.field_name, maximum=MAX_ITEMS)

    @field_validator("generated_at")
    @classmethod
    def generated(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        _derive(self, prefix="memory_assertion_query_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class MemoryGraphNodeKind(StrEnum):
    SOURCE = "source"
    SESSION = "session"
    TURN = "turn"
    EVENT = "event"
    ENTITY = "entity"
    ASSERTION = "assertion"
    UNCERTAINTY = "uncertainty"
    CORRECTION = "correction"
    DECISION = "decision"
    COGNITION = "cognition"
    OUTCOME = "outcome"


class MemoryGraphEdgeKind(StrEnum):
    GROUNDED_IN = "grounded_in"
    OCCURRED_IN = "occurred_in"
    TARGETS = "targets"
    SUPERSEDES = "supersedes"
    AGREES_WITH = "agrees_with"
    CONFLICTS_WITH = "conflicts_with"
    CORRECTS = "corrects"
    EXTERNAL_LINEAGE = "external_lineage"


class MemoryGraphNodeV1Alpha1(_StrictFrozenContract):
    kind: MemoryGraphNodeKind
    ref: str
    contract_ref: str | None = None
    digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("ref", "contract_ref")
    @classmethod
    def refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None


class MemoryGraphEdgeV1Alpha1(_StrictFrozenContract):
    kind: MemoryGraphEdgeKind
    from_ref: str
    to_ref: str

    @field_validator("from_ref", "to_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)


class MemoryGraphProjectionV1Alpha1(_StrictFrozenContract):
    """Derived and rebuildable identifiers-only projection, never ledger truth."""

    contract: Literal["ace.intelligence.memory-graph-projection/v1alpha1"] = GRAPH_PROJECTION_VERSION
    scope_id: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    nodes: tuple[MemoryGraphNodeV1Alpha1, ...]
    edges: tuple[MemoryGraphEdgeV1Alpha1, ...]
    rebuilt_at: datetime
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator("scope_id")
    @classmethod
    def scope_ref(cls, value: str) -> str:
        return validate_reference(value, name="scope_id")

    @field_validator("rebuilt_at")
    @classmethod
    def rebuilt(cls, value: datetime) -> datetime:
        return _aware(value, name="rebuilt_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        node_refs = [item.ref for item in self.nodes]
        if len(node_refs) != len(set(node_refs)) or len(self.nodes) > 2_000 or len(self.edges) > 8_000:
            raise ValueError("graph projection must contain bounded unique nodes")
        known = set(node_refs)
        if any(edge.from_ref not in known or edge.to_ref not in known for edge in self.edges):
            raise ValueError("graph edges must bind exact projected nodes")
        object.__setattr__(self, "nodes", tuple(sorted(self.nodes, key=lambda item: (item.kind, item.ref))))
        object.__setattr__(
            self, "edges", tuple(sorted(self.edges, key=lambda item: (item.kind, item.from_ref, item.to_ref)))
        )
        _derive(self, prefix="memory_graph_projection", id_field="projection_id", digest_field="projection_digest")
        return self


class MemoryGraphQueryReceiptV1Alpha1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.memory-graph-query-receipt/v1alpha1"] = GRAPH_QUERY_RECEIPT_VERSION
    projection_ref: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    authorization_receipt_ref: str
    lifecycle_snapshot_ref: str
    node_refs: tuple[str, ...]
    edge_count: int = Field(ge=0)
    generated_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("projection_ref", "authorization_receipt_ref", "lifecycle_snapshot_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("node_refs", mode="before")
    @classmethod
    def nodes(cls, value: Any) -> tuple[str, ...]:
        return _refs(value, name="node_refs", maximum=2_000)

    @field_validator("generated_at")
    @classmethod
    def generated(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        _derive(self, prefix="memory_graph_query_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


class MemoryPromotionReceiptV1Alpha1(_StrictFrozenContract):
    """Separate bounded reference to an existing Core governed-state commit."""

    contract: Literal["ace.intelligence.memory-promotion-receipt/v1alpha1"] = PROMOTION_RECEIPT_VERSION
    assertion_ref: str
    assertion_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    target_ref: str
    promotion_kind: Literal["correction", "instruction_policy"]
    governed_state_receipt_ref: str
    governed_state_receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    promoted_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("assertion_ref", "target_ref", "governed_state_receipt_ref")
    @classmethod
    def refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("promoted_at")
    @classmethod
    def promoted(cls, value: datetime) -> datetime:
        return _aware(value, name="promoted_at")

    @model_validator(mode="after")
    def identity(self) -> Self:
        _derive(self, prefix="memory_promotion_receipt", id_field="receipt_id", digest_field="receipt_digest")
        return self


__all__ = [
    name
    for name in globals()
    if name.startswith("Memory")
    or name.startswith("Assertion")
    or name
    in {
        "ActivatedMemoryConstraintsV1Alpha1",
        "EntityResolution",
        "EvidenceStatus",
        "GovernedEvidenceV1Alpha1",
        "ReconciliationDisposition",
        "SemanticTargetV1Alpha1",
        "SourceAuthorityKind",
        "SourceIndependence",
    }
]
