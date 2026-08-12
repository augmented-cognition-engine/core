"""Proposal-only 0.7D Intelligence Agent application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
    ProposedCadence,
    intelligence_model_semantic_diff,
)
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
from ace.application.ontology_agent_contracts import ConceptModelDispositionV1, ConceptModelProposalV1
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1


class IntelligenceAgentError(RuntimeError):
    """The Intelligence Agent failed before producing a safe proposal handoff."""


class IntelligenceAgentStaleInput(IntelligenceAgentError):
    """An input or session is not the exact current durable handoff."""


class IntelligenceAgentAttributionError(IntelligenceAgentError):
    """Evidence or a proposal citation is outside the exact admitted closure."""


class IntelligenceModelStrategy(Protocol):
    """Optional host strategy with no connector, persistence, scheduling, or authority port."""

    async def propose(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        user_intent: str,
        audience_constraints: tuple[str, ...],
        cadence_constraints: tuple[ProposedCadence, ...],
        created_at: datetime,
    ) -> IntelligenceModelProposalV1: ...


@dataclass(frozen=True, slots=True)
class AuthorizedObservationSetAdmission:
    observation_set: AuthorizedObservationSetV1
    admission: IntelligenceBuilderArtifactAdmission


@dataclass(frozen=True, slots=True)
class IntelligenceModelProposalAdmission:
    proposal: IntelligenceModelProposalV1
    proposal_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class IntelligenceModelApprovalAdmission:
    proposal: IntelligenceModelProposalV1
    disposition: IntelligenceModelDispositionV1
    disposition_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class IntelligenceAgentOutcome:
    proposal: IntelligenceModelProposalAdmission | None
    blocked_session: IntelligenceBuilderSessionAdmission | None
    blocked_reason: OnboardingBlockReason | None

    @property
    def proposed(self) -> bool:
        return self.proposal is not None and self.blocked_reason is None


def _reference(kind: OnboardingArtifactKind, artifact_id: str, artifact_digest: str) -> OnboardingArtifactReferenceV1:
    return OnboardingArtifactReferenceV1(
        artifact_kind=kind,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
    )


def _current_reference(
    session: IntelligenceBuilderSessionRevisionV1,
    kind: OnboardingArtifactKind,
) -> OnboardingArtifactReferenceV1 | None:
    return next((item for item in session.artifacts if item.artifact_kind is kind), None)


def _replace_references(
    artifacts: tuple[OnboardingArtifactReferenceV1, ...],
    replacements: tuple[OnboardingArtifactReferenceV1, ...],
    *,
    remove: tuple[OnboardingArtifactKind, ...] = (),
) -> tuple[OnboardingArtifactReferenceV1, ...]:
    removed = set(remove) | {item.artifact_kind for item in replacements}
    return tuple(item for item in artifacts if item.artifact_kind not in removed) + replacements


class IntelligenceAgent:
    """Admit bounded evidence, then propose, revise, and approve an inert intelligence model."""

    def __init__(
        self,
        *,
        sessions: IntelligenceBuilderSessionService,
        authority: CoreAuthorityResolver,
        strategy: IntelligenceModelStrategy,
        minimum_confidence: float = 0.6,
    ) -> None:
        self.sessions = sessions
        self.authority = authority
        self.strategy = strategy
        self.minimum_confidence = minimum_confidence

    async def _require_current(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        *,
        occurred_at: datetime,
    ) -> None:
        latest = await self.sessions.load_latest(
            product_id=session.product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != session.revision_id:
            raise IntelligenceAgentStaleInput("Intelligence Agent started from a stale session revision")

    async def _exact_concept_context(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        *,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        occurred_at: datetime,
    ) -> tuple[ConceptModelProposalV1, ConceptModelDispositionV1]:
        model = ConceptModelProposalV1.model_validate(concept_model.model_dump(mode="python"))
        disposition = ConceptModelDispositionV1.model_validate(concept_disposition.model_dump(mode="python"))
        model_ref = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL)
        disposition_ref = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION)
        if (
            model_ref is None
            or disposition_ref is None
            or model_ref.artifact_id != model.proposal_id
            or model_ref.artifact_digest != model.proposal_digest
            or disposition_ref.artifact_id != disposition.disposition_id
            or disposition_ref.artifact_digest != disposition.disposition_digest
            or disposition.proposal_id != model.proposal_id
            or disposition.proposal_digest != model.proposal_digest
            or model.session_id != session.session_id
            or model.correlation_id != session.correlation_id
        ):
            raise IntelligenceAgentStaleInput("concept-model input is not the exact approved handoff")
        persisted_model = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=model_ref,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
        persisted_disposition = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=disposition_ref,
            artifact_type=ConceptModelDispositionV1,
            available_at=occurred_at,
        )
        if persisted_model != model or persisted_disposition != disposition:
            raise IntelligenceAgentStaleInput("concept-model body differs from durable approved material")
        return model, disposition

    async def _exact_source_profile(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        source_profile: SourceProfileProposalV1,
        *,
        occurred_at: datetime,
    ) -> SourceProfileProposalV1:
        profile = SourceProfileProposalV1.model_validate(source_profile.model_dump(mode="python"))
        reference = _current_reference(session, OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL)
        if (
            reference is None
            or reference.artifact_id != profile.proposal_id
            or reference.artifact_digest != profile.proposal_digest
            or profile.session_id != session.session_id
        ):
            raise IntelligenceAgentStaleInput("source-profile input is not the exact approved handoff")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=SourceProfileProposalV1,
            available_at=occurred_at,
        )
        if persisted != profile:
            raise IntelligenceAgentStaleInput("source-profile body differs from durable approved material")
        return profile

    @staticmethod
    def _validate_observation_attribution(
        observations: AuthorizedObservationSetV1,
        source_profile: SourceProfileProposalV1,
        concept_model: ConceptModelProposalV1,
    ) -> None:
        samples = {str(item.sample_id): item for item in source_profile.samples}
        entity_types = {item.type_id: item for item in concept_model.entity_types}
        for observation in observations.observations:
            sample = samples.get(observation.source_sample_id)
            entity = entity_types.get(observation.entity_type_id)
            declared_fields = set() if sample is None else {item.field_path.removeprefix("/") for item in sample.fields}
            attributes = observation.attributes.parsed_value()
            if (
                observations.session_id != concept_model.session_id
                or observations.source_profile_proposal_id != source_profile.proposal_id
                or observations.source_profile_proposal_digest != source_profile.proposal_digest
                or sample is None
                or observation.source_sample_digest != sample.sample_digest
                or observation.source_ref != sample.source_ref
                or observation.evidence_digest != sample.evidence_digest
                or entity is None
                or not isinstance(attributes, dict)
                or not set(attributes).issubset(declared_fields)
            ):
                raise IntelligenceAgentAttributionError(
                    "authorized observation does not bind exact source-profile and concept-model material"
                )

    async def admit_observations(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        source_profile: SourceProfileProposalV1,
        observations: AuthorizedObservationSetV1,
        occurred_at: datetime,
    ) -> AuthorizedObservationSetAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED:
            raise IntelligenceAgentError("observation admission requires concept_model_approved state")
        await self._require_current(session, occurred_at=occurred_at)
        model, _ = await self._exact_concept_context(
            session,
            concept_model=concept_model,
            concept_disposition=concept_disposition,
            occurred_at=occurred_at,
        )
        profile = await self._exact_source_profile(session, source_profile, occurred_at=occurred_at)
        exact = AuthorizedObservationSetV1.model_validate(observations.model_dump(mode="python"))
        if exact.session_id != session.session_id or exact.correlation_id != session.correlation_id:
            raise IntelligenceAgentStaleInput("observation set crossed the exact session handoff")
        self._validate_observation_attribution(exact, profile, model)
        admission = await self.sessions.persist_artifact(product_id=session.product_id, artifact=exact)
        return AuthorizedObservationSetAdmission(observation_set=exact, admission=admission)

    async def _load_observations(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        observations: AuthorizedObservationSetV1,
        *,
        occurred_at: datetime,
    ) -> AuthorizedObservationSetV1:
        exact = AuthorizedObservationSetV1.model_validate(observations.model_dump(mode="python"))
        reference = _reference(
            OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
            str(exact.observation_set_id),
            str(exact.observation_set_digest),
        )
        try:
            persisted = await self.sessions.load_artifact(
                product_id=session.product_id,
                reference=reference,
                artifact_type=AuthorizedObservationSetV1,
                available_at=occurred_at,
            )
        except Exception:
            raise IntelligenceAgentStaleInput("observation set is not exact admitted material") from None
        if (
            persisted != exact
            or exact.session_id != session.session_id
            or exact.correlation_id != session.correlation_id
        ):
            raise IntelligenceAgentStaleInput("observation set body differs from exact admitted material")
        return exact

    @staticmethod
    def _validate_proposal_attribution(
        proposal: IntelligenceModelProposalV1,
        observations: AuthorizedObservationSetV1,
        concept_model: ConceptModelProposalV1,
    ) -> None:
        evidence = {str(item.observation_id): item for item in observations.observations}
        entity_types = {item.type_id: item for item in concept_model.entity_types}
        relation_ids = {item.type_id for item in concept_model.relationship_types}
        for citation in proposal.citations:
            observation = evidence.get(citation.observation_id)
            fields = set() if observation is None else set(observation.attributes.parsed_value())
            if (
                observation is None
                or citation.observation_digest != observation.observation_digest
                or citation.source_ref != observation.source_ref
                or citation.evidence_digest != observation.evidence_digest
                or citation.field_path.removeprefix("/") not in fields
            ):
                raise IntelligenceAgentAttributionError("intelligence citation does not bind exact admitted evidence")
        for target in proposal.watch_targets:
            entity = entity_types.get(target.entity_type_id)
            if entity is None:
                raise IntelligenceAgentAttributionError("watch target names an undeclared entity type")
            if target.target_kind.value == "attribute":
                if target.member_id not in {item.attribute_id for item in entity.attributes}:
                    raise IntelligenceAgentAttributionError("watch target names an undeclared entity attribute")
            elif target.member_id not in relation_ids:
                raise IntelligenceAgentAttributionError("watch target names an undeclared relationship type")

    async def propose(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        user_intent: str,
        audience_constraints: tuple[str, ...] = (),
        cadence_constraints: tuple[ProposedCadence, ...] = (),
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceAgentOutcome:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED:
            raise IntelligenceAgentError("Intelligence Agent can propose only from concept_model_approved")
        await self._require_current(session, occurred_at=occurred_at)
        try:
            model, disposition = await self._exact_concept_context(
                session,
                concept_model=concept_model,
                concept_disposition=concept_disposition,
                occurred_at=occurred_at,
            )
            evidence = await self._load_observations(session, observations, occurred_at=occurred_at)
        except IntelligenceAgentStaleInput:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.STALE_INTELLIGENCE_INPUT,
                actor_ref=actor_ref,
                safe_diagnostic="concept-model or observation input is no longer the exact admitted handoff",
                occurred_at=occurred_at,
            )
            return IntelligenceAgentOutcome(None, blocked, OnboardingBlockReason.STALE_INTELLIGENCE_INPUT)
        if not evidence.closure_complete:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.INSUFFICIENT_EVIDENCE_CLOSURE,
                actor_ref=actor_ref,
                safe_diagnostic="authorized observations do not provide complete evidence closure",
                occurred_at=occurred_at,
                artifacts=session.artifacts
                + (
                    _reference(
                        OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
                        str(evidence.observation_set_id),
                        str(evidence.observation_set_digest),
                    ),
                ),
            )
            return IntelligenceAgentOutcome(None, blocked, OnboardingBlockReason.INSUFFICIENT_EVIDENCE_CLOSURE)
        try:
            raw = await self.strategy.propose(
                session=session,
                concept_model=model,
                concept_disposition=disposition,
                observations=evidence,
                user_intent=user_intent,
                audience_constraints=audience_constraints,
                cadence_constraints=cadence_constraints,
                created_at=occurred_at,
            )
            proposal = IntelligenceModelProposalV1.model_validate(raw.model_dump(mode="python"))
            if (
                proposal.session_id != session.session_id
                or proposal.correlation_id != session.correlation_id
                or proposal.goal_ref != session.goal_ref
                or proposal.concept_model_proposal_id != model.proposal_id
                or proposal.concept_model_proposal_digest != model.proposal_digest
                or proposal.concept_model_disposition_id != disposition.disposition_id
                or proposal.concept_model_disposition_digest != disposition.disposition_digest
                or proposal.observation_set_id != evidence.observation_set_id
                or proposal.observation_set_digest != evidence.observation_set_digest
            ):
                raise IntelligenceAgentStaleInput("strategy output crossed exact Intelligence Agent inputs")
            self._validate_proposal_attribution(proposal, evidence, model)
        except (IntelligenceAgentAttributionError, IntelligenceAgentStaleInput):
            raise
        except Exception:
            raise IntelligenceAgentError("intelligence-model strategy failed exact proposal validation") from None
        evidence_ref = _reference(
            OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
            str(evidence.observation_set_id),
            str(evidence.observation_set_digest),
        )
        if proposal.confidence < self.minimum_confidence:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.LOW_CONFIDENCE_INTELLIGENCE_MODEL,
                actor_ref=actor_ref,
                safe_diagnostic="intelligence-model proposal did not meet the declared confidence floor",
                occurred_at=occurred_at,
                artifacts=_replace_references(session.artifacts, (evidence_ref,)),
            )
            return IntelligenceAgentOutcome(None, blocked, OnboardingBlockReason.LOW_CONFIDENCE_INTELLIGENCE_MODEL)
        if any(item.blocks_proposal for item in proposal.conflicts):
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.CONFLICTING_EVIDENCE,
                actor_ref=actor_ref,
                safe_diagnostic="evidence disagreement prevents a safe intelligence-model handoff",
                occurred_at=occurred_at,
                artifacts=_replace_references(session.artifacts, (evidence_ref,)),
            )
            return IntelligenceAgentOutcome(None, blocked, OnboardingBlockReason.CONFLICTING_EVIDENCE)
        admission = await self._persist_and_handoff(
            session,
            proposal,
            evidence_ref=evidence_ref,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
        return IntelligenceAgentOutcome(admission, None, None)

    async def _persist_and_handoff(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        proposal: IntelligenceModelProposalV1,
        *,
        evidence_ref: OnboardingArtifactReferenceV1,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceModelProposalAdmission:
        proposal_admission = await self.sessions.persist_artifact(product_id=session.product_id, artifact=proposal)
        proposal_ref = _reference(
            OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL,
            str(proposal.proposal_id),
            str(proposal.proposal_digest),
        )
        artifacts = _replace_references(
            session.artifacts,
            (evidence_ref, proposal_ref),
            remove=(
                OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION,
                OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW,
            ),
        )
        next_session = await self.sessions.advance(
            session,
            stage=OnboardingStage.INTELLIGENCE_MODEL_PROPOSED,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return IntelligenceModelProposalAdmission(proposal, proposal_admission, next_session)

    async def revise(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        prior: IntelligenceModelProposalV1,
        edited: IntelligenceModelProposalV1,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceModelProposalAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.INTELLIGENCE_MODEL_PROPOSED:
            raise IntelligenceAgentError("intelligence-model edits require intelligence_model_proposed state")
        await self._require_current(session, occurred_at=occurred_at)
        exact_prior = IntelligenceModelProposalV1.model_validate(prior.model_dump(mode="python"))
        exact_edited = IntelligenceModelProposalV1.model_validate(edited.model_dump(mode="python"))
        current_ref = _current_reference(session, OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL)
        invariant_fields = (
            "session_id",
            "correlation_id",
            "goal_ref",
            "user_intent",
            "concept_model_proposal_id",
            "concept_model_proposal_digest",
            "concept_model_disposition_id",
            "concept_model_disposition_digest",
            "observation_set_id",
            "observation_set_digest",
        )
        if (
            current_ref is None
            or current_ref.artifact_id != exact_prior.proposal_id
            or current_ref.artifact_digest != exact_prior.proposal_digest
            or exact_edited.prior_proposal_id != exact_prior.proposal_id
            or exact_edited.prior_proposal_digest != exact_prior.proposal_digest
            or exact_edited.revision != exact_prior.revision + 1
            or any(getattr(exact_edited, field) != getattr(exact_prior, field) for field in invariant_fields)
        ):
            raise IntelligenceAgentStaleInput("edited proposal does not extend the exact current revision")
        expected_diff = intelligence_model_semantic_diff(exact_prior, exact_edited)
        if not expected_diff or exact_edited.semantic_diff != expected_diff:
            raise IntelligenceAgentError("edited proposal semantic diff does not match exact revision changes")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=current_ref,
            artifact_type=IntelligenceModelProposalV1,
            available_at=occurred_at,
        )
        if persisted != exact_prior:
            raise IntelligenceAgentStaleInput("prior intelligence-model body differs from durable material")
        evidence_ref = _current_reference(session, OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET)
        concept_ref = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL)
        if evidence_ref is None or concept_ref is None:
            raise IntelligenceAgentStaleInput("edited proposal lost exact evidence or concept handoff")
        evidence = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=evidence_ref,
            artifact_type=AuthorizedObservationSetV1,
            available_at=occurred_at,
        )
        concept = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=concept_ref,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
        self._validate_proposal_attribution(exact_edited, evidence, concept)
        return await self._persist_and_handoff(
            session,
            exact_edited,
            evidence_ref=evidence_ref,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )

    async def approve(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        proposal: IntelligenceModelProposalV1,
        approval_receipt_ref: str,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceModelApprovalAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.INTELLIGENCE_MODEL_PROPOSED:
            raise IntelligenceAgentError("intelligence-model approval requires intelligence_model_proposed state")
        await self._require_current(session, occurred_at=occurred_at)
        exact = IntelligenceModelProposalV1.model_validate(proposal.model_dump(mode="python"))
        reference = _current_reference(session, OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL)
        if (
            reference is None
            or reference.artifact_id != exact.proposal_id
            or reference.artifact_digest != exact.proposal_digest
        ):
            raise IntelligenceAgentStaleInput("approval does not name the exact current intelligence-model revision")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=IntelligenceModelProposalV1,
            available_at=occurred_at,
        )
        if persisted != exact:
            raise IntelligenceAgentStaleInput("approval proposal body differs from durable material")
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
            raise IntelligenceAgentError("intelligence-model approval failed exact Core resolution") from None
        if (
            approval.receipt_ref != approval_receipt_ref
            or approval.product_id != session.product_id
            or approval.subject_ref != exact.proposal_id
            or approval.actor_ref != actor_ref
            or approval.approved_at > occurred_at
        ):
            raise IntelligenceAgentError("intelligence-model approval does not bind exact current material")
        disposition = IntelligenceModelDispositionV1(
            session_id=session.session_id,
            proposal_id=str(exact.proposal_id),
            proposal_digest=str(exact.proposal_digest),
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            approved_at=occurred_at,
        )
        disposition_admission = await self.sessions.persist_artifact(
            product_id=session.product_id, artifact=disposition
        )
        disposition_ref = _reference(
            OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION,
            str(disposition.disposition_id),
            str(disposition.disposition_digest),
        )
        artifacts = _replace_references(session.artifacts, (disposition_ref,))
        approved_session = await self.sessions.advance(
            session,
            stage=OnboardingStage.INTELLIGENCE_MODEL_APPROVED,
            authority=OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return IntelligenceModelApprovalAdmission(exact, disposition, disposition_admission, approved_session)


__all__ = [
    "AuthorizedObservationSetAdmission",
    "IntelligenceAgent",
    "IntelligenceAgentAttributionError",
    "IntelligenceAgentError",
    "IntelligenceAgentOutcome",
    "IntelligenceAgentStaleInput",
    "IntelligenceModelApprovalAdmission",
    "IntelligenceModelProposalAdmission",
    "IntelligenceModelStrategy",
]
