"""Side-effect-free host boundary for preparing one reviewable build plan."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ace.application.installed_pack_artifacts import InstalledCompiledPackArtifactResolver, InstalledPackArtifactError
from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    IntelligenceBuildEffect,
    RecordedSourceReferenceV1,
)
from ace.application.intelligence_build_plan_binding import (
    BoundIntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanBindingError,
    IntelligenceBuildPlanBindingService,
    IntelligenceBuildPlanBindRequestV1Alpha1,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildPlannerV1Alpha3,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
    validate_intelligence_build_planner_v1alpha3_registration,
)
from ace.application.intelligence_build_review import project_intelligence_build_review
from ace.application.intelligence_system_projection import (
    IntelligenceSystemProjectionV1Alpha1,
    project_intelligence_system_plan,
)
from core.engine.core.installed_intelligence_catalog import (
    InstalledIntelligenceCatalogError,
    InstalledOnboardingProfile,
    discover_installed_onboarding_profiles,
)
from core.engine.core.intelligence_build_planner_registry import (
    IntelligenceBuildPlannerRegistryError,
    resolve_intelligence_build_planner,
)


class IntelligenceBuildPlanPrepareV1(BaseModel):
    """Unscoped onboarding selection; verified identity supplies product and actor."""

    model_config = ConfigDict(extra="forbid")

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


class IntelligenceBuildPlanPrepareV1Alpha2(BaseModel):
    """Activation-neutral onboarding selection; identity supplies product and actor."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=240)
    profile_id: str = Field(min_length=1, max_length=240)
    profile_digest: str
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str = Field(min_length=1, max_length=240)
    source_group_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    cadence_id: str = Field(min_length=1, max_length=240)
    proposed_effects: tuple[IntelligenceBuildEffect, ...] = REQUIRED_INTELLIGENCE_BUILD_EFFECTS
    requested_at: datetime


class IntelligenceBuildProjectionRequestV1(BaseModel):
    """JSON transport envelope for one strict, content-addressed reviewed plan."""

    model_config = ConfigDict(extra="forbid")

    plan: dict[str, Any]

    def exact_plan(self) -> IntelligenceBuildPlanV1Alpha3:
        return IntelligenceBuildPlanV1Alpha3.model_validate_json(json.dumps(self.plan))


class IntelligenceBuildPlannerResolutionPort(Protocol):
    def resolve(self, profile_id: str) -> IntelligenceBuildPlannerV1Alpha3 | None: ...


class _InstalledPlannerResolution:
    def resolve(self, profile_id: str) -> IntelligenceBuildPlannerV1Alpha3 | None:
        return resolve_intelligence_build_planner(profile_id)


@dataclass(frozen=True, slots=True)
class IntelligenceBuildPlanHttpRuntime:
    profiles: tuple[InstalledOnboardingProfile, ...]
    packs: InstalledCompiledPackArtifactResolver
    planners: IntelligenceBuildPlannerResolutionPort


class IntelligenceBuildPlanError(RuntimeError):
    """Base failure for the authority-neutral planning boundary."""


class IntelligenceBuildPlanUnauthenticated(IntelligenceBuildPlanError):
    """Verified token lacks a usable product-scoped identity."""


class IntelligenceBuildPlanNotFound(IntelligenceBuildPlanError):
    """The requested inert onboarding profile is not installed."""


class IntelligenceBuildPlanConflict(IntelligenceBuildPlanError):
    """The proposed selection or returned plan crossed exact review material."""


class IntelligenceBuildPlanUnavailable(IntelligenceBuildPlanError):
    """The exact installed planner or Pack is unavailable."""


