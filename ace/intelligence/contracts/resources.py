"""Immutable, domain-neutral ACE Intelligence resources.

The contracts in this module describe the shared Intelligence resource DAG.  They
deliberately contain no domain nouns and impose no Observation -> Signal -> Shift
-> Brief promotion sequence.  Every resource is an independently content-addressed
as-of record governed by one exact Domain Activation revision.

``EntitySnapshotV1Alpha1`` is intentionally a snapshot rather than a mutable
``EntityState`` object: changing projected entity state creates another immutable
snapshot and may cite the prior snapshot through lineage.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.intelligence.contracts.common import (
    MAX_CANONICAL_VALUE_CHARS,
    MAX_REFS,
    parse_json_strict,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)

OBSERVATION_VERSION = "ace.intelligence.observation/v1alpha1"
ENTITY_SNAPSHOT_VERSION = "ace.intelligence.entity-snapshot/v1alpha1"
SIGNAL_VERSION = "ace.intelligence.signal/v1alpha1"
SHIFT_VERSION = "ace.intelligence.shift/v1alpha1"
BRIEF_VERSION = "ace.intelligence.brief/v1alpha1"
CASE_VERSION = "ace.intelligence.case/v1alpha1"
CITATION_VERSION = "ace.intelligence.citation/v1alpha1"
GROUNDED_CLAIM_VERSION = "ace.intelligence.grounded-claim/v1alpha1"
ACTIVATION_REVISION_REFERENCE_VERSION = "ace.intelligence.activation-revision-reference/v1alpha1"
LINEAGE_REFERENCE_VERSION = "ace.intelligence.lineage-reference/v1alpha1"
CANONICAL_JSON_VALUE_VERSION = "ace.intelligence.canonical-json-value/v1alpha1"
SOURCE_MAPPING_REFERENCE_VERSION = "ace.intelligence.source-mapping-reference/v1alpha1"

MAX_SUBJECT_REFS = 256
MAX_CITATIONS = 256
MAX_CLAIMS = 256
MAX_BRIEF_CHARS = 100_000


class _StrictFrozenContract(FrozenContract):
    """A deeply immutable-by-shape contract with no Python input coercion."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class IntelligenceResourceMode(StrEnum):
    """Whether a resource is a preview artifact or part of the live intelligence record."""

    PREPARED = "prepared"
    LIVE = "live"


class EvidenceAcquisitionMode(StrEnum):
    """How cited evidence entered ACE; hosts verify the accompanying acquisition receipt."""

    LIVE = "live"
    RECORDED_REPLAY = "recorded_replay"
    PREPARED_FIXTURE = "prepared_fixture"


class ClaimGroundingKind(StrEnum):
    """Whether a claim is directly cited or an explicitly bounded inference."""

    CITED = "cited"
    INFERENCE = "inference"


class LineageResourceKind(StrEnum):
    """Domain-neutral resource families that may participate in the Intelligence DAG."""

    EVIDENCE = "evidence"
    OBSERVATION = "observation"
    ENTITY_SNAPSHOT = "entity_snapshot"
    SIGNAL = "signal"
    SHIFT = "shift"
    CASE = "case"
    BRIEF = "brief"
    DECISION = "decision"
    OUTCOME = "outcome"
    RECEIPT = "receipt"


class LineageRelation(StrEnum):
    """How an exact upstream record contributed to the current resource."""

    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
    SUPERSEDES = "supersedes"


