"""Owner-reviewed binding of one activation-neutral Intelligence build plan.

Preparing a plan is side-effect free and cannot name grants or capability
implementations on an owner's behalf.  This boundary accepts those exact
reviewed bindings, re-resolves the installed Pack and its evidence, and only
then derives the activation specification and executable request identity.
It does not resolve, mint, or exercise authority or approval.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from ace.application.installed_pack_artifacts import (
    InstalledCompiledPackArtifactResolver,
    InstalledPackArtifactError,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildPlanV1Alpha3,
    intelligence_build_execution_identity,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import (
    AuthorityBindingV1,
    CapabilityBindingV1,
    DomainActivationSpecV1,
)
from ace.intelligence.contracts.common import validate_digest, validate_reference
from ace.intelligence.packs.activation import prepare_domain_activation

INTELLIGENCE_BUILD_PLAN_BIND_REQUEST_VERSION = "ace.application.intelligence-build-plan-bind-request/v1alpha1"
BOUND_INTELLIGENCE_BUILD_PLAN_VERSION = "ace.application.bound-intelligence-build-plan/v1alpha1"


class _BindingContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class IntelligenceBuildPlanBindRequestV1Alpha1(_BindingContract):
    """Exact plan plus bindings explicitly selected for owner review."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=False,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )

    contract: Literal["ace.application.intelligence-build-plan-bind-request/v1alpha1"] = (
        INTELLIGENCE_BUILD_PLAN_BIND_REQUEST_VERSION
    )
    plan: IntelligenceBuildPlanV1Alpha3
    capability_bindings: tuple[CapabilityBindingV1, ...] = Field(default_factory=tuple, max_length=256)
    authority_bindings: tuple[AuthorityBindingV1, ...] = Field(default_factory=tuple, max_length=256)
    bound_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("plan", mode="before")
    @classmethod
    def _json_plan(cls, value):
        if isinstance(value, dict):
            try:
                return IntelligenceBuildPlanV1Alpha3.model_validate(value)
            except ValidationError:
                return IntelligenceBuildPlanV1Alpha3.model_validate_json(json.dumps(value))
        return value

    @field_validator("capability_bindings")
    @classmethod
    def _capability_bindings(cls, value: tuple[CapabilityBindingV1, ...]) -> tuple[CapabilityBindingV1, ...]:
        keys = [item.requirement_id for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("capability bindings must name each requirement once")
        return tuple(sorted(value, key=lambda item: item.requirement_id))

    @field_validator("authority_bindings")
    @classmethod
    def _authority_bindings(cls, value: tuple[AuthorityBindingV1, ...]) -> tuple[AuthorityBindingV1, ...]:
        keys = [item.request_id for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("authority bindings must name each request once")
        return tuple(sorted(value, key=lambda item: item.request_id))

    @field_validator("bound_at")
    @classmethod
    def _bound_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bound_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("request_id")
    @classmethod
    def _request_ref(cls, value: str | None) -> str | None:
        return validate_reference(value, name="request_id") if value is not None else None

    @field_validator("request_digest")
    @classmethod
    def _request_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def _derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_plan_bind_request:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id not in {None, expected_id} or self.request_digest not in {None, expected_digest}:
            raise ValueError("bind request identity does not match exact reviewed material")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self


class BoundIntelligenceBuildPlanV1Alpha1(_BindingContract):
    """One exact plan after reviewed bindings make execution identity possible."""

    contract: Literal["ace.application.bound-intelligence-build-plan/v1alpha1"] = BOUND_INTELLIGENCE_BUILD_PLAN_VERSION
    binding_request: IntelligenceBuildPlanBindRequestV1Alpha1
    activation_spec: DomainActivationSpecV1
    execution_request_id: str | None = None
    execution_request_digest: str | None = None
    bound_plan_id: str | None = None
    bound_plan_digest: str | None = None

    @field_validator("execution_request_id", "bound_plan_id")
    @classmethod
    def _references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("execution_request_digest", "bound_plan_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    def execution_material(self) -> dict:
        plan = self.binding_request.plan
        request = plan.request
        return {
            "activation_approval_subject_ref": self.activation_spec.spec_id,
            "client_request_id": request.client_request_id,
            "profile_id": request.profile_id,
            "subject": request.subject,
            "outcome_id": request.outcome_id,
            "source_group_ids": list(request.source_group_ids),
            "recorded_source_selection_refs": [
                item.model_dump(mode="json") for item in plan.recorded_source_selection_refs
            ],
            "cadence_id": request.cadence_id,
            "approved_effects": list(request.proposed_effects),
            "requested_at": request.requested_at.isoformat().replace("+00:00", "Z"),
        }

    @model_validator(mode="after")
    def _bind_exact_execution(self) -> Self:
        plan = self.binding_request.plan
        proposal = plan.activation_proposal
        if (
            self.activation_spec.product_id != plan.request.product_id
            or self.activation_spec.activation_key != proposal.activation_key
            or self.activation_spec.pack != proposal.pack
            or self.activation_spec.overlay != proposal.overlay
            or self.activation_spec.capability_bindings != self.binding_request.capability_bindings
            or self.activation_spec.authority_bindings != self.binding_request.authority_bindings
        ):
            raise ValueError("bound activation specification crossed exact reviewed plan material")
        execution_id, execution_digest = intelligence_build_execution_identity(
            product_id=plan.request.product_id,
            actor_ref=plan.request.actor_ref,
            request_material=self.execution_material(),
        )
        if self.execution_request_id not in {None, execution_id}:
            raise ValueError("execution request identity does not match the bound plan")
        if self.execution_request_digest not in {None, execution_digest}:
            raise ValueError("execution request digest does not match the bound plan")
        object.__setattr__(self, "execution_request_id", execution_id)
        object.__setattr__(self, "execution_request_digest", execution_digest)
        material = self.model_dump(mode="json", exclude={"bound_plan_id", "bound_plan_digest"})
        digest = canonical_hash(material)
        expected_id = f"bound_intelligence_build_plan:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.bound_plan_id not in {None, expected_id} or self.bound_plan_digest not in {None, expected_digest}:
            raise ValueError("bound plan identity does not match exact material")
        object.__setattr__(self, "bound_plan_id", expected_id)
        object.__setattr__(self, "bound_plan_digest", expected_digest)
        return self


class IntelligenceBuildPlanBindingError(RuntimeError):
    """Reviewed plan bindings failed exact installed-material validation."""


class IntelligenceBuildPlanBindingService:
    """Bind exact requirements without resolving or exercising any authority."""

    def __init__(self, *, packs: InstalledCompiledPackArtifactResolver) -> None:
        self.packs = packs

    async def bind(
        self,
        request: IntelligenceBuildPlanBindRequestV1Alpha1,
    ) -> BoundIntelligenceBuildPlanV1Alpha1:
        try:
            exact = IntelligenceBuildPlanBindRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            plan = exact.plan
            proposal = plan.activation_proposal
            artifact = await self.packs.resolve_exact(reference=plan.pack_reference)
            if artifact is None:
                raise IntelligenceBuildPlanBindingError("planned Intelligence Pack is not installed exactly")
            pack = artifact.pack
            capability_ids = tuple(item.requirement_id for item in pack.capability_requirements)
            authority_ids = tuple(item.request_id for item in pack.authority_requests)
            if (
                proposal.pack != plan.pack_reference
                or proposal.capability_requirement_ids != capability_ids
                or proposal.authority_request_ids != authority_ids
            ):
                raise IntelligenceBuildPlanBindingError(
                    "activation proposal crossed the exact installed Pack requirements"
                )
            receipts = tuple(artifact.conformance_receipts)
            spec = prepare_domain_activation(
                product_id=plan.request.product_id,
                activation_key=proposal.activation_key,
                pack=pack,
                overlay=proposal.overlay,
                compilation_receipt_ref=artifact.compilation.result_id,
                conformance_receipt_refs=tuple(str(item.receipt_id) for item in receipts),
                conformance_receipts=receipts,
                capability_bindings=exact.capability_bindings,
                authority_bindings=exact.authority_bindings,
            )
            return BoundIntelligenceBuildPlanV1Alpha1(
                binding_request=exact,
                activation_spec=spec,
            )
        except IntelligenceBuildPlanBindingError:
            raise
        except InstalledPackArtifactError as exc:
            raise IntelligenceBuildPlanBindingError("installed Intelligence Pack failed exact resolution") from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise IntelligenceBuildPlanBindingError("reviewed activation bindings failed closed") from exc


__all__ = [
    "BOUND_INTELLIGENCE_BUILD_PLAN_VERSION",
    "INTELLIGENCE_BUILD_PLAN_BIND_REQUEST_VERSION",
    "BoundIntelligenceBuildPlanV1Alpha1",
    "IntelligenceBuildPlanBindRequestV1Alpha1",
    "IntelligenceBuildPlanBindingError",
    "IntelligenceBuildPlanBindingService",
]
