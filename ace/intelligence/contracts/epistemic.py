"""Domain-neutral per-statement epistemic-status declaration and projection.

ACE owns the *grammar* of epistemic status; a Domain Pack owns the *vocabulary*.
Core knows nothing about any of this. Intelligence declares:

* what a status declaration may constrain (:class:`EpistemicStatusDeclarationV1`),
* how a bounded vocabulary binds to Brief templates (:class:`EpistemicStatusSetV1`),
* how a provider names one status per draft claim
  (:class:`BriefSynthesisDraftV1Alpha2`),
* and how the resulting per-claim status becomes a durable, machine-readable
  sibling projection of one exact Brief
  (:class:`BriefEpistemicStatusProjectionV1Alpha1`).

Honest scope of validation
--------------------------
Every constraint expressible here is derived from the strongest domain-neutral
support facts ACE currently possesses about a claim:

* its :class:`ClaimGroundingKind` (``cited`` or ``inference``),
* the exact set of selected support record identities bound to it,
* the cardinality of that set,
* the resource *kinds* of those supports, and
* whether the claim carries an explicit uncertainty statement.

That is all. In particular a ``corroborated``-style label can require a minimum
number of supports, a minimum number of *distinct support kinds*, and a closed
set of allowed kinds -- but none of those facts prove that the supports come
from **independent source families**. ACE has no public derivation-family or
source-independence predicate yet. ``proves_source_family_independence`` is
therefore pinned to ``False`` so no Domain Pack can declare a stronger guarantee
than the runtime can actually enforce.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    sorted_unique,
    validate_slug,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    ClaimGroundingKind,
    IntelligenceResourceMode,
    LineageResourceKind,
)

EPISTEMIC_STATUS_MODULE_VERSION = "ace.intelligence.epistemic-status/v1alpha1"
EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION = "ace.intelligence.epistemic-status/v1alpha2"
EPISTEMIC_STATUS_DECLARATION_V1ALPHA2_VERSION = "ace.intelligence.epistemic-status-declaration/v1alpha2"
EPISTEMIC_STATUS_SET_V1ALPHA2_VERSION = "ace.intelligence.epistemic-status-set/v1alpha2"
BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_V1ALPHA2_VERSION = "ace.intelligence.brief-claim-epistemic-status-binding/v1alpha2"
BRIEF_EPISTEMIC_STATUS_PROJECTION_V1ALPHA2_VERSION = "ace.intelligence.brief-epistemic-status-projection/v1alpha2"
DERIVATION_FAMILY_MEMBERSHIP_VERSION = "ace.intelligence.derivation-family-membership/v1alpha1"
EPISTEMIC_STATUS_DECLARATION_VERSION = "ace.intelligence.epistemic-status-declaration/v1alpha1"
EPISTEMIC_STATUS_SET_VERSION = "ace.intelligence.epistemic-status-set/v1alpha1"
BRIEF_DRAFT_CLAIM_STATUS_BINDING_VERSION = "ace.intelligence.brief-draft-claim-status-binding/v1alpha1"
BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION = "ace.intelligence.brief-synthesis-draft/v1alpha2"
BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_VERSION = "ace.intelligence.brief-claim-epistemic-status-binding/v1alpha1"
BRIEF_EPISTEMIC_STATUS_PROJECTION_VERSION = "ace.intelligence.brief-epistemic-status-projection/v1alpha1"

#: Durable record kind for the sibling status projection.
BRIEF_EPISTEMIC_STATUS_PROJECTION_KIND = "brief_epistemic_status_projection"

#: Durable record kind for the family-aware sibling status projection. It is a
#: distinct kind so a single record kind never mixes payload contracts.
BRIEF_DERIVATION_FAMILY_STATUS_PROJECTION_KIND = "brief_derivation_family_status_projection"

MAX_STATUSES = 32
MAX_STATUS_KINDS = len(LineageResourceKind)


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
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:") or value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    return value


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact epistemic material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact epistemic material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


def _ordered_grounding_kinds(value: Any) -> tuple[ClaimGroundingKind, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("allowed grounding kinds must be an ordered collection")
    kinds = tuple(ClaimGroundingKind(item) for item in value)
    if not kinds or len(kinds) != len(set(kinds)):
        raise ValueError("allowed grounding kinds must be a non-empty unique set")
    return tuple(sorted(kinds, key=lambda item: item.value))


def _ordered_resource_kinds(value: Any, *, name: str, allow_empty: bool) -> tuple[LineageResourceKind, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an ordered collection")
    kinds = tuple(LineageResourceKind(item) for item in value)
    if len(kinds) != len(set(kinds)):
        raise ValueError(f"{name} must be unique")
    if not allow_empty and not kinds:
        raise ValueError(f"{name} must not be empty")
    if len(kinds) > MAX_STATUS_KINDS:
        raise ValueError(f"{name} exceeds the supported resource-kind bound")
    return tuple(sorted(kinds, key=lambda item: item.value))


# -- Domain-declared vocabulary -----------------------------------------------


class EpistemicStatusDeclarationV1(FrozenContract):
    """One domain-declared status label plus the generic facts ACE will enforce.

    The label itself is opaque to ACE. Only the surrounding constraints are
    interpreted, and only against domain-neutral support facts.
    """

    contract: Literal["ace.intelligence.epistemic-status-declaration/v1alpha1"] = EPISTEMIC_STATUS_DECLARATION_VERSION
    status_id: str
    display_name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=2_000)
    allowed_grounding_kinds: tuple[ClaimGroundingKind, ...] = Field(min_length=1, max_length=2)
    allowed_support_kinds: tuple[LineageResourceKind, ...] = Field(min_length=1)
    required_support_kinds: tuple[LineageResourceKind, ...] = Field(default_factory=tuple)
    min_support_count: int = Field(default=1, ge=1, le=256)
    max_support_count: int | None = Field(default=None, ge=1, le=256)
    min_distinct_support_kinds: int = Field(default=1, ge=1, le=MAX_STATUS_KINDS)
    requires_uncertainty: StrictBool = False
    #: ACE cannot prove independent source families until a public
    #: derivation-family predicate exists. Pinned so a Pack cannot overclaim.
    proves_source_family_independence: Literal[False] = False

    @field_validator("status_id")
    @classmethod
    def validate_status_id(cls, value: str) -> str:
        return validate_slug(value, name="status_id")

    @field_validator("allowed_grounding_kinds", mode="before")
    @classmethod
    def normalize_grounding_kinds(cls, value: Any) -> tuple[ClaimGroundingKind, ...]:
        return _ordered_grounding_kinds(value)

    @field_validator("allowed_support_kinds", mode="before")
    @classmethod
    def normalize_allowed_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="allowed_support_kinds", allow_empty=False)

    @field_validator("required_support_kinds", mode="before")
    @classmethod
    def normalize_required_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="required_support_kinds", allow_empty=True)

    @model_validator(mode="after")
    def validate_constraint_coherence(self) -> Self:
        if self.max_support_count is not None and self.max_support_count < self.min_support_count:
            raise ValueError("max_support_count must not be below min_support_count")
        if not set(self.required_support_kinds) <= set(self.allowed_support_kinds):
            raise ValueError("required support kinds must be a subset of allowed support kinds")
        if self.min_distinct_support_kinds > len(self.allowed_support_kinds):
            raise ValueError("min_distinct_support_kinds exceeds the declared allowed support kinds")
        if self.min_distinct_support_kinds > self.min_support_count:
            raise ValueError("min_distinct_support_kinds cannot exceed min_support_count")
        if len(self.required_support_kinds) > self.min_support_count:
            raise ValueError("required support kinds cannot exceed min_support_count")
        if ClaimGroundingKind.CITED in self.allowed_grounding_kinds and self.requires_uncertainty:
            raise ValueError("a cited-capable status cannot require an inference uncertainty statement")
        return self


class EpistemicStatusSetV1(FrozenContract):
    """One bounded status vocabulary bound to exact Brief templates."""

    contract: Literal["ace.intelligence.epistemic-status-set/v1alpha1"] = EPISTEMIC_STATUS_SET_VERSION
    status_set_id: str
    display_name: str = Field(min_length=1, max_length=160)
    brief_template_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    require_status_for_every_claim: StrictBool = True
    statuses: tuple[EpistemicStatusDeclarationV1, ...] = Field(min_length=1, max_length=MAX_STATUSES)

    @field_validator("status_set_id")
    @classmethod
    def validate_status_set_id(cls, value: str) -> str:
        return validate_slug(value, name="status_set_id")

    @field_validator("brief_template_ids", mode="before")
    @classmethod
    def normalize_template_ids(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("brief_template_ids must be an ordered collection")
        validated = tuple(validate_slug(item, name="brief_template_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("brief_template_ids must be unique")
        return tuple(sorted(validated))

    @field_validator("statuses")
    @classmethod
    def normalize_statuses(
        cls,
        value: tuple[EpistemicStatusDeclarationV1, ...],
    ) -> tuple[EpistemicStatusDeclarationV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.status_id,
            label="epistemic statuses",
            maximum=MAX_STATUSES,
        )

    @model_validator(mode="after")
    def require_status_coverage(self) -> Self:
        if not self.require_status_for_every_claim:
            raise ValueError("an epistemic status set must require one declared status for every claim")
        return self


class EpistemicStatusModuleV1(FrozenContract):
    """One immutable declarative module of domain-owned status vocabularies."""

    contract: Literal["ace.intelligence.epistemic-status/v1alpha1"] = EPISTEMIC_STATUS_MODULE_VERSION
    module_id: str
    status_sets: tuple[EpistemicStatusSetV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("status_sets")
    @classmethod
    def normalize_status_sets(cls, value: tuple[EpistemicStatusSetV1, ...]) -> tuple[EpistemicStatusSetV1, ...]:
        return sorted_unique(value, key=lambda item: item.status_set_id, label="epistemic status sets")


class EpistemicStatusDeclarationV1Alpha2(FrozenContract):
    """A status declaration that may additionally require independent families.

    This is the additive sibling of :class:`EpistemicStatusDeclarationV1`. It
    adds exactly one constraint: ``min_distinct_derivation_families``. A Pack
    that does not raise that value above ``1`` behaves precisely as it did under
    ``v1alpha1``, and a Pack that stays on ``v1alpha1`` is untouched.

    Unlike ``v1alpha1`` -- where ``proves_source_family_independence`` is pinned
    to ``False`` because the runtime could not establish it --
    ``v1alpha2`` *derives* that flag and refuses to let a Pack state it
    incorrectly in either direction.
    """

    contract: Literal["ace.intelligence.epistemic-status-declaration/v1alpha2"] = (
        EPISTEMIC_STATUS_DECLARATION_V1ALPHA2_VERSION
    )
    status_id: str
    display_name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=2_000)
    allowed_grounding_kinds: tuple[ClaimGroundingKind, ...] = Field(min_length=1, max_length=2)
    allowed_support_kinds: tuple[LineageResourceKind, ...] = Field(min_length=1)
    required_support_kinds: tuple[LineageResourceKind, ...] = Field(default_factory=tuple)
    min_support_count: int = Field(default=1, ge=1, le=256)
    max_support_count: int | None = Field(default=None, ge=1, le=256)
    min_distinct_support_kinds: int = Field(default=1, ge=1, le=MAX_STATUS_KINDS)
    #: Minimum number of distinct *derived* Observation families the supports
    #: must span. ``1`` means no independence requirement at all.
    min_distinct_derivation_families: int = Field(default=1, ge=1, le=256)
    requires_uncertainty: StrictBool = False
    proves_source_family_independence: StrictBool = False

    @field_validator("status_id")
    @classmethod
    def validate_status_id(cls, value: str) -> str:
        return validate_slug(value, name="status_id")

    @field_validator("allowed_grounding_kinds", mode="before")
    @classmethod
    def normalize_grounding_kinds(cls, value: Any) -> tuple[ClaimGroundingKind, ...]:
        return _ordered_grounding_kinds(value)

    @field_validator("allowed_support_kinds", mode="before")
    @classmethod
    def normalize_allowed_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="allowed_support_kinds", allow_empty=False)

    @field_validator("required_support_kinds", mode="before")
    @classmethod
    def normalize_required_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="required_support_kinds", allow_empty=True)

    @model_validator(mode="after")
    def validate_constraint_coherence(self) -> Self:
        if self.max_support_count is not None and self.max_support_count < self.min_support_count:
            raise ValueError("max_support_count must not be below min_support_count")
        if not set(self.required_support_kinds) <= set(self.allowed_support_kinds):
            raise ValueError("required support kinds must be a subset of allowed support kinds")
        if self.min_distinct_support_kinds > len(self.allowed_support_kinds):
            raise ValueError("min_distinct_support_kinds exceeds the declared allowed support kinds")
        if self.min_distinct_support_kinds > self.min_support_count:
            raise ValueError("min_distinct_support_kinds cannot exceed min_support_count")
        if len(self.required_support_kinds) > self.min_support_count:
            raise ValueError("required support kinds cannot exceed min_support_count")
        if ClaimGroundingKind.CITED in self.allowed_grounding_kinds and self.requires_uncertainty:
            raise ValueError("a cited-capable status cannot require an inference uncertainty statement")
        if self.min_distinct_derivation_families > self.min_support_count:
            raise ValueError("min_distinct_derivation_families cannot exceed min_support_count")
        if self.min_distinct_derivation_families > 1 and tuple(self.allowed_support_kinds) != (
            LineageResourceKind.OBSERVATION,
        ):
            # Families are derived only over admitted Observation lineage, so a
            # status that demands independent families must admit nothing else.
            raise ValueError("a status requiring distinct derivation families must allow only observation supports")
        expected_independence = self.min_distinct_derivation_families >= 2
        if self.proves_source_family_independence is not expected_independence:
            raise ValueError(
                "proves_source_family_independence must equal whether the status requires "
                "at least two distinct derivation families"
            )
        return self


class EpistemicStatusSetV1Alpha2(FrozenContract):
    """A bounded status vocabulary whose statuses may require family independence."""

    contract: Literal["ace.intelligence.epistemic-status-set/v1alpha2"] = EPISTEMIC_STATUS_SET_V1ALPHA2_VERSION
    status_set_id: str
    display_name: str = Field(min_length=1, max_length=160)
    brief_template_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    require_status_for_every_claim: StrictBool = True
    statuses: tuple[EpistemicStatusDeclarationV1Alpha2, ...] = Field(
        min_length=1,
        max_length=MAX_STATUSES,
    )

    @field_validator("status_set_id")
    @classmethod
    def validate_status_set_id(cls, value: str) -> str:
        return validate_slug(value, name="status_set_id")

    @field_validator("brief_template_ids", mode="before")
    @classmethod
    def normalize_template_ids(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("brief_template_ids must be an ordered collection")
        validated = tuple(validate_slug(item, name="brief_template_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("brief_template_ids must be unique")
        return tuple(sorted(validated))

    @field_validator("statuses")
    @classmethod
    def normalize_statuses(
        cls,
        value: tuple[EpistemicStatusDeclarationV1Alpha2, ...],
    ) -> tuple[EpistemicStatusDeclarationV1Alpha2, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.status_id,
            label="epistemic statuses",
            maximum=MAX_STATUSES,
        )

    @model_validator(mode="after")
    def require_status_coverage(self) -> Self:
        if not self.require_status_for_every_claim:
            raise ValueError("an epistemic status set must require one declared status for every claim")
        return self


class EpistemicStatusModuleV1Alpha2(FrozenContract):
    """Declarative module of status vocabularies that may require independence."""

    contract: Literal["ace.intelligence.epistemic-status/v1alpha2"] = EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION
    module_id: str
    status_sets: tuple[EpistemicStatusSetV1Alpha2, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("status_sets")
    @classmethod
    def normalize_status_sets(
        cls,
        value: tuple[EpistemicStatusSetV1Alpha2, ...],
    ) -> tuple[EpistemicStatusSetV1Alpha2, ...]:
        return sorted_unique(value, key=lambda item: item.status_set_id, label="epistemic status sets")


# -- Structured provider output ------------------------------------------------


class BriefDraftClaimStatusBindingV1Alpha1(_StrictFrozenContract):
    """One draft claim identity bound to exactly one declared status label."""

    contract: Literal["ace.intelligence.brief-draft-claim-status-binding/v1alpha1"] = (
        BRIEF_DRAFT_CLAIM_STATUS_BINDING_VERSION
    )
    draft_claim_id: str
    status_id: str

    @field_validator("draft_claim_id")
    @classmethod
    def validate_draft_claim_id(cls, value: str) -> str:
        return _reference(value, name="draft_claim_id")

    @field_validator("status_id")
    @classmethod
    def validate_status_id(cls, value: str) -> str:
        return validate_slug(value, name="status_id")


# -- Durable per-claim projection ---------------------------------------------


class BriefClaimEpistemicStatusBindingV1Alpha1(_StrictFrozenContract):
    """Content-free per-statement status plus the exact facts that admitted it.

    ``support_record_ids``/``support_kinds``/``support_count`` are the reproduced
    domain-neutral evidence ACE actually checked. They make the status decision
    auditable without re-reading the Brief body or its Markdown.
    """

    contract: Literal["ace.intelligence.brief-claim-epistemic-status-binding/v1alpha1"] = (
        BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_VERSION
    )
    claim_id: str
    status_id: str
    grounding_kind: ClaimGroundingKind
    support_record_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    support_kinds: tuple[LineageResourceKind, ...] = Field(min_length=1)
    support_count: int = Field(ge=1, le=256)
    carries_uncertainty: StrictBool

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        return _reference(value, name="claim_id")

    @field_validator("status_id")
    @classmethod
    def validate_status_id(cls, value: str) -> str:
        return validate_slug(value, name="status_id")

    @field_validator("support_record_ids")
    @classmethod
    def normalize_support_record_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="support_record_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("claim status support identities must be unique")
        return tuple(sorted(validated))

    @field_validator("support_kinds", mode="before")
    @classmethod
    def normalize_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="support_kinds", allow_empty=False)

    @model_validator(mode="after")
    def validate_support_shape(self) -> Self:
        if self.support_count != len(self.support_record_ids):
            raise ValueError("claim status support_count must equal its exact bound support identities")
        if self.grounding_kind is ClaimGroundingKind.CITED and self.carries_uncertainty:
            raise ValueError("a cited claim status must not report an inference uncertainty statement")
        return self


class BriefEpistemicStatusProjectionV1Alpha1(_StrictFrozenContract):
    """Durable sibling projection binding one exact Brief's claims to statuses.

    This is deliberately a *sibling* record rather than a field on
    ``ace.intelligence.brief/v1alpha1`` or on any synthesis receipt: those
    contracts derive their identity from their canonical payload, so extending
    them would silently re-key every historical artifact. The projection instead
    names the exact Brief and the exact synthesis receipt it explains.
    """

    contract: Literal["ace.intelligence.brief-epistemic-status-projection/v1alpha1"] = (
        BRIEF_EPISTEMIC_STATUS_PROJECTION_VERSION
    )
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    brief_id: str
    brief_digest: str
    synthesis_receipt_contract: str
    synthesis_receipt_id: str
    synthesis_receipt_digest: str
    module_id: str
    module_digest: str
    status_set_id: str
    status_set_digest: str
    template_id: str
    declared_status_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_STATUSES)
    claim_statuses: tuple[BriefClaimEpistemicStatusBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    as_of: datetime
    generated_at: datetime
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator(
        "product_id",
        "brief_id",
        "synthesis_receipt_contract",
        "synthesis_receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator(
        "brief_digest",
        "synthesis_receipt_digest",
        "module_digest",
        "status_set_digest",
        "projection_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("module_id", "status_set_id", "template_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("declared_status_ids")
    @classmethod
    def normalize_declared_status_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="declared_status_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("declared status identities must be unique")
        return tuple(sorted(validated))

    @field_validator("as_of", "generated_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("projection_id")
    @classmethod
    def validate_projection_id(cls, value: str | None) -> str | None:
        return _reference(value, name="projection_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("status projection crossed exact product scope")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("status projection must bind one exact Brief identity")
        if self.as_of > self.generated_at:
            raise ValueError("status projection as_of must not follow its generation time")
        claim_ids = tuple(item.claim_id for item in self.claim_statuses)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("status projection must bind each exact claim at most once")
        declared = set(self.declared_status_ids)
        if any(item.status_id not in declared for item in self.claim_statuses):
            raise ValueError("status projection used a status outside the declared vocabulary")
        _derive_identity(
            self,
            prefix="brief_epistemic_status_projection",
            id_field="projection_id",
            digest_field="projection_digest",
        )
        return self


class DerivationFamilyMembershipV1Alpha1(_StrictFrozenContract):
    """One derived family: its exact root and its exact sorted members.

    This is the durable, inspectable form of
    :attr:`~ace.intelligence.derivation.DerivationFamilyClosure.members_by_root`.
    Disclosing roots alone would not let an auditor check *which* records
    collapsed into which origin, so the membership is carried explicitly.
    """

    contract: Literal["ace.intelligence.derivation-family-membership/v1alpha1"] = DERIVATION_FAMILY_MEMBERSHIP_VERSION
    root_record_id: str
    member_record_ids: tuple[str, ...] = Field(min_length=1, max_length=1_024)

    @field_validator("root_record_id")
    @classmethod
    def validate_root(cls, value: str) -> str:
        return _reference(value, name="root_record_id")

    @field_validator("member_record_ids")
    @classmethod
    def normalize_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_reference(item, name="member_record_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("derivation family members must be unique")
        return tuple(sorted(validated))

    @model_validator(mode="after")
    def validate_membership(self) -> Self:
        if self.root_record_id not in self.member_record_ids:
            raise ValueError("a derivation family must contain its own root")
        return self


class BriefClaimEpistemicStatusBindingV1Alpha2(_StrictFrozenContract):
    """Per-statement status plus the exact derivation-family proof behind it.

    The additive sibling of :class:`BriefClaimEpistemicStatusBindingV1Alpha1`.
    It discloses the exact family roots the supports collapsed to and the
    requirement that was applied, so an auditor can re-derive the independence
    decision without re-reading the Brief or trusting the label.
    """

    contract: Literal["ace.intelligence.brief-claim-epistemic-status-binding/v1alpha2"] = (
        BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_V1ALPHA2_VERSION
    )
    claim_id: str
    status_id: str
    grounding_kind: ClaimGroundingKind
    support_record_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    support_kinds: tuple[LineageResourceKind, ...] = Field(min_length=1)
    support_count: int = Field(ge=1, le=256)
    carries_uncertainty: StrictBool
    #: Exact distinct family roots the Observation supports collapsed to, sorted.
    #: Empty when the claim has no Observation supports at all, which is legal
    #: for a status that requires no independence.
    derivation_family_roots: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    distinct_derivation_family_count: int = Field(ge=0, le=256)
    required_distinct_derivation_families: int = Field(ge=1, le=256)

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        return _reference(value, name="claim_id")

    @field_validator("status_id")
    @classmethod
    def validate_status_id(cls, value: str) -> str:
        return validate_slug(value, name="status_id")

    @field_validator("support_record_ids", "derivation_family_roots")
    @classmethod
    def normalize_identity_sets(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(_reference(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must use unique exact identities")
        return tuple(sorted(validated))

    @field_validator("support_kinds", mode="before")
    @classmethod
    def normalize_support_kinds(cls, value: Any) -> tuple[LineageResourceKind, ...]:
        return _ordered_resource_kinds(value, name="support_kinds", allow_empty=False)

    @model_validator(mode="after")
    def validate_support_and_family_shape(self) -> Self:
        if self.support_count != len(self.support_record_ids):
            raise ValueError("claim status support_count must equal its exact bound support identities")
        if self.grounding_kind is ClaimGroundingKind.CITED and self.carries_uncertainty:
            raise ValueError("a cited claim status must not report an inference uncertainty statement")
        if self.distinct_derivation_family_count != len(self.derivation_family_roots):
            raise ValueError("distinct_derivation_family_count must equal the exact disclosed family roots")
        if self.distinct_derivation_family_count > self.support_count:
            raise ValueError("a claim cannot span more families than it has supports")
        # ``required == 1`` means "no independence requirement": a claim grounded
        # only on non-Observation resources legitimately has no family at all.
        # A root is deliberately NOT required to be one of the claim's supports,
        # because collapsing resolves a syndicated support to an origin the
        # claim never cited.
        if (
            self.required_distinct_derivation_families > 1
            and self.distinct_derivation_family_count < self.required_distinct_derivation_families
        ):
            raise ValueError("claim supports do not span the required number of distinct derivation families")
        return self


class BriefEpistemicStatusProjectionV1Alpha2(_StrictFrozenContract):
    """Durable status projection that also discloses derivation-family proof.

    Additive sibling of :class:`BriefEpistemicStatusProjectionV1Alpha1`; the
    ``v1alpha1`` record is untouched, so every artifact already written under it
    keeps its exact identity.
    """

    contract: Literal["ace.intelligence.brief-epistemic-status-projection/v1alpha2"] = (
        BRIEF_EPISTEMIC_STATUS_PROJECTION_V1ALPHA2_VERSION
    )
    product_id: str
    mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED
    activation_revision: ActivationRevisionReferenceV1Alpha1
    brief_id: str
    brief_digest: str
    synthesis_receipt_contract: str
    synthesis_receipt_id: str
    synthesis_receipt_digest: str
    module_id: str
    module_digest: str
    status_set_id: str
    status_set_digest: str
    template_id: str
    declared_status_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_STATUSES)
    claim_statuses: tuple[BriefClaimEpistemicStatusBindingV1Alpha2, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    #: The exact predicate that produced every family root above.
    derivation_family_policy: str
    #: The exact lineage relations that collapsed a record into its parent.
    collapsing_relations: tuple[str, ...] = Field(min_length=1, max_length=8)
    #: Full family assignment of the closure: every root and its exact members,
    #: so the independence decision is re-derivable from the record alone.
    closure_families: tuple[DerivationFamilyMembershipV1Alpha1, ...] = Field(
        min_length=1,
        max_length=1_024,
    )
    as_of: datetime
    generated_at: datetime
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator(
        "product_id",
        "brief_id",
        "synthesis_receipt_contract",
        "synthesis_receipt_id",
        "derivation_family_policy",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _reference(value, name=info.field_name)

    @field_validator(
        "brief_digest",
        "synthesis_receipt_digest",
        "module_digest",
        "status_set_digest",
        "projection_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("module_id", "status_set_id", "template_id")
    @classmethod
    def validate_slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("declared_status_ids")
    @classmethod
    def normalize_declared_status_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_slug(item, name="declared_status_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("declared status identities must be unique")
        return tuple(sorted(validated))

    @field_validator("collapsing_relations")
    @classmethod
    def normalize_sorted_unique(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(_reference(item, name=info.field_name) for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must be unique")
        return tuple(sorted(validated))

    @field_validator("closure_families")
    @classmethod
    def normalize_closure_families(
        cls,
        value: tuple[DerivationFamilyMembershipV1Alpha1, ...],
    ) -> tuple[DerivationFamilyMembershipV1Alpha1, ...]:
        roots = [item.root_record_id for item in value]
        if len(roots) != len(set(roots)):
            raise ValueError("each derivation family root must appear exactly once")
        members = [member for item in value for member in item.member_record_ids]
        if len(members) != len(set(members)):
            raise ValueError("derivation families must not overlap on any member")
        return tuple(sorted(value, key=lambda item: item.root_record_id))

    @field_validator("as_of", "generated_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("projection_id")
    @classmethod
    def validate_projection_id(cls, value: str | None) -> str | None:
        return _reference(value, name="projection_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("status projection crossed exact product scope")
        if not self.brief_id.startswith("brief:"):
            raise ValueError("status projection must bind one exact Brief identity")
        if self.as_of > self.generated_at:
            raise ValueError("status projection as_of must not follow its generation time")
        claim_ids = tuple(item.claim_id for item in self.claim_statuses)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("status projection must bind each exact claim at most once")
        declared = set(self.declared_status_ids)
        if any(item.status_id not in declared for item in self.claim_statuses):
            raise ValueError("status projection used a status outside the declared vocabulary")
        closure_roots = {item.root_record_id for item in self.closure_families}
        closure_members = {member for item in self.closure_families for member in item.member_record_ids}
        for item in self.claim_statuses:
            if not set(item.derivation_family_roots) <= closure_roots:
                raise ValueError("a claim discloses a family root outside the exact closure family assignment")
            observation_supports = set(item.support_record_ids) & closure_members
            if item.derivation_family_roots and not observation_supports:
                raise ValueError("a claim discloses family roots but names no member of any closure family")
        _derive_identity(
            self,
            prefix="brief_derivation_family_status_projection",
            id_field="projection_id",
            digest_field="projection_digest",
        )
        return self


__all__ = [
    "BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_VERSION",
    "BRIEF_CLAIM_EPISTEMIC_STATUS_BINDING_V1ALPHA2_VERSION",
    "BRIEF_DERIVATION_FAMILY_STATUS_PROJECTION_KIND",
    "BRIEF_EPISTEMIC_STATUS_PROJECTION_V1ALPHA2_VERSION",
    "EPISTEMIC_STATUS_DECLARATION_V1ALPHA2_VERSION",
    "EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION",
    "EPISTEMIC_STATUS_SET_V1ALPHA2_VERSION",
    "DERIVATION_FAMILY_MEMBERSHIP_VERSION",
    "DerivationFamilyMembershipV1Alpha1",
    "BriefClaimEpistemicStatusBindingV1Alpha2",
    "BriefEpistemicStatusProjectionV1Alpha2",
    "EpistemicStatusDeclarationV1Alpha2",
    "EpistemicStatusModuleV1Alpha2",
    "EpistemicStatusSetV1Alpha2",
    "BRIEF_DRAFT_CLAIM_STATUS_BINDING_VERSION",
    "BRIEF_EPISTEMIC_STATUS_PROJECTION_KIND",
    "BRIEF_EPISTEMIC_STATUS_PROJECTION_VERSION",
    "BRIEF_SYNTHESIS_DRAFT_V1ALPHA2_VERSION",
    "EPISTEMIC_STATUS_DECLARATION_VERSION",
    "EPISTEMIC_STATUS_MODULE_VERSION",
    "EPISTEMIC_STATUS_SET_VERSION",
    "BriefClaimEpistemicStatusBindingV1Alpha1",
    "BriefDraftClaimStatusBindingV1Alpha1",
    "BriefEpistemicStatusProjectionV1Alpha1",
    "EpistemicStatusDeclarationV1",
    "EpistemicStatusModuleV1",
    "EpistemicStatusSetV1",
]