def _normalize_aware_datetime(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _strict_confidence(value: Any) -> float:
    if type(value) is not float:
        raise ValueError("confidence must be a float without coercion")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be finite and between 0.0 and 1.0")
    return value


def _sorted_references(values: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    validated = tuple(validate_reference(value, name=label) for value in values)
    if len(validated) != len(set(validated)):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(validated))


def _derive_identity(
    instance: FrozenContract,
    *,
    id_field: str,
    digest_field: str,
    prefix: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact resource material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact resource material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class CanonicalJsonValueV1Alpha1(_StrictFrozenContract):
    """Bounded canonical JSON stored as text so public resources remain deeply immutable."""

    contract: Literal["ace.intelligence.canonical-json-value/v1alpha1"] = CANONICAL_JSON_VALUE_VERSION
    value_json: str = Field(min_length=1, max_length=MAX_CANONICAL_VALUE_CHARS)

    @field_validator("value_json")
    @classmethod
    def normalize_json(cls, value: str) -> str:
        try:
            normalized = canonical_json(parse_json_strict(value))
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("value_json must be bounded finite JSON with unique object keys") from exc
        if len(normalized) > MAX_CANONICAL_VALUE_CHARS:
            raise ValueError("value_json exceeds the bounded canonical size")
        return normalized

    def parsed_value(self) -> Any:
        """Return a fresh parsed value; mutating it cannot mutate this contract."""

        return parse_json_strict(self.value_json)


class ActivationRevisionReferenceV1Alpha1(_StrictFrozenContract):
    """Exact product-scoped handle whose existence and state a host must resolve through Core."""

    contract: Literal["ace.intelligence.activation-revision-reference/v1alpha1"] = ACTIVATION_REVISION_REFERENCE_VERSION
    product_id: str
    activation_key: str
    activation_id: str
    revision: StrictInt = Field(ge=1)
    revision_id: str
    revision_digest: str

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("activation_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return validate_slug(value, name="activation_key")

    @field_validator("activation_id", "revision_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("revision_digest")
    @classmethod
    def validate_revision_digest(cls, value: str) -> str:
        return validate_digest(value)

    @model_validator(mode="after")
    def validate_exact_reference(self) -> Self:
        expected_activation_id = f"domain_activation:{canonical_hash([self.product_id, self.activation_key])[:32]}"
        if self.activation_id != expected_activation_id:
            raise ValueError("activation_id does not match product_id and activation_key")
        expected_revision_id = f"activation_revision:{self.revision_digest.removeprefix('sha256:')[:32]}"
        if self.revision_id != expected_revision_id:
            raise ValueError("revision_id and revision_digest do not identify the same revision")
        return self


class SourceMappingReferenceV1Alpha1(_StrictFrozenContract):
    """Exact activation-bound Pack IR rule that normalized one Observation."""

    contract: Literal["ace.intelligence.source-mapping-reference/v1alpha1"] = SOURCE_MAPPING_REFERENCE_VERSION
    activation_revision: ActivationRevisionReferenceV1Alpha1
    compiled_pack_id: str
    pack_digest: str
    module_id: str
    module_digest: str
    mapping_id: str
    mapping_digest: str

    @field_validator("compiled_pack_id")
    @classmethod
    def validate_compiled_pack_id(cls, value: str) -> str:
        return validate_reference(value, name="compiled_pack_id")

    @field_validator("module_id", "mapping_id")
    @classmethod
    def validate_mapping_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("pack_digest", "module_digest", "mapping_digest")
    @classmethod
    def validate_mapping_digests(cls, value: str) -> str:
        return validate_digest(value)

    @model_validator(mode="after")
    def validate_pack_identity(self) -> Self:
        expected_pack_id = f"pack_ir:{self.pack_digest.removeprefix('sha256:')[:32]}"
        if self.compiled_pack_id != expected_pack_id:
            raise ValueError("compiled_pack_id and pack_digest must identify one exact Pack IR")
        return self


class LineageReferenceV1Alpha1(_StrictFrozenContract):
    """One exact edge from an Intelligence resource to an upstream immutable record."""

    contract: Literal["ace.intelligence.lineage-reference/v1alpha1"] = LINEAGE_REFERENCE_VERSION
    resource_kind: LineageResourceKind
    relation: LineageRelation = LineageRelation.DERIVED_FROM
    resource_id: str
    resource_digest: str
    resource_as_of: datetime
    resource_available_at: datetime

    @field_validator("resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        return validate_reference(value, name="lineage resource_id")

    @field_validator("resource_digest")
    @classmethod
    def validate_resource_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("resource_as_of", "resource_available_at")
    @classmethod
    def normalize_resource_times(cls, value: datetime, info) -> datetime:
        return _normalize_aware_datetime(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_content_identity_pair(self) -> Self:
        if self.resource_available_at < self.resource_as_of:
            raise ValueError("lineage resource_available_at cannot precede resource_as_of")
        prefix = self.resource_kind.value
        if not self.resource_id.startswith(f"{prefix}:"):
            raise ValueError("lineage resource kind must match the resource ID prefix")
        content_addressed_kinds = {
            LineageResourceKind.OBSERVATION,
            LineageResourceKind.ENTITY_SNAPSHOT,
            LineageResourceKind.SIGNAL,
            LineageResourceKind.SHIFT,
            LineageResourceKind.CASE,
            LineageResourceKind.BRIEF,
        }
        if self.resource_kind in content_addressed_kinds:
            expected_id = f"{prefix}:{self.resource_digest.removeprefix('sha256:')[:32]}"
            if self.resource_id != expected_id:
                raise ValueError("content-addressed lineage resource kind, ID, and digest must identify one record")
        return self


class CitationV1Alpha1(_StrictFrozenContract):
    """A content-pinned source location used to ground one or more Brief claims."""

    contract: Literal["ace.intelligence.citation/v1alpha1"] = CITATION_VERSION
    source_ref: str
    source_digest: str
    acquisition_mode: EvidenceAcquisitionMode
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str
    source_as_of: datetime
    retrieved_at: datetime
    locator: str | None = Field(default=None, min_length=1, max_length=500)
    excerpt: str | None = Field(default=None, min_length=1, max_length=4_000)
    citation_id: str | None = None
    citation_digest: str | None = None

    @field_validator("source_ref", "acquisition_receipt_ref")
    @classmethod
    def validate_source_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("source_digest", "acquisition_receipt_digest")
    @classmethod
    def validate_source_digests(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("source_as_of", "retrieved_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _normalize_aware_datetime(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.retrieved_at < self.source_as_of:
            raise ValueError("citation retrieved_at cannot precede source_as_of")
        _derive_identity(
            self,
            id_field="citation_id",
            digest_field="citation_digest",
            prefix="citation",
        )
        return self


class GroundedClaimV1Alpha1(_StrictFrozenContract):
    """A Brief claim tied to one or more exact Citation records."""

    contract: Literal["ace.intelligence.grounded-claim/v1alpha1"] = GROUNDED_CLAIM_VERSION
    statement: str = Field(min_length=1, max_length=4_000)
    grounding_kind: ClaimGroundingKind = ClaimGroundingKind.CITED
    citation_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    inference_basis_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    confidence: float
    uncertainty: str | None = Field(default=None, min_length=1, max_length=2_000)
    claim_id: str | None = None
    claim_digest: str | None = None

    @field_validator("citation_ids")
    @classmethod
    def normalize_citation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="claim citation IDs")

    @field_validator("inference_basis_refs")
    @classmethod
    def normalize_inference_basis_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="claim inference basis references")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        return _strict_confidence(value)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.grounding_kind is ClaimGroundingKind.CITED:
            if not self.citation_ids:
                raise ValueError("a cited claim requires at least one citation")
            if self.inference_basis_refs:
                raise ValueError("a cited claim cannot declare inference basis references")
        else:
            if not self.inference_basis_refs:
                raise ValueError("an inference claim requires explicit basis references")
            if self.uncertainty is None:
                raise ValueError("an inference claim requires an explicit uncertainty statement")
        _derive_identity(
            self,
            id_field="claim_id",
            digest_field="claim_digest",
            prefix="grounded_claim",
        )
        return self


class _IntelligenceResourceV1Alpha1(_StrictFrozenContract):
    """Common governed identity, time, and lineage envelope for Intelligence resources."""

    _resource_id_prefix: ClassVar[str]
    _availability_field: ClassVar[str]

    product_id: str
    mode: IntelligenceResourceMode
    activation_revision: ActivationRevisionReferenceV1Alpha1
    as_of: datetime
    lineage: tuple[LineageReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_REFS)
    resource_id: str | None = None
    resource_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value, name="as_of")

    @field_validator("lineage")
    @classmethod
    def normalize_lineage(cls, value: tuple[LineageReferenceV1Alpha1, ...]) -> tuple[LineageReferenceV1Alpha1, ...]:
        identity_by_id: dict[str, tuple[LineageResourceKind, str]] = {}
        for item in value:
            identity = (item.resource_kind, item.resource_digest)
            prior = identity_by_id.setdefault(item.resource_id, identity)
            if prior != identity:
                raise ValueError("one lineage resource ID cannot name multiple kinds or digests")
        keys = [
            (item.resource_kind.value, item.relation.value, item.resource_id, item.resource_digest) for item in value
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("lineage references must be unique")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.resource_kind.value,
                    item.relation.value,
                    item.resource_id,
                    item.resource_digest,
                ),
            )
        )

    @model_validator(mode="after")
    def validate_scope_and_derive_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("resource product_id must match its exact activation revision")
        available_at = getattr(self, self._availability_field)
        future_state = [item.resource_id for item in self.lineage if item.resource_as_of > self.as_of]
        if future_state:
            raise ValueError(f"lineage resources cannot have a later as_of cutoff: {sorted(future_state)}")
        unavailable = [item.resource_id for item in self.lineage if item.resource_available_at > available_at]
        if unavailable:
            raise ValueError(
                f"lineage resources must be available before this resource is produced: {sorted(unavailable)}"
            )
        _derive_identity(
            self,
            id_field="resource_id",
            digest_field="resource_digest",
            prefix=self._resource_id_prefix,
        )
        return self


class ObservationV1Alpha1(_IntelligenceResourceV1Alpha1):
    """A normalized source observation; it need not produce any later resource."""

    _resource_id_prefix = "observation"
    _availability_field = "ingested_at"

    contract: Literal["ace.intelligence.observation/v1alpha1"] = OBSERVATION_VERSION
    source_ref: str
    source_digest: str
    acquisition_mode: EvidenceAcquisitionMode
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    ingested_at: datetime
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_SUBJECT_REFS)
    payload: CanonicalJsonValueV1Alpha1
    confidence: float
    source_mapping: SourceMappingReferenceV1Alpha1 | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("source_ref", "acquisition_receipt_ref")
    @classmethod
    def validate_source_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("source_digest", "acquisition_receipt_digest")
    @classmethod
    def validate_source_digests(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator(
        "source_published_at",
        "event_effective_at",
        "observed_at",
        "ingested_at",
    )
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _normalize_aware_datetime(value, name=info.field_name) if value is not None else None

    @field_validator("subject_refs")
    @classmethod
    def normalize_subject_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="observation subject references")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        return _strict_confidence(value)

    @model_validator(mode="after")
    def prevent_fixture_as_live(self) -> Self:
        if self.mode is IntelligenceResourceMode.LIVE and self.acquisition_mode is not EvidenceAcquisitionMode.LIVE:
            raise ValueError("a live Observation requires live acquisition")
        if self.observed_at > self.ingested_at:
            raise ValueError("Observation ingested_at cannot precede observed_at")
        if self.ingested_at > self.as_of:
            raise ValueError("Observation as_of cannot precede ingested_at")
        if self.source_published_at is not None and self.source_published_at > self.observed_at:
            raise ValueError("Observation source_published_at cannot follow observed_at")
        if self.source_mapping is not None and self.source_mapping.activation_revision != self.activation_revision:
            raise ValueError("Observation source mapping must bind its exact activation revision")
        return self


class EntitySnapshotV1Alpha1(_IntelligenceResourceV1Alpha1):
    """An immutable as-of projection of one resolved entity's attributes."""

    _resource_id_prefix = "entity_snapshot"
    _availability_field = "projected_at"

    contract: Literal["ace.intelligence.entity-snapshot/v1alpha1"] = ENTITY_SNAPSHOT_VERSION
    entity_ref: str
    entity_type_ref: str
    attributes: CanonicalJsonValueV1Alpha1
    projected_at: datetime
    confidence: float

    @field_validator("entity_ref", "entity_type_ref")
    @classmethod
    def validate_entity_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("projected_at")
    @classmethod
    def normalize_projected_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value, name="projected_at")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        return _strict_confidence(value)

    @model_validator(mode="after")
    def validate_projection_time(self) -> Self:
        if self.projected_at < self.as_of:
            raise ValueError("Entity Snapshot projected_at cannot precede as_of")
        return self


class SignalV1Alpha1(_IntelligenceResourceV1Alpha1):
    """A detected item of attention; no Observation or Shift predecessor is required."""

    _resource_id_prefix = "signal"
    _availability_field = "detected_at"

    contract: Literal["ace.intelligence.signal/v1alpha1"] = SIGNAL_VERSION
    signal_type_ref: str
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_SUBJECT_REFS)
    details: CanonicalJsonValueV1Alpha1
    detected_at: datetime
    confidence: float

    @field_validator("signal_type_ref")
    @classmethod
    def validate_signal_type_ref(cls, value: str) -> str:
        return validate_reference(value, name="signal_type_ref")

    @field_validator("subject_refs")
    @classmethod
    def normalize_subject_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="signal subject references")

    @field_validator("detected_at")
    @classmethod
    def normalize_detected_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value, name="detected_at")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        return _strict_confidence(value)

    @model_validator(mode="after")
    def validate_detection_time(self) -> Self:
        if self.detected_at < self.as_of:
            raise ValueError("Signal detected_at cannot precede as_of")
        return self


