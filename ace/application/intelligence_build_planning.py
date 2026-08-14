"""Public, authority-neutral contracts for reviewing an Intelligence build plan.

Planning is deliberately separate from execution.  An installed planner may
interpret one inert onboarding profile and its exact compiled Pack, but it
cannot connect sources, write records, activate a Pack, mint approval, or call
the governed build executor through this interface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    IntelligenceBuildEffect,
    RecordedSourceReferenceV1,
)
from ace.application.recorded_source_selection import (
    RecordedSourceSelectionReferenceV1Alpha1,
    RecordedSourceSelectionV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1, DomainActivationSpecV1
from ace.intelligence.contracts.common import validate_digest, validate_reference
from ace.intelligence.contracts.intelligence_builder_presentation import IntelligenceOnboardingProfileV1Alpha1
from ace.intelligence.contracts.pack import CompiledDomainPackV1

INTELLIGENCE_BUILD_PLANNER_CONTRACT = "ace.application.intelligence-build-planner/v1alpha1"
INTELLIGENCE_BUILD_PLAN_REQUEST_VERSION = "ace.application.intelligence-build-plan-request/v1alpha1"
INTELLIGENCE_BUILD_PLAN_VERSION = "ace.application.intelligence-build-plan/v1alpha1"
INTELLIGENCE_BUILD_PLANNING_CAPABILITY = "intelligence_build_planning"
INTELLIGENCE_BUILD_PLANNER_V1ALPHA2_CONTRACT = "ace.application.intelligence-build-planner/v1alpha2"
INTELLIGENCE_BUILD_PLAN_REQUEST_V1ALPHA2_VERSION = "ace.application.intelligence-build-plan-request/v1alpha2"
INTELLIGENCE_BUILD_PLAN_V1ALPHA2_VERSION = "ace.application.intelligence-build-plan/v1alpha2"


class _PlanningContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def intelligence_build_execution_identity(
    *,
    product_id: str,
    actor_ref: str,
    request_material: dict,
) -> tuple[str, str]:
    """Derive the established ``/start`` identity without changing its bytes."""

    raw_digest = canonical_hash([product_id, actor_ref, request_material])
    return f"intelligence_build:{raw_digest[:32]}", f"sha256:{raw_digest}"


class IntelligenceBuildPlanRequestV1Alpha1(_PlanningContract):
    """One exact, side-effect-free onboarding selection submitted for review."""

    contract: Literal["ace.application.intelligence-build-plan-request/v1alpha1"] = (
        INTELLIGENCE_BUILD_PLAN_REQUEST_VERSION
    )
    product_id: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    client_request_id: str = Field(min_length=1, max_length=240)
    profile_id: str = Field(min_length=1, max_length=240)
    profile_digest: str
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str = Field(min_length=1, max_length=240)
    source_group_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    recorded_source_refs: tuple[RecordedSourceReferenceV1, ...] = Field(default_factory=tuple, max_length=64)
    cadence_id: str = Field(min_length=1, max_length=240)
    proposed_effects: tuple[IntelligenceBuildEffect, ...] = REQUIRED_INTELLIGENCE_BUILD_EFFECTS
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("product_id", "actor_ref", "client_request_id", "profile_id")
    @classmethod
    def _references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("profile_digest", "request_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("request_id")
    @classmethod
    def _request_ref(cls, value: str | None) -> str | None:
        return validate_reference(value, name="request_id") if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def _aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("source_group_ids")
    @classmethod
    def _unique_source_groups(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_group_ids must be unique")
        return value

    @field_validator("recorded_source_refs")
    @classmethod
    def _exact_recorded_sources(
        cls,
        value: tuple[RecordedSourceReferenceV1, ...],
    ) -> tuple[RecordedSourceReferenceV1, ...]:
        keys = [(item.source_group_id, item.material_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("recorded_source_refs must name each exact recorded material once")
        return tuple(sorted(value, key=lambda item: (item.source_group_id, item.material_id)))

    @field_validator("proposed_effects")
    @classmethod
    def _bounded_effects(cls, value: tuple[IntelligenceBuildEffect, ...]) -> tuple[IntelligenceBuildEffect, ...]:
        if value != REQUIRED_INTELLIGENCE_BUILD_EFFECTS:
            raise ValueError("proposed_effects must preserve the exact bounded onboarding effect sequence")
        return value

    @model_validator(mode="after")
    def _derive_identity(self) -> Self:
        if any(item.source_group_id not in set(self.source_group_ids) for item in self.recorded_source_refs):
            raise ValueError("every recorded source reference must belong to a selected source group")
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_plan_request:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id not in {None, expected_id} or self.request_digest not in {None, expected_digest}:
            raise ValueError("plan request identity does not match exact onboarding material")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self

    def execution_material(self, *, activation_subject_ref: str) -> dict:
        """Return exactly the material hashed by the existing governed ``/start`` route."""

        return {
            "activation_approval_subject_ref": activation_subject_ref,
            "client_request_id": self.client_request_id,
            "profile_id": self.profile_id,
            "subject": self.subject,
            "outcome_id": self.outcome_id,
            "source_group_ids": list(self.source_group_ids),
            "recorded_source_refs": [item.model_dump(mode="json") for item in self.recorded_source_refs],
            "cadence_id": self.cadence_id,
            "approved_effects": list(self.proposed_effects),
            "requested_at": self.requested_at.isoformat().replace("+00:00", "Z"),
        }


class IntelligenceBuildPlanV1Alpha1(_PlanningContract):
    """Exact review material produced without granting or exercising authority."""

    contract: Literal["ace.application.intelligence-build-plan/v1alpha1"] = INTELLIGENCE_BUILD_PLAN_VERSION
    request: IntelligenceBuildPlanRequestV1Alpha1
    planner_artifact: CapabilityArtifactIdentityV1Alpha1
    pack_reference: CompiledPackRefV1
    activation_spec: DomainActivationSpecV1
    recorded_source_refs: tuple[RecordedSourceReferenceV1, ...] = Field(default_factory=tuple, max_length=64)
    execution_request_id: str | None = None
    execution_request_digest: str | None = None
    plan_id: str | None = None
    plan_digest: str | None = None

    @field_validator("execution_request_id", "plan_id")
    @classmethod
    def _references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("execution_request_digest", "plan_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def _bind_exact_plan(self) -> Self:
        if self.planner_artifact.capability != INTELLIGENCE_BUILD_PLANNING_CAPABILITY:
            raise ValueError("planner artifact must declare the Intelligence build planning capability")
        if self.planner_artifact.contract != INTELLIGENCE_BUILD_PLANNER_CONTRACT:
            raise ValueError("planner artifact must implement the exact planning contract")
        if self.activation_spec.product_id != self.request.product_id:
            raise ValueError("activation specification crossed the requested product scope")
        if self.activation_spec.pack != self.pack_reference:
            raise ValueError("activation specification crossed the exact planned Pack")
        if self.recorded_source_refs != self.request.recorded_source_refs:
            raise ValueError("planner changed the exact recorded source selection")
        execution_id, execution_digest = intelligence_build_execution_identity(
            product_id=self.request.product_id,
            actor_ref=self.request.actor_ref,
            request_material=self.request.execution_material(activation_subject_ref=self.activation_spec.spec_id),
        )
        if self.execution_request_id not in {None, execution_id}:
            raise ValueError("execution request identity does not match the reviewable plan")
        if self.execution_request_digest not in {None, execution_digest}:
            raise ValueError("execution request digest does not match the reviewable plan")
        object.__setattr__(self, "execution_request_id", execution_id)
        object.__setattr__(self, "execution_request_digest", execution_digest)
        material = self.model_dump(mode="json", exclude={"plan_id", "plan_digest"})
        digest = canonical_hash(material)
        plan_id = f"intelligence_build_plan:{digest[:32]}"
        plan_digest = f"sha256:{digest}"
        if self.plan_id not in {None, plan_id} or self.plan_digest not in {None, plan_digest}:
            raise ValueError("plan identity does not match exact review material")
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "plan_digest", plan_digest)
        return self


class IntelligenceBuildPlanRequestV1Alpha2(_PlanningContract):
    """Activation-neutral onboarding selection submitted for exact planning."""

    contract: Literal["ace.application.intelligence-build-plan-request/v1alpha2"] = (
        INTELLIGENCE_BUILD_PLAN_REQUEST_V1ALPHA2_VERSION
    )
    product_id: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    client_request_id: str = Field(min_length=1, max_length=240)
    profile_id: str = Field(min_length=1, max_length=240)
    profile_digest: str
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str = Field(min_length=1, max_length=240)
    source_group_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    cadence_id: str = Field(min_length=1, max_length=240)
    proposed_effects: tuple[IntelligenceBuildEffect, ...] = REQUIRED_INTELLIGENCE_BUILD_EFFECTS
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("product_id", "actor_ref", "client_request_id", "profile_id")
    @classmethod
    def _references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("profile_digest", "request_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("request_id")
    @classmethod
    def _request_ref(cls, value: str | None) -> str | None:
        return validate_reference(value, name="request_id") if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def _aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("source_group_ids")
    @classmethod
    def _unique_source_groups(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_group_ids must be unique")
        return value

    @field_validator("proposed_effects")
    @classmethod
    def _bounded_effects(cls, value: tuple[IntelligenceBuildEffect, ...]) -> tuple[IntelligenceBuildEffect, ...]:
        if value != REQUIRED_INTELLIGENCE_BUILD_EFFECTS:
            raise ValueError("proposed_effects must preserve the exact bounded onboarding effect sequence")
        return value

    @model_validator(mode="after")
    def _derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_plan_request:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id not in {None, expected_id} or self.request_digest not in {None, expected_digest}:
            raise ValueError("plan request identity does not match exact onboarding material")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self


class IntelligenceBuildPlanV1Alpha2(_PlanningContract):
    """Exact review material with activation-neutral recorded-source selections."""

    contract: Literal["ace.application.intelligence-build-plan/v1alpha2"] = INTELLIGENCE_BUILD_PLAN_V1ALPHA2_VERSION
    request: IntelligenceBuildPlanRequestV1Alpha2
    planner_artifact: CapabilityArtifactIdentityV1Alpha1
    pack_reference: CompiledPackRefV1
    activation_spec: DomainActivationSpecV1
    recorded_source_selections: tuple[RecordedSourceSelectionV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    recorded_source_selection_refs: tuple[RecordedSourceSelectionReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    execution_request_id: str | None = None
    execution_request_digest: str | None = None
    plan_id: str | None = None
    plan_digest: str | None = None

    @field_validator("recorded_source_selections")
    @classmethod
    def _canonical_selections(
        cls,
        value: tuple[RecordedSourceSelectionV1Alpha1, ...],
    ) -> tuple[RecordedSourceSelectionV1Alpha1, ...]:
        keys = [(item.source_group_id, item.selection_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("recorded_source_selections must name each exact selection once")
        return tuple(sorted(value, key=lambda item: (item.source_group_id, str(item.selection_id))))

    @field_validator("execution_request_id", "plan_id")
    @classmethod
    def _references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("execution_request_digest", "plan_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    def execution_material(self) -> dict:
        return {
            "activation_approval_subject_ref": self.activation_spec.spec_id,
            "client_request_id": self.request.client_request_id,
            "profile_id": self.request.profile_id,
            "subject": self.request.subject,
            "outcome_id": self.request.outcome_id,
            "source_group_ids": list(self.request.source_group_ids),
            "recorded_source_selection_refs": [
                item.model_dump(mode="json") for item in self.recorded_source_selection_refs
            ],
            "cadence_id": self.request.cadence_id,
            "approved_effects": list(self.request.proposed_effects),
            "requested_at": self.request.requested_at.isoformat().replace("+00:00", "Z"),
        }

    @model_validator(mode="after")
    def _bind_exact_plan(self) -> Self:
        if self.planner_artifact.capability != INTELLIGENCE_BUILD_PLANNING_CAPABILITY:
            raise ValueError("planner artifact must declare the Intelligence build planning capability")
        if self.planner_artifact.contract != INTELLIGENCE_BUILD_PLANNER_V1ALPHA2_CONTRACT:
            raise ValueError("planner artifact must implement the exact v1alpha2 planning contract")
        if self.activation_spec.product_id != self.request.product_id:
            raise ValueError("activation specification crossed the requested product scope")
        if self.activation_spec.pack != self.pack_reference:
            raise ValueError("activation specification crossed the exact planned Pack")
        selected_groups = set(self.request.source_group_ids)
        if any(item.product_id != self.request.product_id for item in self.recorded_source_selections):
            raise ValueError("recorded source selection crossed the requested product scope")
        if any(item.pack != self.pack_reference for item in self.recorded_source_selections):
            raise ValueError("recorded source selection crossed the exact planned Pack")
        if any(item.source_group_id not in selected_groups for item in self.recorded_source_selections):
            raise ValueError("recorded source selection crossed the selected source groups")
        exact_refs = tuple(item.reference() for item in self.recorded_source_selections)
        if self.recorded_source_selection_refs and self.recorded_source_selection_refs != exact_refs:
            raise ValueError("recorded source selection references changed the exact reviewed selections")
        object.__setattr__(self, "recorded_source_selection_refs", exact_refs)
        execution_id, execution_digest = intelligence_build_execution_identity(
            product_id=self.request.product_id,
            actor_ref=self.request.actor_ref,
            request_material=self.execution_material(),
        )
        if self.execution_request_id not in {None, execution_id}:
            raise ValueError("execution request identity does not match the reviewable plan")
        if self.execution_request_digest not in {None, execution_digest}:
            raise ValueError("execution request digest does not match the reviewable plan")
        object.__setattr__(self, "execution_request_id", execution_id)
        object.__setattr__(self, "execution_request_digest", execution_digest)
        material = self.model_dump(mode="json", exclude={"plan_id", "plan_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_plan:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.plan_id not in {None, expected_id} or self.plan_digest not in {None, expected_digest}:
            raise ValueError("plan identity does not match exact review material")
        object.__setattr__(self, "plan_id", expected_id)
        object.__setattr__(self, "plan_digest", expected_digest)
        return self


class IntelligenceBuildPlanner(Protocol):
    """Installed, profile-specific, authority-neutral build planner."""

    profile_id: str
    pack_reference: CompiledPackRefV1
    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def prepare(
        self,
        request: IntelligenceBuildPlanRequestV1Alpha1,
        *,
        profile: IntelligenceOnboardingProfileV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> IntelligenceBuildPlanV1Alpha1: ...


class IntelligenceBuildPlannerV1Alpha2(Protocol):
    """Installed planner that proposes exact activation-neutral source selections."""

    profile_id: str
    pack_reference: CompiledPackRefV1
    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def prepare(
        self,
        request: IntelligenceBuildPlanRequestV1Alpha2,
        *,
        profile: IntelligenceOnboardingProfileV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> IntelligenceBuildPlanV1Alpha2: ...


def validate_intelligence_build_planner_registration(
    planner: IntelligenceBuildPlanner,
    *,
    profile_id: str,
) -> tuple[CompiledPackRefV1, CapabilityArtifactIdentityV1Alpha1]:
    """Revalidate one installed planner's declarative identity at the host edge."""

    if getattr(planner, "profile_id", None) != profile_id:
        raise ValueError("Intelligence build planner profile identity changed")
    pack_reference = CompiledPackRefV1.model_validate(
        getattr(planner, "pack_reference", None).model_dump(mode="python")
    )
    artifact = CapabilityArtifactIdentityV1Alpha1.model_validate(
        getattr(planner, "artifact_identity", None).model_dump(mode="python")
    )
    if (
        artifact.capability != INTELLIGENCE_BUILD_PLANNING_CAPABILITY
        or artifact.contract != INTELLIGENCE_BUILD_PLANNER_CONTRACT
    ):
        raise ValueError("Intelligence build planner declared the wrong capability contract")
    return pack_reference, artifact


