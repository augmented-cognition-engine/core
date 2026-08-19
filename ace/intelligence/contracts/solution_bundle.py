"""Solution Bundle manifest, resolution receipt, and activation revision contracts.

A Solution Bundle composes one exact pack, overlay, adapter set, Atrium-module
set, and policy into one deterministically resolvable unit (packet Decision
1). These contracts are domain-neutral: no field, identifier, or branch here
names Personal Intelligence or any other specific bundle. A concrete bundle
(Personal Intelligence, Code Intelligence, ...) is only ever a *value* of
these contracts, constructed outside ``ace/core`` and ``ace/intelligence``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    sorted_unique,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
    validate_version,
)

SOLUTION_BUNDLE_MANIFEST_VERSION = "ace.intelligence.solution-bundle-manifest/v1alpha1"
SOLUTION_BUNDLE_RESOLUTION_RECEIPT_VERSION = "ace.intelligence.solution-bundle-resolution-receipt/v1alpha1"
SOLUTION_BUNDLE_ACTIVATION_REVISION_VERSION = "ace.intelligence.solution-bundle-activation-revision/v1alpha1"


class AdapterBindingV1(FrozenContract):
    """One exact, independently versioned adapter artifact bound by a bundle (Decision 3)."""

    adapter_id: str
    adapter_version: str
    artifact_digest: str

    @field_validator("adapter_id")
    @classmethod
    def validate_adapter_id(cls, value: str) -> str:
        return validate_slug(value, name="adapter_id")

    @field_validator("adapter_version")
    @classmethod
    def validate_adapter_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return validate_digest(value)


class AtriumModuleBindingV1(FrozenContract):
    """One exact, independently versioned Atrium-module artifact bound by a bundle."""

    module_id: str
    module_version: str
    artifact_digest: str

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("module_version")
    @classmethod
    def validate_module_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("artifact_digest")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return validate_digest(value)


class PolicyBindingV1(FrozenContract):
    """One exact, independently versioned policy bound by a bundle."""

    policy_id: str
    policy_version: str
    policy_digest: str

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, value: str) -> str:
        return validate_slug(value, name="policy_id")

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("policy_digest")
    @classmethod
    def validate_policy_digest(cls, value: str) -> str:
        return validate_digest(value)


class SolutionBundleManifestV1(FrozenContract):
    """Exact pack, overlay, adapter, Atrium-module, and policy bindings for one bundle."""

    contract: Literal["ace.intelligence.solution-bundle-manifest/v1alpha1"] = SOLUTION_BUNDLE_MANIFEST_VERSION
    product_id: str = Field(min_length=1, max_length=240)
    bundle_id: str
    bundle_version: str
    pack: CompiledPackRefV1
    overlay: CompiledOverlayV1
    adapters: tuple[AdapterBindingV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    atrium_modules: tuple[AtriumModuleBindingV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    policy: PolicyBindingV1
    manifest_id: str | None = None
    manifest_hash: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("bundle_id")
    @classmethod
    def validate_bundle_id(cls, value: str) -> str:
        return validate_slug(value, name="bundle_id")

    @field_validator("bundle_version")
    @classmethod
    def validate_bundle_version(cls, value: str) -> str:
        return validate_version(value)

    @field_validator("adapters")
    @classmethod
    def normalize_adapters(cls, value: tuple[AdapterBindingV1, ...]) -> tuple[AdapterBindingV1, ...]:
        return sorted_unique(value, key=lambda item: item.adapter_id, label="adapter bindings")

    @field_validator("atrium_modules")
    @classmethod
    def normalize_atrium_modules(cls, value: tuple[AtriumModuleBindingV1, ...]) -> tuple[AtriumModuleBindingV1, ...]:
        return sorted_unique(value, key=lambda item: item.module_id, label="Atrium module bindings")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.overlay.pack_id != self.pack.pack_id or self.overlay.pack_version != self.pack.pack_version:
            raise ValueError("overlay must target the exact compiled pack identity and version")
        if self.overlay.pack_digest != self.pack.pack_digest:
            raise ValueError("overlay must target the exact compiled pack digest")
        material = self.model_dump(mode="json", exclude={"manifest_id", "manifest_hash"})
        digest = canonical_hash(material)
        expected_id = f"solution_bundle_manifest:{digest[:32]}"
        expected_hash = f"sha256:{digest}"
        if self.manifest_id is not None and self.manifest_id != expected_id:
            raise ValueError("solution bundle manifest identity does not match exact material")
        if self.manifest_hash is not None and self.manifest_hash != expected_hash:
            raise ValueError("solution bundle manifest hash does not match exact material")
        object.__setattr__(self, "manifest_id", expected_id)
        object.__setattr__(self, "manifest_hash", expected_hash)
        return self


class SolutionBundleResolutionReceiptV1(FrozenContract):
    """Deterministic, side-effect-free resolution of one exact bundle manifest.

    Pure derivation of the manifest's material: the same manifest always
    resolves to a byte-identical receipt. ``authority_stage`` is baked into
    the published schema as a non-overridable constant so resolution can
    never be mistaken for a live activation authority.
    """

    contract: Literal["ace.intelligence.solution-bundle-resolution-receipt/v1alpha1"] = (
        SOLUTION_BUNDLE_RESOLUTION_RECEIPT_VERSION
    )
    authority_stage: Literal["resolved"] = "resolved"
    manifest: SolutionBundleManifestV1
    bundle_state_id: str | None = None
    resolution_id: str | None = None
    resolution_hash: str | None = None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.manifest.manifest_id is None or self.manifest.manifest_hash is None:
            raise ValueError("resolution receipt requires an exact derived manifest identity")
        expected_state_id = (
            f"solution_bundle:{canonical_hash([self.manifest.product_id, self.manifest.bundle_id])[:32]}"
        )
        if self.bundle_state_id is not None and self.bundle_state_id != expected_state_id:
            raise ValueError("resolution receipt bundle state identity does not match exact scope")
        object.__setattr__(self, "bundle_state_id", expected_state_id)
        material = self.model_dump(mode="json", exclude={"resolution_id", "resolution_hash"})
        digest = canonical_hash(material)
        expected_id = f"solution_bundle_resolution:{digest[:32]}"
        expected_hash = f"sha256:{digest}"
        if self.resolution_id is not None and self.resolution_id != expected_id:
            raise ValueError("resolution receipt identity does not match exact material")
        if self.resolution_hash is not None and self.resolution_hash != expected_hash:
            raise ValueError("resolution receipt hash does not match exact material")
        object.__setattr__(self, "resolution_id", expected_id)
        object.__setattr__(self, "resolution_hash", expected_hash)
        return self


class BundleActivationAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class BundleActivationRuntimeState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class SolutionBundleActivationRevisionV1(FrozenContract):
    """One append-only Solution Bundle activation transition.

    Mirrors :class:`~ace.intelligence.contracts.activation.DomainActivationRevisionV1`:
    persistence and atomic admission remain an Application/Core concern; this
    contract only states one exact, self-validating transition.
    """

    contract: Literal["ace.intelligence.solution-bundle-activation-revision/v1alpha1"] = (
        SOLUTION_BUNDLE_ACTIVATION_REVISION_VERSION
    )
    activation_id: str | None = None
    revision: StrictInt = Field(ge=1)
    manifest: SolutionBundleManifestV1
    resolution_receipt: SolutionBundleResolutionReceiptV1
    action: BundleActivationAction
    state: BundleActivationRuntimeState
    prior_revision_id: str | None = None
    actor_ref: str = Field(min_length=1, max_length=240)
    approval_receipt_ref: str = Field(min_length=1, max_length=240)
    occurred_at: datetime
    revision_id: str | None = None
    revision_hash: str | None = None

    @field_validator("activation_id", "prior_revision_id", "actor_ref", "approval_receipt_ref")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_and_derive(self) -> Self:
        if self.resolution_receipt.manifest != self.manifest:
            raise ValueError("activation revision resolution receipt must resolve the exact bound manifest")
        if self.revision == 1 and self.prior_revision_id is not None:
            raise ValueError("the first bundle activation revision cannot have a prior revision")
        if self.revision > 1 and self.prior_revision_id is None:
            raise ValueError("later bundle activation revisions require a prior revision")
        if self.revision == 1 and self.action is not BundleActivationAction.ACTIVATE:
            raise ValueError("the first bundle activation revision must activate")
        if self.action is BundleActivationAction.ACTIVATE and self.state is not BundleActivationRuntimeState.ACTIVE:
            raise ValueError("an activate action must produce the active state")
        if self.action is BundleActivationAction.DEACTIVATE and self.state is not BundleActivationRuntimeState.RETIRED:
            raise ValueError("a deactivate action must produce the retired state")
        expected_activation_id = str(self.resolution_receipt.bundle_state_id)
        if self.activation_id is not None and self.activation_id != expected_activation_id:
            raise ValueError("bundle activation identity does not match its exact resolved scope")
        material = self.model_dump(mode="json", exclude={"activation_id", "revision_id", "revision_hash"})
        expected_hash = canonical_hash(material)
        expected_revision_id = f"solution_bundle_activation_revision:{expected_hash[:32]}"
        if self.revision_id is not None and self.revision_id != expected_revision_id:
            raise ValueError("bundle activation revision identity does not match exact material")
        if self.revision_hash is not None and self.revision_hash != expected_hash:
            raise ValueError("bundle activation revision hash does not match exact material")
        object.__setattr__(self, "activation_id", expected_activation_id)
        object.__setattr__(self, "revision_id", expected_revision_id)
        object.__setattr__(self, "revision_hash", expected_hash)
        return self


__all__ = [
    "SOLUTION_BUNDLE_MANIFEST_VERSION",
    "SOLUTION_BUNDLE_RESOLUTION_RECEIPT_VERSION",
    "SOLUTION_BUNDLE_ACTIVATION_REVISION_VERSION",
    "AdapterBindingV1",
    "AtriumModuleBindingV1",
    "BundleActivationAction",
    "BundleActivationRuntimeState",
    "PolicyBindingV1",
    "SolutionBundleActivationRevisionV1",
    "SolutionBundleManifestV1",
    "SolutionBundleResolutionReceiptV1",
]