class ShiftV1Alpha1(_IntelligenceResourceV1Alpha1):
    """A material delta against a stated baseline; it need not have a Signal predecessor."""

    _resource_id_prefix = "shift"
    _availability_field = "detected_at"

    contract: Literal["ace.intelligence.shift/v1alpha1"] = SHIFT_VERSION
    shift_type_ref: str
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_SUBJECT_REFS)
    baseline_as_of: datetime
    baseline: CanonicalJsonValueV1Alpha1
    current: CanonicalJsonValueV1Alpha1
    delta: CanonicalJsonValueV1Alpha1
    detected_at: datetime
    confidence: float

    @field_validator("shift_type_ref")
    @classmethod
    def validate_shift_type_ref(cls, value: str) -> str:
        return validate_reference(value, name="shift_type_ref")

    @field_validator("subject_refs")
    @classmethod
    def normalize_subject_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="shift subject references")

    @field_validator("baseline_as_of", "detected_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _normalize_aware_datetime(value, name=info.field_name)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        return _strict_confidence(value)

    @model_validator(mode="after")
    def validate_temporal_window(self) -> Self:
        if self.baseline_as_of > self.as_of:
            raise ValueError("baseline_as_of cannot be later than the Shift as_of time")
        if self.detected_at < self.as_of:
            raise ValueError("Shift detected_at cannot precede as_of")
        return self


class CaseV1Alpha1(_IntelligenceResourceV1Alpha1):
    """An immutable as-of closure over several exact Intelligence developments.

    A Case is orientation material, not a mutable workspace or an attention
    event. Its content identity binds the exact upstream records, subject
    scope, purpose, cutoff, and assembly time. Because upstream resources are
    themselves content-addressed, the direct member set commits transitively to
    every admitted derivation below it.
    """

    _resource_id_prefix = "case"
    _availability_field = "assembled_at"

    contract: Literal["ace.intelligence.case/v1alpha1"] = CASE_VERSION
    case_type_ref: str
    title: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2_000)
    subject_refs: tuple[str, ...] = Field(min_length=1, max_length=MAX_SUBJECT_REFS)
    assembled_at: datetime

    @field_validator("case_type_ref")
    @classmethod
    def validate_case_type_ref(cls, value: str) -> str:
        return validate_reference(value, name="case_type_ref")

    @field_validator("subject_refs")
    @classmethod
    def normalize_subject_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_references(value, label="Case subject references")

    @field_validator("assembled_at")
    @classmethod
    def normalize_assembled_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value, name="assembled_at")

    @model_validator(mode="after")
    def validate_closure(self) -> Self:
        if self.assembled_at < self.as_of:
            raise ValueError("Case assembled_at cannot precede its as_of cutoff")
        if len(self.lineage) < 2:
            raise ValueError("a Case requires at least two exact upstream resources")
        return self


