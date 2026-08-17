"""Core-owned bootstrap from a reviewed Builder plan to canonical activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.application.briefing_agent_contracts import FirstBriefingPreviewV1
from ace.application.domain_activation import (
    CommittedActivationBinding,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import (
    CommittedDomainActivationPlan,
    DomainActivationPlanAdmissionService,
    activation_commit_reference,
    prepare_activation_onboarding_handoff,
)
from ace.application.domain_activation_plan_contracts import (
    ActivationPlanAction,
    ActivationRequestedEffect,
    ActivationRuntimeState,
    DomainActivationRevisionV1Alpha2,
    IntelligenceActivationPlanV1Alpha2,
)
from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
)
from ace.application.intelligence_build_plan_binding import BoundIntelligenceBuildPlanV1Alpha1
from ace.application.intelligence_builder import (
    IntelligenceBuilderArtifactAdmission,
    IntelligenceBuilderArtifactNotFoundError,
    IntelligenceBuilderSessionAdmission,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_activation_contracts import (
    BuilderActivationPlanArtifactV1,
    BuilderActivationReceiptArtifactV1,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingStage,
    OnboardingTransitionAuthority,
)
from ace.intelligence.contracts.activation import CompiledPackRefV1, DomainActivationSpecV1
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1


class IntelligenceBuilderActivationError(RuntimeError):
    """The durable Builder activation boundary failed closed."""


class IntelligenceBuilderActivationDependencyNotReadyError(IntelligenceBuilderActivationError):
    """A required durable prerequisite (session, artifact, or compiled Pack) does not exist yet.

    Distinct from the base error's crossed/stale/mismatched-material cases:
    this subclass names only "the audited prerequisite is not durably present
    yet", which HTTP boundaries map to 404 rather than 409.
    """


class ExactCompiledPackResolver(Protocol):
    async def load_exact(self, *, reference: CompiledPackRefV1) -> CompiledDomainPackV1 | None: ...


class ExactInstalledPackConformanceResolver(Protocol):
    """Resolve one installed compiled Pack together with its passing conformance evidence."""

    async def resolve_exact(self, *, reference: CompiledPackRefV1):  # -> InstalledCompiledPackArtifact | None
        ...


@dataclass(frozen=True, slots=True)
class BuilderActivationPlanAdmission:
    artifact: BuilderActivationPlanArtifactV1
    artifact_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class BuilderActivationBootstrapOutcome:
    binding: CommittedActivationBinding
    receipt_artifact: BuilderActivationReceiptArtifactV1
    artifact_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission
    replayed: bool


class IntelligenceBuilderActivationService:
    """Reload exact durable Builder material, then commit canonical activation."""

    def __init__(
        self,
        *,
        sessions: IntelligenceBuilderSessionService,
        plans: DomainActivationPlanAdmissionService,
        compatibility: DomainActivationCompatibilityService,
        canonical: DomainActivationAdmissionService,
        packs: ExactCompiledPackResolver,
    ) -> None:
        self.sessions = sessions
        self.plans = plans
        self.compatibility = compatibility
        self.canonical = canonical
        self.packs = packs

    async def record_current_plan(
        self,
        *,
        product_id: str,
        session_id: str,
        committed: CommittedDomainActivationPlan,
        pack: CompiledPackRefV1,
        recorded_at: datetime,
    ) -> BuilderActivationPlanAdmission:
        current = await self.sessions.load_latest(
            product_id=product_id,
            session_id=session_id,
            available_at=recorded_at,
        )
        if current is None:
            raise IntelligenceBuilderActivationDependencyNotReadyError(
                "activation plan requires the exact current briefing-ready session"
            )
        if current.stage is not OnboardingStage.FIRST_BRIEFING_READY:
            raise IntelligenceBuilderActivationError(
                "activation plan requires the current session to be briefing-ready"
            )
        source = committed.revision
        admitted = await self.plans.reload(
            product_id=product_id,
            activation_key=source.plan.spec.activation_key,
        )
        if admitted is None or admitted != committed:
            raise IntelligenceBuilderActivationError("activation plan is not the exact current Core-admitted revision")
        if (
            source.plan.spec.product_id != product_id
            or source.plan.onboarding_handoff.session_id != session_id
            or source.plan.onboarding_handoff.session_revision_id != current.revision_id
            or source.plan.spec.pack != pack
        ):
            raise IntelligenceBuilderActivationError("activation plan crossed its exact session, product, or Pack")
        reference = activation_commit_reference(committed)
        artifact = BuilderActivationPlanArtifactV1(
            session_id=session_id,
            session_revision_id=str(current.revision_id),
            session_revision_digest=str(current.revision_digest),
            source_commit=reference,
            spec_id=str(source.plan.spec.spec_id),
            spec_digest=f"sha256:{source.plan.spec.spec_hash}",
            pack=pack,
            created_at=recorded_at,
        )
        artifact_admission = await self.sessions.persist_artifact(product_id=product_id, artifact=artifact)
        artifacts = tuple(
            item for item in current.artifacts if item.artifact_kind is not OnboardingArtifactKind.ACTIVATION_PLAN
        ) + (
            OnboardingArtifactReferenceV1(
                artifact_kind=OnboardingArtifactKind.ACTIVATION_PLAN,
                artifact_id=str(artifact.artifact_id),
                artifact_digest=str(artifact.artifact_digest),
            ),
        )
        session = await self.sessions.advance(
            current,
            stage=OnboardingStage.ACTIVATION_PENDING,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=source.actor_ref,
            occurred_at=recorded_at,
            artifacts=artifacts,
        )
        return BuilderActivationPlanAdmission(
            artifact=artifact,
            artifact_admission=artifact_admission,
            session=session,
        )

    async def activate(
        self,
        *,
        product_id: str,
        session_id: str,
        activation_approval_receipt_ref: str,
        evaluated_at: datetime,
    ) -> BuilderActivationBootstrapOutcome:
        try:
            current = await self.sessions.load_latest(
                product_id=product_id,
                session_id=session_id,
                available_at=evaluated_at,
            )
            if current is None or current.stage not in {OnboardingStage.ACTIVATION_PENDING, OnboardingStage.ACTIVE}:
                raise IntelligenceBuilderActivationError("activation requires the exact current pending session")
            plan_refs = [
                item for item in current.artifacts if item.artifact_kind is OnboardingArtifactKind.ACTIVATION_PLAN
            ]
            if len(plan_refs) != 1:
                raise IntelligenceBuilderActivationError("current session must bind one exact durable activation plan")
            plan_artifact = await self.sessions.load_artifact(
                product_id=product_id,
                reference=plan_refs[0],
                artifact_type=BuilderActivationPlanArtifactV1,
                available_at=evaluated_at,
            )
            source = await self.plans.reload(
                product_id=product_id,
                activation_key=plan_artifact.source_commit.activation_key,
            )
            if source is None or activation_commit_reference(source) != plan_artifact.source_commit:
                raise IntelligenceBuilderActivationError("durable activation plan is stale or no longer current")
            revision = source.revision
            if (
                plan_artifact.session_id != session_id
                or plan_artifact.session_revision_id != revision.plan.onboarding_handoff.session_revision_id
                or plan_artifact.spec_id != revision.plan.spec.spec_id
                or plan_artifact.spec_digest != f"sha256:{revision.plan.spec.spec_hash}"
                or plan_artifact.pack != revision.plan.spec.pack
            ):
                raise IntelligenceBuilderActivationError("durable activation plan linkage changed")
            prepared = await self.compatibility.prepare_initial_canonical_activation(
                revision=revision,
                activation_approval_receipt_ref=activation_approval_receipt_ref,
                evaluated_at=evaluated_at,
            )
            pack = await self.packs.load_exact(reference=plan_artifact.pack)
            if pack is None:
                raise IntelligenceBuilderActivationDependencyNotReadyError("exact compiled Pack is unavailable")
            canonical = await self.canonical.reload(
                product_id=product_id,
                activation_key=revision.plan.spec.activation_key,
            )
            replayed = canonical is not None
            if canonical is None:
                canonical = await self.canonical.admit(
                    prepared.canonical_revision,
                    expected_head_revision_id=None,
                    committed_at=evaluated_at,
                )
            elif canonical.revision != prepared.canonical_revision:
                raise IntelligenceBuilderActivationError("canonical activation head already binds different material")
            binding = bind_committed_activation(pack=pack, committed=canonical)
            canonical_reference = ActivationRevisionReferenceV1Alpha1(
                product_id=product_id,
                activation_key=canonical.revision.spec.activation_key,
                activation_id=str(canonical.revision.activation_id),
                revision=canonical.revision.revision,
                revision_id=str(canonical.revision.revision_id),
                revision_digest=f"sha256:{canonical.revision.revision_hash}",
            )
            receipt_artifact = BuilderActivationReceiptArtifactV1(
                session_id=session_id,
                activation_plan_artifact_id=str(plan_artifact.artifact_id),
                activation_plan_artifact_digest=str(plan_artifact.artifact_digest),
                source_commit=plan_artifact.source_commit,
                canonical_revision=canonical_reference,
                canonical_state_kind=canonical.commit_receipt.state_kind,
                canonical_commit_receipt_id=str(canonical.commit_receipt.receipt_id),
                canonical_commit_receipt_digest=f"sha256:{canonical.commit_receipt.receipt_hash}",
                activated_at=canonical.commit_receipt.committed_at,
            )
            artifact_admission = await self.sessions.persist_artifact(
                product_id=product_id,
                artifact=receipt_artifact,
            )
            receipt_ref = OnboardingArtifactReferenceV1(
                artifact_kind=OnboardingArtifactKind.ACTIVATION_RECEIPT,
                artifact_id=str(receipt_artifact.artifact_id),
                artifact_digest=str(receipt_artifact.artifact_digest),
            )
            artifacts = tuple(
                item
                for item in current.artifacts
                if item.artifact_kind is not OnboardingArtifactKind.ACTIVATION_RECEIPT
            ) + (receipt_ref,)
            if current.stage is OnboardingStage.ACTIVE:
                if (
                    receipt_ref not in current.artifacts
                    or current.approval_receipt_ref != activation_approval_receipt_ref
                ):
                    raise IntelligenceBuilderActivationError(
                        "active Builder session does not bind the exact activation receipt"
                    )
                session = await self.sessions.reload_admission(current)
            else:
                session = await self.sessions.advance(
                    current,
                    stage=OnboardingStage.ACTIVE,
                    authority=OnboardingTransitionAuthority.CORE_ACTIVATION,
                    actor_ref=revision.actor_ref,
                    occurred_at=evaluated_at,
                    artifacts=artifacts,
                    approval_receipt_ref=activation_approval_receipt_ref,
                )
            return BuilderActivationBootstrapOutcome(
                binding=binding,
                receipt_artifact=receipt_artifact,
                artifact_admission=artifact_admission,
                session=session,
                replayed=replayed,
            )
        except IntelligenceBuilderActivationError:
            raise
        except Exception as exc:
            raise IntelligenceBuilderActivationError("Builder activation bootstrap failed closed") from exc


class DomainActivationPlanNotAdmittedError(IntelligenceBuilderActivationError):
    """No exact durable v1alpha2 activation plan is admitted for this activation yet."""


def prepare_initial_domain_activation_plan(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    observations: AuthorizedObservationSetV1,
    intelligence_model: IntelligenceModelProposalV1,
    intelligence_disposition: IntelligenceModelDispositionV1,
    first_briefing: FirstBriefingPreviewV1,
    spec: DomainActivationSpecV1,
    created_at: datetime,
) -> IntelligenceActivationPlanV1Alpha2:
    """Close one exact FIRST_BRIEFING_READY session and 0.7D handoff into an inert initial-activation plan.

    This grants no authority: it reuses the same non-authorizing closure
    :func:`prepare_activation_onboarding_handoff` already performs and wraps
    it around one exact bound activation specification. The result still
    requires its own separate approval before
    :class:`DomainActivationPlanAdmissionService` will admit it.
    """

    handoff = prepare_activation_onboarding_handoff(
        session=session,
        observations=observations,
        intelligence_model=intelligence_model,
        intelligence_disposition=intelligence_disposition,
        first_briefing=first_briefing,
    )
    try:
        return IntelligenceActivationPlanV1Alpha2(
            action=ActivationPlanAction.INITIAL_ACTIVATION,
            onboarding_handoff=handoff,
            spec=spec,
            requested_effects=(ActivationRequestedEffect.PACK_ACTIVATION,),
            requested_capabilities=spec.capability_bindings,
            requested_authorities=spec.authority_bindings,
            expected_head_revision_id=None,
            created_at=created_at,
        )
    except (TypeError, ValueError) as exc:
        raise IntelligenceBuilderActivationError("initial activation plan failed exact construction") from exc


@dataclass(frozen=True, slots=True)
class _RequiredOnboardingMaterial:
    session: IntelligenceBuilderSessionRevisionV1
    observations: AuthorizedObservationSetV1
    intelligence_model: IntelligenceModelProposalV1
    intelligence_disposition: IntelligenceModelDispositionV1
    first_briefing: FirstBriefingPreviewV1


def _required_artifact_reference(
    session: IntelligenceBuilderSessionRevisionV1,
    kind: OnboardingArtifactKind,
) -> OnboardingArtifactReferenceV1:
    matches = tuple(item for item in session.artifacts if item.artifact_kind is kind)
    if len(matches) != 1:
        raise IntelligenceBuilderActivationDependencyNotReadyError(
            f"session is missing its exact durable {kind.value} artifact"
        )
    return matches[0]


class IntelligenceBuilderActivationPlanCoordinator:
    """Connect one exact FIRST_BRIEFING_READY session to a separately admitted v1alpha2 plan.

    This is the production seam between the Builder's inert 0.7D handoff and
    :class:`IntelligenceBuilderActivationService`. It never substitutes the
    reviewed activation specification's own approval for the v1alpha2 plan's
    distinct approval, never fabricates the onboarding handoff from a bound
    HTTP plan, and never trusts caller-supplied plan material -- every
    dependency is durably reloaded and point-of-use revalidated.
    """

    def __init__(
        self,
        *,
        sessions: IntelligenceBuilderSessionService,
        plans: DomainActivationPlanAdmissionService,
        packs: ExactInstalledPackConformanceResolver,
        activation: IntelligenceBuilderActivationService,
    ) -> None:
        self.sessions = sessions
        self.plans = plans
        self.packs = packs
        self.activation = activation

    async def _reload_onboarding_material(
        self,
        *,
        product_id: str,
        session_id: str,
        evaluated_at: datetime,
    ) -> _RequiredOnboardingMaterial:
        session = await self.sessions.load_latest(
            product_id=product_id,
            session_id=session_id,
            available_at=evaluated_at,
        )
        if session is None:
            raise IntelligenceBuilderActivationDependencyNotReadyError(
                "activation plan requires the exact current briefing-ready session"
            )
        if session.stage is not OnboardingStage.FIRST_BRIEFING_READY:
            raise IntelligenceBuilderActivationError(
                "activation plan requires the current session to be briefing-ready"
            )
        try:
            observations = await self.sessions.load_artifact(
                product_id=product_id,
                reference=_required_artifact_reference(session, OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET),
                artifact_type=AuthorizedObservationSetV1,
                available_at=evaluated_at,
            )
            intelligence_model = await self.sessions.load_artifact(
                product_id=product_id,
                reference=_required_artifact_reference(session, OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL),
                artifact_type=IntelligenceModelProposalV1,
                available_at=evaluated_at,
            )
            intelligence_disposition = await self.sessions.load_artifact(
                product_id=product_id,
                reference=_required_artifact_reference(session, OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION),
                artifact_type=IntelligenceModelDispositionV1,
                available_at=evaluated_at,
            )
            first_briefing = await self.sessions.load_artifact(
                product_id=product_id,
                reference=_required_artifact_reference(session, OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW),
                artifact_type=FirstBriefingPreviewV1,
                available_at=evaluated_at,
            )
        except IntelligenceBuilderArtifactNotFoundError as exc:
            raise IntelligenceBuilderActivationDependencyNotReadyError(str(exc)) from exc
        return _RequiredOnboardingMaterial(
            session=session,
            observations=observations,
            intelligence_model=intelligence_model,
            intelligence_disposition=intelligence_disposition,
            first_briefing=first_briefing,
        )

    async def prepare(
        self,
        *,
        product_id: str,
        session_id: str,
        bound: BoundIntelligenceBuildPlanV1Alpha1,
        created_at: datetime,
    ) -> IntelligenceActivationPlanV1Alpha2:
        """Side-effect-free preview of the exact plan the owner is about to approve."""

        if bound.binding_request.plan.request.product_id != product_id:
            raise IntelligenceBuilderActivationError("bound plan crossed the exact activation product scope")
        material = await self._reload_onboarding_material(
            product_id=product_id,
            session_id=session_id,
            evaluated_at=created_at,
        )
        return prepare_initial_domain_activation_plan(
            session=material.session,
            observations=material.observations,
            intelligence_model=material.intelligence_model,
            intelligence_disposition=material.intelligence_disposition,
            first_briefing=material.first_briefing,
            spec=bound.activation_spec,
            created_at=created_at,
        )

    async def admit(
        self,
        *,
        product_id: str,
        session_id: str,
        bound: BoundIntelligenceBuildPlanV1Alpha1,
        actor_ref: str,
        approval_receipt_ref: str,
        created_at: datetime,
        committed_at: datetime,
    ) -> CommittedDomainActivationPlan:
        """Durably admit the exact plan, replaying an identical prior admission."""

        if bound.binding_request.plan.request.product_id != product_id:
            raise IntelligenceBuilderActivationError("bound plan crossed the exact activation product scope")
        material = await self._reload_onboarding_material(
            product_id=product_id,
            session_id=session_id,
            evaluated_at=committed_at,
        )
        plan = prepare_initial_domain_activation_plan(
            session=material.session,
            observations=material.observations,
            intelligence_model=material.intelligence_model,
            intelligence_disposition=material.intelligence_disposition,
            first_briefing=material.first_briefing,
            spec=bound.activation_spec,
            created_at=created_at,
        )
        existing = await self.plans.reload(product_id=product_id, activation_key=plan.spec.activation_key)
        if existing is not None:
            if existing.revision.plan != plan:
                raise IntelligenceBuilderActivationError(
                    "activation plan is already admitted with different exact material"
                )
            return existing
        artifact = await self.packs.resolve_exact(reference=plan.spec.pack)
        if artifact is None:
            raise IntelligenceBuilderActivationDependencyNotReadyError(
                "exact compiled Pack for the activation plan is unavailable"
            )
        revision = DomainActivationRevisionV1Alpha2(
            revision=1,
            plan=plan,
            state=ActivationRuntimeState.ACTIVE,
            prior_revision_id=None,
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            occurred_at=committed_at,
        )
        return await self.plans.admit(
            revision,
            pack=artifact.pack,
            conformance_receipts=artifact.conformance_receipts,
            session=material.session,
            observations=material.observations,
            intelligence_model=material.intelligence_model,
            intelligence_disposition=material.intelligence_disposition,
            first_briefing=material.first_briefing,
            committed_at=committed_at,
        )

    async def activate(
        self,
        *,
        product_id: str,
        bound: BoundIntelligenceBuildPlanV1Alpha1,
        activation_approval_receipt_ref: str,
        requested_at: datetime,
    ) -> BuilderActivationBootstrapOutcome:
        """Derive the exact session from the admitted plan and drive record_current_plan/activate.

        Crash-safe: if a prior call already advanced the session into
        ``ACTIVATION_PENDING`` (or ``ACTIVE``), this resumes from there
        instead of re-running ``record_current_plan``.
        """

        if bound.binding_request.plan.request.product_id != product_id:
            raise IntelligenceBuilderActivationError("bound plan crossed the exact activation product scope")
        committed = await self.plans.reload(
            product_id=product_id,
            activation_key=bound.activation_spec.activation_key,
        )
        if committed is None:
            raise DomainActivationPlanNotAdmittedError(
                "the v1alpha2 activation plan has not yet been separately approved and admitted"
            )
        spec = committed.revision.plan.spec
        if spec != bound.activation_spec:
            raise IntelligenceBuilderActivationError(
                "admitted activation plan crossed the exact bound activation specification"
            )
        session_id = committed.revision.plan.onboarding_handoff.session_id
        session = await self.sessions.load_latest(
            product_id=product_id,
            session_id=session_id,
            available_at=requested_at,
        )
        if session is None:
            raise IntelligenceBuilderActivationDependencyNotReadyError(
                "activation requires the exact current Builder session"
            )
        if session.stage is OnboardingStage.FIRST_BRIEFING_READY:
            await self.activation.record_current_plan(
                product_id=product_id,
                session_id=session_id,
                committed=committed,
                pack=spec.pack,
                recorded_at=requested_at,
            )
        elif session.stage not in {OnboardingStage.ACTIVATION_PENDING, OnboardingStage.ACTIVE}:
            raise IntelligenceBuilderActivationError(
                "Builder session is not eligible to record or activate this exact plan"
            )
        return await self.activation.activate(
            product_id=product_id,
            session_id=session_id,
            activation_approval_receipt_ref=activation_approval_receipt_ref,
            evaluated_at=requested_at,
        )


__all__ = [
    "BuilderActivationBootstrapOutcome",
    "BuilderActivationPlanAdmission",
    "DomainActivationPlanNotAdmittedError",
    "ExactCompiledPackResolver",
    "ExactInstalledPackConformanceResolver",
    "IntelligenceBuilderActivationDependencyNotReadyError",
    "IntelligenceBuilderActivationError",
    "IntelligenceBuilderActivationPlanCoordinator",
    "IntelligenceBuilderActivationService",
    "prepare_initial_domain_activation_plan",
]