def validate_intelligence_build_planner_v1alpha2_registration(
    planner: IntelligenceBuildPlannerV1Alpha2,
    *,
    profile_id: str,
) -> tuple[CompiledPackRefV1, CapabilityArtifactIdentityV1Alpha1]:
    """Revalidate one installed v1alpha2 planner identity at the host edge."""

    if getattr(planner, "profile_id", None) != profile_id:
        raise ValueError("Intelligence build planner profile identity changed")
    pack_reference = CompiledPackRefV1.model_validate(
        getattr(planner, "pack_reference", None).model_dump(mode="python")
    )
    artifact = CapabilityArtifactIdentityV1Alpha1.model_validate(
        getattr(planner, "artifact_identity", None).model_dump(mode="python")
    )
    if (
        artifact.capability != INTELLIGENCE_BUILD_PLANNING_CAPABILITY
        or artifact.contract != INTELLIGENCE_BUILD_PLANNER_V1ALPHA2_CONTRACT
    ):
        raise ValueError("Intelligence build planner declared the wrong v1alpha2 capability contract")
    return pack_reference, artifact


__all__ = [
    "INTELLIGENCE_BUILD_PLAN_REQUEST_VERSION",
    "INTELLIGENCE_BUILD_PLAN_VERSION",
    "INTELLIGENCE_BUILD_PLANNER_CONTRACT",
    "INTELLIGENCE_BUILD_PLANNING_CAPABILITY",
    "INTELLIGENCE_BUILD_PLANNER_V1ALPHA2_CONTRACT",
    "INTELLIGENCE_BUILD_PLAN_REQUEST_V1ALPHA2_VERSION",
    "INTELLIGENCE_BUILD_PLAN_V1ALPHA2_VERSION",
    "IntelligenceBuildPlanRequestV1Alpha1",
    "IntelligenceBuildPlanRequestV1Alpha2",
    "IntelligenceBuildPlanV1Alpha1",
    "IntelligenceBuildPlanV1Alpha2",
    "IntelligenceBuildPlanner",
    "IntelligenceBuildPlannerV1Alpha2",
    "intelligence_build_execution_identity",
    "validate_intelligence_build_planner_registration",
    "validate_intelligence_build_planner_v1alpha2_registration",
]