class BriefV1Alpha1(_IntelligenceResourceV1Alpha1):
    """A grounded narrative over any frozen combination of upstream resources."""

    _resource_id_prefix = "brief"
    _availability_field = "generated_at"

    contract: Literal["ace.intelligence.brief/v1alpha1"] = BRIEF_VERSION
    brief_type_ref: str
    title: str = Field(min_length=1, max_length=300)
    executive_summary: str = Field(min_length=1, max_length=8_000)
    body_markdown: str = Field(min_length=1, max_length=MAX_BRIEF_CHARS)
    generated_at: datetime
    citations: tuple[CitationV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_CITATIONS)
    claims: tuple[GroundedClaimV1Alpha1, ...] = Field(min_length=1, max_length=MAX_CLAIMS)

    @field_validator("brief_type_ref")
    @classmethod
    def validate_brief_type_ref(cls, value: str) -> str:
        return validate_reference(value, name="brief_type_ref")

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value, name="generated_at")

    @field_validator("citations")
    @classmethod
    def normalize_citations(cls, value: tuple[CitationV1Alpha1, ...]) -> tuple[CitationV1Alpha1, ...]:
        ids = [item.citation_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Brief citations must use unique content identities")
        return tuple(sorted(value, key=lambda item: item.citation_id or ""))

    @field_validator("claims")
    @classmethod
    def validate_unique_claims(cls, value: tuple[GroundedClaimV1Alpha1, ...]) -> tuple[GroundedClaimV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Brief claims must use unique content identities")
        return value

    @model_validator(mode="after")
    def validate_claim_grounding(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("Brief generated_at cannot precede as_of")
        unavailable = [
            item.citation_id
            for item in self.citations
            if item.source_as_of > self.as_of or item.retrieved_at > self.as_of
        ]
        if unavailable:
            raise ValueError("Brief citations must be available by the Brief as_of cutoff")
        citation_ids = {item.citation_id for item in self.citations}
        used_citation_ids = {citation_id for claim in self.claims for citation_id in claim.citation_ids}
        missing = used_citation_ids - citation_ids
        if missing:
            raise ValueError(f"Brief claims reference missing citations: {sorted(missing)}")
        unused = citation_ids - used_citation_ids
        if unused:
            raise ValueError(f"Brief contains unused citations: {sorted(unused)}")
        lineage_ids = {item.resource_id for item in self.lineage}
        used_basis_refs = {
            basis_ref
            for claim in self.claims
            if claim.grounding_kind is ClaimGroundingKind.INFERENCE
            for basis_ref in claim.inference_basis_refs
        }
        missing_basis = used_basis_refs - lineage_ids
        if missing_basis:
            raise ValueError(
                f"Brief inference basis references are missing from exact lineage: {sorted(missing_basis)}"
            )
        if self.mode is IntelligenceResourceMode.LIVE:
            nonlive = [
                item.citation_id for item in self.citations if item.acquisition_mode is not EvidenceAcquisitionMode.LIVE
            ]
            if nonlive:
                raise ValueError("a live Brief cannot cite prepared-fixture or recorded-replay evidence")
        return self
