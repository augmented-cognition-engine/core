"""Core-owned bootstrap from a reviewed Builder plan to canonical activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

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
)
from ace.application.intelligence_builder import (
    IntelligenceBuilderArtifactAdmission,
    IntelligenceBuilderSessionAdmission,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_activation_contracts import (
    BuilderActivationPlanArtifactV1,
    BuilderActivationReceiptArtifactV1,
)
from ace.application.intelligence_builder_contracts import (
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingStage,
    OnboardingTransitionAuthority,
)
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1


class IntelligenceBuilderActivationError(RuntimeError):
    """The durable Builder activation boundary failed closed."""


class ExactCompiledPackResolver(Protocol):
    async def load_exact(self, *, reference: CompiledPackRefV1) -> CompiledDomainPackV1 | None: ...


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
        if current is None or current.stage is not OnboardingStage.FIRST_BRIEFING_READY:
            raise IntelligenceBuilderActivationError(
                "activation plan requires the exact current briefing-ready session"
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
                raise IntelligenceBuilderActivationError("exact compiled Pack is unavailable")
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


__all__ = [
    "BuilderActivationBootstrapOutcome",
    "BuilderActivationPlanAdmission",
    "ExactCompiledPackResolver",
    "IntelligenceBuilderActivationError",
    "IntelligenceBuilderActivationService",
]
