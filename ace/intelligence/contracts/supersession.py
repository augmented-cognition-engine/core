"""Domain-neutral, append-only supersession-impact contracts.

When a record is superseded or corrected, the honest question is not "what is now
false" — ACE cannot know that — but **"what depended on it?"**. These contracts
carry that answer: the exact superseder, the exact superseded target, the exact
cutoff the answer was computed under, and every downstream resource whose
admitted lineage reaches the target, with the path that put it in scope.

Append-only by construction
---------------------------
Nothing here rewrites, retracts, or invalidates a historical artifact. A prior
Brief keeps its exact identity and stays replayable under its original cutoff.
The impact projection is a **separate, later, additive** record that says which
of that Brief's material has since been superseded. Reading the impact view is
the consumer's decision; ACE never silently mutates history.

What this does not claim
------------------------
Impact is *dependency*, not falsehood. A statement that depended on a corrected
record may still be entirely correct — the World fixture's own correction leaves
an attributed statement untouched. The projection therefore reports scope and
reasons, and explicitly carries the set of resources it found **unaffected**, so
a reader can see the boundary rather than infer it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.common import validate_digest, validate_reference
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    IntelligenceResourceMode,
    LineageRelation,
    LineageResourceKind,
)

SUPERSESSION_IMPACT_PATH_VERSION = "ace.intelligence.supersession-impact-path/v1alpha1"
SUPERSESSION_CLAIM_IMPACT_VERSION = "ace.intelligence.supersession-claim-impact/v1alpha1"
SUPERSESSION_IMPACT_PROJECTION_VERSION = "ace.intelligence.supersession-impact-projection/v1alpha1"

#: Durable record kind for the sibling impact projection.
SUPERSESSION_IMPACT_PROJECTION_KIND = "supersession_impact_projection"

MAX_IMPACTED = 4_096


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


def _reference(value: str, *, name: str) -> str:
    return validate_reference(value, name=name)


def _digest(value: str, *, name: str) -> str:
    try:
        return validate_digest(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in (None, expected_id):
        raise ValueError(f"{id_field} does not match exact supersession material")
    if getattr(instance, digest_field) not in (None, expected_digest):
        raise ValueError(f"{digest_field} does not match exact supersession material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class SupersessionImpactPathV1Alpha1(_StrictFrozenContract):
    """One downstream resource and the exact edge that put it in scope."""

    contract: Literal["ace.intelligence.supersession-impact-path/v1alpha1"] = SUPERSESSION_IMPACT_PATH_VERSION
    resource_id: str
    resource_kind: LineageResourceKind
    resource_digest: str
    #: ``1`` means this resource names the superseded target directly; higher
    #: depths reached it through other impacted resources.
    depth: int = Field(ge=1, le=64)
    #: The exact resource this one depends on, one step closer to the target.
    via_resource_id: str
    #: The exact lineage relation that expressed that dependency.
    via_relation: LineageRelation

    @field_validator("resource_id", "via_resource_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("resource_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _digest(value, name="resource_digest")

    @model_validator(mode="after")
    def reject_self_reference(self) -> Self:
        if self.resource_id == self.via_resource_id:
            raise ValueError("an impact path cannot depend on itself")
        return self


class SupersessionClaimImpactV1Alpha1(_StrictFrozenContract):
    """One Brief claim whose exact grounded support reaches the superseded record."""

    contract: Literal["ace.intelligence.supersession-claim-impact/v1alpha1"] = SUPERSESSION_CLAIM_IMPACT_VERSION
    brief_id: str
    claim_id: str
    #: The exact supports of this claim that are impacted. Never all supports
    #: unless every one of them is impacted.
    impacted_support_record_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    total_support_count: int = Field(ge=1, le=256)
    #: ``True`` only when every support of the claim is impacted.
    fully_impacted: StrictBool

    @field_validator("brief_id", "claim_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator("impacted_support_record_ids")
    @classmethod
    def normalize_supports(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="impacted_support_record_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("impacted claim supports must be unique")
        return tuple(sorted(validated))

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        impacted = len(self.impacted_support_record_ids)
        if impacted > self.total_support_count:
            raise ValueError("a claim cannot have more impacted supports than supports")
        if self.fully_impacted is not (impacted == self.total_support_count):
            raise ValueError("fully_impacted must reflect whether every support is impacted")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("claim impact must name one exact Brief identity")
        return self


class SupersessionImpactProjectionV1Alpha1(_StrictFrozenContract):
    """Durable, append-only enumeration of what depended on a superseded record."""

    contract: Literal["ace.intelligence.supersession-impact-projection/v1alpha1"] = (
        SUPERSESSION_IMPACT_PROJECTION_VERSION
    )
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    #: The record asserting the supersession, and the record it supersedes.
    superseder_resource_id: str
    superseder_resource_digest: str
    superseder_available_at: datetime
    superseded_resource_id: str
    superseded_resource_digest: str
    superseded_resource_kind: LineageResourceKind
    #: The exact predicate and the relations it followed.
    impact_policy: str
    eligible_relations: tuple[str, ...] = Field(min_length=1, max_length=8)
    #: No resource available after this instant was considered.
    closure_cutoff_at: datetime
    closure_resource_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_IMPACTED)
    impacted: tuple[SupersessionImpactPathV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_IMPACTED,
    )
    #: Everything in the closure the traversal did **not** reach. Disclosed so a
    #: reader can see the boundary of the claim rather than infer it.
    unaffected_resource_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_IMPACTED)
    claim_impacts: tuple[SupersessionClaimImpactV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_IMPACTED,
    )
    #: Historical artifacts this projection explicitly does not alter.
    preserved_artifact_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    as_of: datetime
    generated_at: datetime
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator(
        "product_id",
        "superseder_resource_id",
        "superseded_resource_id",
        "impact_policy",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator(
        "superseder_resource_digest",
        "superseded_resource_digest",
        "projection_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("eligible_relations")
    @classmethod
    def normalize_relations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(LineageRelation(item).value for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("eligible relations must be unique")
        return tuple(sorted(validated))

    @field_validator(
        "closure_resource_ids",
        "unaffected_resource_ids",
        "preserved_artifact_ids",
    )
    @classmethod
    def normalize_identity_sets(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(_reference(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must use unique exact identities")
        return tuple(sorted(validated))

    @field_validator("superseder_available_at", "closure_cutoff_at", "as_of", "generated_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("projection_id")
    @classmethod
    def validate_projection_id(cls, value: str | None) -> str | None:
        return _reference(value, name="projection_id") if value is not None else None

    @field_validator("impacted")
    @classmethod
    def normalize_impacted(
        cls,
        value: tuple[SupersessionImpactPathV1Alpha1, ...],
    ) -> tuple[SupersessionImpactPathV1Alpha1, ...]:
        ids = [item.resource_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("each impacted resource must appear exactly once")
        return tuple(sorted(value, key=lambda item: (item.depth, item.resource_id)))

    @field_validator("claim_impacts")
    @classmethod
    def normalize_claim_impacts(
        cls,
        value: tuple[SupersessionClaimImpactV1Alpha1, ...],
    ) -> tuple[SupersessionClaimImpactV1Alpha1, ...]:
        keys = [(item.brief_id, item.claim_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("each impacted claim must appear exactly once")
        return tuple(sorted(value, key=lambda item: (item.brief_id, item.claim_id)))

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("impact projection crossed exact product scope")
        if self.superseder_resource_id == self.superseded_resource_id:
            raise ValueError("a record cannot supersede itself")
        if self.superseder_available_at > self.generated_at:
            raise ValueError("a supersession cannot be projected before it is available")
        if self.as_of > self.generated_at:
            raise ValueError("impact as_of must not follow its generation time")
        closure = set(self.closure_resource_ids)
        if self.superseded_resource_id not in closure:
            raise ValueError("the superseded record must belong to the exact projected closure")
        impacted_ids = {item.resource_id for item in self.impacted}
        if not impacted_ids <= closure:
            raise ValueError("every impacted resource must belong to the exact projected closure")
        if self.superseder_resource_id in impacted_ids:
            raise ValueError("the superseder is the cause of the impact, never its subject")
        if self.superseded_resource_id in impacted_ids:
            raise ValueError("the superseded target is not downstream of itself")
        unaffected = set(self.unaffected_resource_ids)
        if unaffected & impacted_ids:
            raise ValueError("a resource cannot be both impacted and unaffected")
        expected_unaffected = closure - impacted_ids - {self.superseded_resource_id}
        if unaffected != expected_unaffected:
            raise ValueError("unaffected resources must be exactly the closure minus the target and its impact")
        reachable = impacted_ids | {self.superseded_resource_id}
        for item in self.impacted:
            if item.via_resource_id not in reachable:
                raise ValueError("every impact path must step through the target or another impacted resource")
            if item.depth == 1 and item.via_resource_id != self.superseded_resource_id:
                raise ValueError("a direct impact must name the superseded target itself")
        for item in self.claim_impacts:
            if not set(item.impacted_support_record_ids) <= impacted_ids | {self.superseded_resource_id}:
                raise ValueError("an impacted claim support must itself be the target or an impacted resource")
        _derive_identity(
            self,
            prefix="supersession_impact_projection",
            id_field="projection_id",
            digest_field="projection_digest",
        )
        return self


__all__ = [
    "MAX_IMPACTED",
    "SUPERSESSION_CLAIM_IMPACT_VERSION",
    "SUPERSESSION_IMPACT_PATH_VERSION",
    "SUPERSESSION_IMPACT_PROJECTION_KIND",
    "SUPERSESSION_IMPACT_PROJECTION_VERSION",
    "SupersessionClaimImpactV1Alpha1",
    "SupersessionImpactPathV1Alpha1",
    "SupersessionImpactProjectionV1Alpha1",
]
