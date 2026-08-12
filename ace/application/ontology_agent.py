"""Proposal-only 0.7C Ontology Agent application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.application.intelligence_builder import (
    IntelligenceBuilderArtifactAdmission,
    IntelligenceBuilderSessionAdmission,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceProfileProposalV1,
)
from ace.application.ontology_agent_contracts import (
    ConceptModelDispositionV1,
    ConceptModelProposalV1,
    OrganizationTerminologyV1,
    concept_model_semantic_diff,
)
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1


class OntologyAgentError(RuntimeError):
    """The Ontology Agent failed before producing a safe proposal handoff."""


class OntologyAgentStaleProposal(OntologyAgentError):
    """The proposal or source-profile handoff is not the exact current material."""


class OntologyAgentAttributionError(OntologyAgentError):
    """The proposal contains concepts without exact admitted source attribution."""


class ConceptModelStrategy(Protocol):
    """Optional host strategy; provider use remains outside the application service."""

    async def propose(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        source_profile: SourceProfileProposalV1,
        user_intent: str,
        organization_terminology: tuple[OrganizationTerminologyV1, ...],
        created_at: datetime,
    ) -> ConceptModelProposalV1: ...


@dataclass(frozen=True, slots=True)
class ConceptModelProposalAdmission:
    proposal: ConceptModelProposalV1
    proposal_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class ConceptModelApprovalAdmission:
    proposal: ConceptModelProposalV1
    disposition: ConceptModelDispositionV1
    disposition_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class OntologyAgentOutcome:
    proposal: ConceptModelProposalAdmission | None
    blocked_session: IntelligenceBuilderSessionAdmission | None
    blocked_reason: OnboardingBlockReason | None

    @property
    def proposed(self) -> bool:
        return self.proposal is not None and self.blocked_reason is None


def _reference(
    kind: OnboardingArtifactKind,
    artifact_id: str,
    artifact_digest: str,
) -> OnboardingArtifactReferenceV1:
    return OnboardingArtifactReferenceV1(
        artifact_kind=kind,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
    )


def _replace_reference(
    artifacts: tuple[OnboardingArtifactReferenceV1, ...],
    replacement: OnboardingArtifactReferenceV1,
    *,
    remove: tuple[OnboardingArtifactKind, ...] = (),
) -> tuple[OnboardingArtifactReferenceV1, ...]:
    removed = set(remove) | {replacement.artifact_kind}
    return tuple(item for item in artifacts if item.artifact_kind not in removed) + (replacement,)


def _current_reference(
    session: IntelligenceBuilderSessionRevisionV1,
    kind: OnboardingArtifactKind,
) -> OnboardingArtifactReferenceV1 | None:
    return next((item for item in session.artifacts if item.artifact_kind is kind), None)


class OntologyAgent:
    """Generate, revise, and approve exact cited concept-model proposals."""

    def __init__(
        self,
        *,
        sessions: IntelligenceBuilderSessionService,
        authority: CoreAuthorityResolver,
        strategy: ConceptModelStrategy,
        minimum_confidence: float = 0.6,
    ) -> None:
        self.sessions = sessions
        self.authority = authority
        self.strategy = strategy
        self.minimum_confidence = minimum_confidence

    async def _exact_source_profile(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        source_profile: SourceProfileProposalV1,
        occurred_at: datetime,
    ) -> SourceProfileProposalV1:
        if source_profile is None:
            raise OntologyAgentStaleProposal("source-profile input is missing")
        exact = SourceProfileProposalV1.model_validate(source_profile.model_dump(mode="python"))
        reference = _current_reference(session, OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL)
        if (
            reference is None
            or reference.artifact_id != exact.proposal_id
            or reference.artifact_digest != exact.proposal_digest
            or exact.session_id != session.session_id
        ):
            raise OntologyAgentStaleProposal("source-profile input is not the current exact handoff")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=SourceProfileProposalV1,
            available_at=occurred_at,
        )
        if persisted != exact:
            raise OntologyAgentStaleProposal("source-profile body differs from durable handoff material")
        return exact

    @staticmethod
    def _validate_attribution(
        proposal: ConceptModelProposalV1,
        source_profile: SourceProfileProposalV1,
    ) -> None:
        samples = {str(sample.sample_id): sample for sample in source_profile.samples}
        for citation in proposal.citations:
            sample = samples.get(citation.source_sample_id)
            fields = set() if sample is None else {item.field_path for item in sample.fields}
            if (
                citation.source_profile_proposal_id != source_profile.proposal_id
                or citation.source_profile_proposal_digest != source_profile.proposal_digest
                or sample is None
                or citation.source_sample_digest != sample.sample_digest
                or citation.source_ref != sample.source_ref
                or citation.evidence_digest != sample.evidence_digest
                or citation.field_path not in fields
            ):
                raise OntologyAgentAttributionError(
                    "concept citation does not bind exact admitted source-profile evidence"
                )

    async def propose(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        source_profile: SourceProfileProposalV1,
        user_intent: str,
        organization_terminology: tuple[OrganizationTerminologyV1, ...] = (),
        actor_ref: str,
        occurred_at: datetime,
    ) -> OntologyAgentOutcome:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.SOURCES_READY:
            raise OntologyAgentError("Ontology Agent can propose only from sources_ready")
        latest = await self.sessions.load_latest(
            product_id=session.product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != session.revision_id:
            raise OntologyAgentStaleProposal("concept proposal started from a stale session revision")
        exact_profile = await self._exact_source_profile(
            session=session,
            source_profile=source_profile,
            occurred_at=occurred_at,
        )
        try:
            raw = await self.strategy.propose(
                session=session,
                source_profile=exact_profile,
                user_intent=user_intent,
                organization_terminology=organization_terminology,
                created_at=occurred_at,
            )
            proposal = ConceptModelProposalV1.model_validate(raw.model_dump(mode="python"))
            self._validate_attribution(proposal, exact_profile)
        except OntologyAgentAttributionError:
            raise
        except Exception:
            raise OntologyAgentError("concept-model strategy failed exact proposal validation") from None
        if proposal.confidence < self.minimum_confidence:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.LOW_CONFIDENCE_MAPPING,
                actor_ref=actor_ref,
                safe_diagnostic="concept-model proposal did not meet the declared confidence floor",
                occurred_at=occurred_at,
            )
            return OntologyAgentOutcome(
                proposal=None,
                blocked_session=blocked,
                blocked_reason=OnboardingBlockReason.LOW_CONFIDENCE_MAPPING,
            )
        if any(item.blocks_mapping for item in proposal.conflicts):
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.CONFLICTING_SOURCES,
                actor_ref=actor_ref,
                safe_diagnostic="source disagreement prevents a safe concept-model handoff",
                occurred_at=occurred_at,
            )
            return OntologyAgentOutcome(
                proposal=None,
                blocked_session=blocked,
                blocked_reason=OnboardingBlockReason.CONFLICTING_SOURCES,
            )
        return OntologyAgentOutcome(
            proposal=await self._persist_and_handoff(session, proposal, actor_ref=actor_ref, occurred_at=occurred_at),
            blocked_session=None,
            blocked_reason=None,
        )

    async def _persist_and_handoff(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        proposal: ConceptModelProposalV1,
        *,
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConceptModelProposalAdmission:
        admission = await self.sessions.persist_artifact(
            product_id=session.product_id,
            artifact=proposal,
        )
        reference = _reference(
            OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
            str(proposal.proposal_id),
            str(proposal.proposal_digest),
        )
        artifacts = _replace_reference(
            session.artifacts,
            reference,
            remove=(OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,),
        )
        next_session = await self.sessions.advance(
            session,
            stage=OnboardingStage.CONCEPT_MODEL_PROPOSED,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return ConceptModelProposalAdmission(
            proposal=proposal,
            proposal_admission=admission,
            session=next_session,
        )

    async def revise(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        prior: ConceptModelProposalV1,
        edited: ConceptModelProposalV1,
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConceptModelProposalAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.CONCEPT_MODEL_PROPOSED:
            raise OntologyAgentError("concept-model edits require concept_model_proposed state")
        reference = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL)
        exact_prior = ConceptModelProposalV1.model_validate(prior.model_dump(mode="python"))
        exact_edited = ConceptModelProposalV1.model_validate(edited.model_dump(mode="python"))
        if (
            reference is None
            or reference.artifact_id != exact_prior.proposal_id
            or reference.artifact_digest != exact_prior.proposal_digest
            or exact_edited.prior_proposal_id != exact_prior.proposal_id
            or exact_edited.prior_proposal_digest != exact_prior.proposal_digest
            or exact_edited.revision != exact_prior.revision + 1
            or exact_edited.session_id != session.session_id
            or exact_edited.correlation_id != session.correlation_id
            or exact_edited.goal_ref != session.goal_ref
            or exact_edited.user_intent != exact_prior.user_intent
            or exact_edited.source_profile_proposal_id != exact_prior.source_profile_proposal_id
            or exact_edited.source_profile_proposal_digest != exact_prior.source_profile_proposal_digest
        ):
            raise OntologyAgentStaleProposal("edited proposal does not extend the exact current revision")
        expected_diff = concept_model_semantic_diff(exact_prior, exact_edited)
        if not expected_diff or exact_edited.semantic_diff != expected_diff:
            raise OntologyAgentError("edited proposal semantic diff does not match exact revision changes")
        persisted_prior = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
        if persisted_prior != exact_prior:
            raise OntologyAgentStaleProposal("prior proposal body differs from durable material")
        source_reference = _current_reference(session, OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL)
        if source_reference is None:
            raise OntologyAgentStaleProposal("edited proposal lost its exact source-profile handoff")
        source_profile = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=source_reference,
            artifact_type=SourceProfileProposalV1,
            available_at=occurred_at,
        )
        self._validate_attribution(exact_edited, source_profile)
        return await self._persist_and_handoff(
            session,
            exact_edited,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )

    async def approve(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        proposal: ConceptModelProposalV1,
        approval_receipt_ref: str,
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConceptModelApprovalAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.CONCEPT_MODEL_PROPOSED:
            raise OntologyAgentError("concept-model approval requires concept_model_proposed state")
        exact = ConceptModelProposalV1.model_validate(proposal.model_dump(mode="python"))
        reference = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL)
        if (
            reference is None
            or reference.artifact_id != exact.proposal_id
            or reference.artifact_digest != exact.proposal_digest
        ):
            raise OntologyAgentStaleProposal("approval does not name the exact current concept-model revision")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
        if persisted != exact:
            raise OntologyAgentStaleProposal("approval proposal body differs from durable material")
        try:
            raw = await self.authority.resolve_approval(
                receipt_ref=approval_receipt_ref,
                product_id=session.product_id,
                subject_ref=str(exact.proposal_id),
                actor_ref=actor_ref,
                effective_at=occurred_at,
            )
            approval = ResolvedApprovalReceiptV1.model_validate(raw.model_dump(mode="python"))
        except Exception:
            raise OntologyAgentError("concept-model approval failed exact Core resolution") from None
        if (
            approval.receipt_ref != approval_receipt_ref
            or approval.product_id != session.product_id
            or approval.subject_ref != exact.proposal_id
            or approval.actor_ref != actor_ref
            or approval.approved_at > occurred_at
        ):
            raise OntologyAgentError("concept-model approval does not bind exact current material")
        disposition = ConceptModelDispositionV1(
            session_id=session.session_id,
            proposal_id=str(exact.proposal_id),
            proposal_digest=str(exact.proposal_digest),
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            approved_at=occurred_at,
        )
        disposition_admission = await self.sessions.persist_artifact(
            product_id=session.product_id,
            artifact=disposition,
        )
        disposition_reference = _reference(
            OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,
            str(disposition.disposition_id),
            str(disposition.disposition_digest),
        )
        artifacts = _replace_reference(session.artifacts, disposition_reference)
        approved_session = await self.sessions.advance(
            session,
            stage=OnboardingStage.CONCEPT_MODEL_APPROVED,
            authority=OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return ConceptModelApprovalAdmission(
            proposal=exact,
            disposition=disposition,
            disposition_admission=disposition_admission,
            session=approved_session,
        )


__all__ = [
    "ConceptModelApprovalAdmission",
    "ConceptModelProposalAdmission",
    "ConceptModelStrategy",
    "OntologyAgent",
    "OntologyAgentAttributionError",
    "OntologyAgentError",
    "OntologyAgentOutcome",
    "OntologyAgentStaleProposal",
]