def intelligence_build_plan_runtime() -> IntelligenceBuildPlanHttpRuntime:
    try:
        profiles = discover_installed_onboarding_profiles()
        packs = InstalledCompiledPackArtifactResolver.discover()
    except (InstalledIntelligenceCatalogError, InstalledPackArtifactError) as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence planning material is ambiguous") from exc
    return IntelligenceBuildPlanHttpRuntime(
        profiles=profiles,
        packs=packs,
        planners=_InstalledPlannerResolution(),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceBuildPlanUnauthenticated("verified token lacks product scope")
    return actor_ref, product_id


def _profile_for_request(
    *, request: IntelligenceBuildPlanPrepareV1Alpha2, runtime: IntelligenceBuildPlanHttpRuntime
) -> InstalledOnboardingProfile:
    matches = tuple(item for item in runtime.profiles if item.profile.profile_id == request.profile_id)
    if not matches:
        raise IntelligenceBuildPlanNotFound("Intelligence onboarding profile is not installed")
    if len(matches) != 1:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence onboarding profile is ambiguous")
    installed = matches[0]
    profile = installed.profile
    if profile.profile_digest != request.profile_digest:
        raise IntelligenceBuildPlanConflict("onboarding profile digest is not current")
    if request.outcome_id not in {item.outcome_id for item in profile.outcomes}:
        raise IntelligenceBuildPlanConflict("selected outcome is not declared by the onboarding profile")
    if request.cadence_id not in {item.cadence_id for item in profile.cadences}:
        raise IntelligenceBuildPlanConflict("selected cadence is not declared by the onboarding profile")
    declared_groups = {item.source_group_id for item in profile.source_groups}
    if any(item not in declared_groups for item in request.source_group_ids):
        raise IntelligenceBuildPlanConflict("selected source group is not declared by the onboarding profile")
    return installed


async def prepare_intelligence_build_plan(
    *,
    request: IntelligenceBuildPlanPrepareV1Alpha2,
    user: dict,
    runtime: IntelligenceBuildPlanHttpRuntime,
) -> IntelligenceBuildPlanV1Alpha3:
    """Prepare exact review material without granting authority or executing work."""

    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    if request.requested_at.tzinfo is None or request.requested_at.utcoffset() is None:
        raise IntelligenceBuildPlanConflict("requested_at must include a timezone")
    if request.requested_at.astimezone(UTC) > now + timedelta(minutes=5):
        raise IntelligenceBuildPlanConflict("requested_at cannot be materially in the future")
    installed_profile = _profile_for_request(request=request, runtime=runtime)
    try:
        planner = runtime.planners.resolve(request.profile_id)
    except IntelligenceBuildPlannerRegistryError as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planners are ambiguous") from exc
    if planner is None:
        raise IntelligenceBuildPlanUnavailable(
            f"no Intelligence build planner is registered for profile: {request.profile_id}"
        )
    try:
        pack_reference, planner_artifact = validate_intelligence_build_planner_v1alpha3_registration(
            planner,
            profile_id=request.profile_id,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planner identity is invalid") from exc
    try:
        artifact = await runtime.packs.resolve_exact(reference=pack_reference)
    except InstalledPackArtifactError as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence Pack failed exact resolution") from exc
    if artifact is None:
        raise IntelligenceBuildPlanUnavailable("planned Intelligence Pack is not installed at the exact version")
    try:
        exact_request = IntelligenceBuildPlanRequestV1Alpha2(
            product_id=product_id,
            actor_ref=actor_ref,
            **request.model_dump(mode="python"),
        )
        plan = IntelligenceBuildPlanV1Alpha3.model_validate(
            (
                await planner.prepare(
                    exact_request,
                    profile=installed_profile.profile,
                    pack=artifact.pack,
                )
            ).model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise IntelligenceBuildPlanConflict("Intelligence build planner returned invalid review material") from exc
    except Exception as exc:
        raise IntelligenceBuildPlanUnavailable("Intelligence build planner is unavailable") from exc
    if (
        plan.request != exact_request
        or plan.planner_artifact != planner_artifact
        or plan.pack_reference != pack_reference
        or plan.activation_proposal.pack != pack_reference
        or plan.activation_proposal.capability_requirement_ids
        != tuple(item.requirement_id for item in artifact.pack.capability_requirements)
        or plan.activation_proposal.authority_request_ids
        != tuple(item.request_id for item in artifact.pack.authority_requests)
    ):
        raise IntelligenceBuildPlanConflict("Intelligence build planner changed exact installed review material")
    try:
        exact_review = project_intelligence_build_review(
            request_id=str(exact_request.request_id),
            request_digest=str(exact_request.request_digest),
            subject=exact_request.subject,
            outcome_id=exact_request.outcome_id,
            cadence_id=exact_request.cadence_id,
            profile=installed_profile.profile,
            pack_reference=pack_reference,
            pack=artifact.pack,
            selections=plan.recorded_source_selections,
        )
        if plan.review_projection is not None and plan.review_projection != exact_review:
            raise IntelligenceBuildPlanConflict("Intelligence build planner changed exact review presentation")
        plan = IntelligenceBuildPlanV1Alpha3.model_validate(
            {
                **plan.model_dump(mode="python", exclude={"plan_id", "plan_digest", "review_projection"}),
                "review_projection": exact_review,
            }
        )
    except IntelligenceBuildPlanConflict:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise IntelligenceBuildPlanConflict("Intelligence build review projection is invalid") from exc
    return plan


async def bind_intelligence_build_plan(
    *,
    request: IntelligenceBuildPlanBindRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuildPlanHttpRuntime,
) -> BoundIntelligenceBuildPlanV1Alpha1:
    """Bind reviewed references without resolving, granting, or exercising authority."""

    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    if request.bound_at > now + timedelta(minutes=5):
        raise IntelligenceBuildPlanConflict("bound_at cannot be materially in the future")
    plan = request.plan
    if plan.request.product_id != product_id or plan.request.actor_ref != actor_ref:
        raise IntelligenceBuildPlanUnauthenticated("reviewed plan crossed verified product or actor scope")

    prepare_request = IntelligenceBuildPlanPrepareV1Alpha2(
        client_request_id=plan.request.client_request_id,
        profile_id=plan.request.profile_id,
        profile_digest=plan.request.profile_digest,
        subject=plan.request.subject,
        outcome_id=plan.request.outcome_id,
        source_group_ids=plan.request.source_group_ids,
        cadence_id=plan.request.cadence_id,
        proposed_effects=plan.request.proposed_effects,
        requested_at=plan.request.requested_at,
    )
    _profile_for_request(request=prepare_request, runtime=runtime)
    try:
        planner = runtime.planners.resolve(plan.request.profile_id)
    except IntelligenceBuildPlannerRegistryError as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planners are ambiguous") from exc
    if planner is None:
        raise IntelligenceBuildPlanUnavailable(
            f"no Intelligence build planner is registered for profile: {plan.request.profile_id}"
        )
    try:
        pack_reference, planner_artifact = validate_intelligence_build_planner_v1alpha3_registration(
            planner,
            profile_id=plan.request.profile_id,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planner identity is invalid") from exc
    if plan.pack_reference != pack_reference or plan.planner_artifact != planner_artifact:
        raise IntelligenceBuildPlanConflict("reviewed plan is stale for the installed planner")
    try:
        return await IntelligenceBuildPlanBindingService(packs=runtime.packs).bind(request)
    except IntelligenceBuildPlanBindingError as exc:
        raise IntelligenceBuildPlanConflict(str(exc)) from exc


async def project_intelligence_build_plan(
    *,
    plan: IntelligenceBuildPlanV1Alpha3,
    user: dict,
    runtime: IntelligenceBuildPlanHttpRuntime,
) -> IntelligenceSystemProjectionV1Alpha1:
    """Project exact reviewed material without changing or authorizing the plan."""

    actor_ref, product_id = _verified_claims(user)
    if plan.request.product_id != product_id or plan.request.actor_ref != actor_ref:
        raise IntelligenceBuildPlanUnauthenticated("reviewed plan crossed verified product or actor scope")
    prepare_request = IntelligenceBuildPlanPrepareV1Alpha2(
        client_request_id=plan.request.client_request_id,
        profile_id=plan.request.profile_id,
        profile_digest=plan.request.profile_digest,
        subject=plan.request.subject,
        outcome_id=plan.request.outcome_id,
        source_group_ids=plan.request.source_group_ids,
        cadence_id=plan.request.cadence_id,
        proposed_effects=plan.request.proposed_effects,
        requested_at=plan.request.requested_at,
    )
    installed_profile = _profile_for_request(request=prepare_request, runtime=runtime)
    try:
        planner = runtime.planners.resolve(plan.request.profile_id)
    except IntelligenceBuildPlannerRegistryError as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planners are ambiguous") from exc
    if planner is None:
        raise IntelligenceBuildPlanUnavailable(
            f"no Intelligence build planner is registered for profile: {plan.request.profile_id}"
        )
    try:
        pack_reference, planner_artifact = validate_intelligence_build_planner_v1alpha3_registration(
            planner,
            profile_id=plan.request.profile_id,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence build planner identity is invalid") from exc
    if plan.pack_reference != pack_reference or plan.planner_artifact != planner_artifact:
        raise IntelligenceBuildPlanConflict("reviewed plan is stale for the installed planner")
    try:
        artifact = await runtime.packs.resolve_exact(reference=pack_reference)
    except InstalledPackArtifactError as exc:
        raise IntelligenceBuildPlanUnavailable("installed Intelligence Pack failed exact resolution") from exc
    if artifact is None:
        raise IntelligenceBuildPlanUnavailable("planned Intelligence Pack is not installed at the exact version")
    if (
        plan.activation_proposal.pack != pack_reference
        or plan.activation_proposal.capability_requirement_ids
        != tuple(item.requirement_id for item in artifact.pack.capability_requirements)
        or plan.activation_proposal.authority_request_ids
        != tuple(item.request_id for item in artifact.pack.authority_requests)
    ):
        raise IntelligenceBuildPlanConflict("reviewed plan changed exact installed projection material")
    try:
        return project_intelligence_system_plan(
            plan=plan,
            profile=installed_profile.profile,
            pack=artifact.pack,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise IntelligenceBuildPlanConflict("Intelligence system projection is invalid") from exc


__all__ = [
    "BoundIntelligenceBuildPlanV1Alpha1",
    "IntelligenceBuildPlanConflict",
    "IntelligenceBuildPlanError",
    "IntelligenceBuildPlanHttpRuntime",
    "IntelligenceBuildPlanNotFound",
    "IntelligenceBuildPlanPrepareV1",
    "IntelligenceBuildPlanPrepareV1Alpha2",
    "IntelligenceBuildProjectionRequestV1",
    "IntelligenceBuildPlanBindRequestV1Alpha1",
    "IntelligenceBuildPlanUnauthenticated",
    "IntelligenceBuildPlanUnavailable",
    "IntelligenceBuildPlanV1Alpha1",
    "IntelligenceBuildPlanV1Alpha2",
    "IntelligenceBuildPlanV1Alpha3",
    "IntelligenceBuildPlannerResolutionPort",
    "bind_intelligence_build_plan",
    "intelligence_build_plan_runtime",
    "prepare_intelligence_build_plan",
    "project_intelligence_build_plan",
]
