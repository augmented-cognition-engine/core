"""Effect-free 0.7D Briefing Agent over exact approved onboarding material."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.application.briefing_agent_contracts import FirstBriefingPreviewV1
from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    EpistemicClassification,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
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
)
from ace.application.ontology_agent_contracts import ConceptModelDispositionV1, ConceptModelProposalV1


class BriefingAgentError(RuntimeError):
    """The Briefing Agent failed before producing a safe first-Brief handoff."""


class BriefingAgentStaleInput(BriefingAgentError):
    """Brief synthesis did not start from exact current durable material."""


class BriefingAgentAttributionError(BriefingAgentError):
    """Brief content does not close over exact approved statements and evidence."""


class BriefingStrategy(Protocol):
    """Optional host strategy without persistence, delivery, decision, action, or activation ports."""

    async def synthesize(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        generated_at: datetime,
    ) -> FirstBriefingPreviewV1 | None: ...


@dataclass(frozen=True, slots=True)
class FirstBriefingAdmission:
    brief: FirstBriefingPreviewV1
    brief_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class BriefingAgentOutcome:
    briefing: FirstBriefingAdmission | None
    blocked_session: IntelligenceBuilderSessionAdmission | None
    blocked_reason: OnboardingBlockReason | None

    @property
    def ready(self) -> bool:
        return self.briefing is not None and self.blocked_reason is None


def _current_reference(
    session: IntelligenceBuilderSessionRevisionV1,
    kind: OnboardingArtifactKind,
) -> OnboardingArtifactReferenceV1 | None:
    return next((item for item in session.artifacts if item.artifact_kind is kind), None)


class BriefingAgent:
    """Produce and persist one deterministic preview; perform no external effect."""

    def __init__(self, *, sessions: IntelligenceBuilderSessionService, strategy: BriefingStrategy) -> None:
        self.sessions = sessions
        self.strategy = strategy

    async def _require_exact_artifact(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        *,
        kind: OnboardingArtifactKind,
        artifact,
        artifact_type,
        artifact_id: str,
        artifact_digest: str,
        occurred_at: datetime,
    ):
        reference = _current_reference(session, kind)
        if reference is None or reference.artifact_id != artifact_id or reference.artifact_digest != artifact_digest:
            raise BriefingAgentStaleInput(f"{kind.value} is not the exact current handoff")
        persisted = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=artifact_type,
            available_at=occurred_at,
        )
        if persisted != artifact:
            raise BriefingAgentStaleInput(f"{kind.value} body differs from durable handoff material")
        return persisted

    async def _exact_inputs(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        *,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        occurred_at: datetime,
    ) -> tuple[
        ConceptModelProposalV1,
        ConceptModelDispositionV1,
        IntelligenceModelProposalV1,
        IntelligenceModelDispositionV1,
        AuthorizedObservationSetV1,
    ]:
        latest = await self.sessions.load_latest(
            product_id=session.product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != session.revision_id:
            raise BriefingAgentStaleInput("Briefing Agent started from a stale session revision")
        model = ConceptModelProposalV1.model_validate(concept_model.model_dump(mode="python"))
        model_disposition = ConceptModelDispositionV1.model_validate(concept_disposition.model_dump(mode="python"))
        intelligence = IntelligenceModelProposalV1.model_validate(intelligence_model.model_dump(mode="python"))
        intelligence_disposition_exact = IntelligenceModelDispositionV1.model_validate(
            intelligence_disposition.model_dump(mode="python")
        )
        evidence = AuthorizedObservationSetV1.model_validate(observations.model_dump(mode="python"))
        await self._require_exact_artifact(
            session,
            kind=OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
            artifact=model,
            artifact_type=ConceptModelProposalV1,
            artifact_id=str(model.proposal_id),
            artifact_digest=str(model.proposal_digest),
            occurred_at=occurred_at,
        )
        await self._require_exact_artifact(
            session,
            kind=OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,
            artifact=model_disposition,
            artifact_type=ConceptModelDispositionV1,
            artifact_id=str(model_disposition.disposition_id),
            artifact_digest=str(model_disposition.disposition_digest),
            occurred_at=occurred_at,
        )
        await self._require_exact_artifact(
            session,
            kind=OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL,
            artifact=intelligence,
            artifact_type=IntelligenceModelProposalV1,
            artifact_id=str(intelligence.proposal_id),
            artifact_digest=str(intelligence.proposal_digest),
            occurred_at=occurred_at,
        )
        await self._require_exact_artifact(
            session,
            kind=OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION,
            artifact=intelligence_disposition_exact,
            artifact_type=IntelligenceModelDispositionV1,
            artifact_id=str(intelligence_disposition_exact.disposition_id),
            artifact_digest=str(intelligence_disposition_exact.disposition_digest),
            occurred_at=occurred_at,
        )
        await self._require_exact_artifact(
            session,
            kind=OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
            artifact=evidence,
            artifact_type=AuthorizedObservationSetV1,
            artifact_id=str(evidence.observation_set_id),
            artifact_digest=str(evidence.observation_set_digest),
            occurred_at=occurred_at,
        )
        if (
            model_disposition.proposal_id != model.proposal_id
            or model_disposition.proposal_digest != model.proposal_digest
            or intelligence_disposition_exact.proposal_id != intelligence.proposal_id
            or intelligence_disposition_exact.proposal_digest != intelligence.proposal_digest
            or intelligence.concept_model_proposal_id != model.proposal_id
            or intelligence.concept_model_disposition_id != model_disposition.disposition_id
            or intelligence.observation_set_id != evidence.observation_set_id
            or any(item.session_id != session.session_id for item in (model, evidence))
        ):
            raise BriefingAgentStaleInput("Briefing Agent inputs crossed exact approved handoffs")
        return model, model_disposition, intelligence, intelligence_disposition_exact, evidence

    @staticmethod
    def _validate_attribution(
        brief: FirstBriefingPreviewV1,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        observations: AuthorizedObservationSetV1,
    ) -> None:
        derivation = brief.derivation
        if (
            derivation.session_id != session.session_id
            or derivation.correlation_id != session.correlation_id
            or derivation.concept_model_proposal_id != concept_model.proposal_id
            or derivation.concept_model_proposal_digest != concept_model.proposal_digest
            or derivation.concept_model_disposition_id != concept_disposition.disposition_id
            or derivation.concept_model_disposition_digest != concept_disposition.disposition_digest
            or derivation.intelligence_model_proposal_id != intelligence_model.proposal_id
            or derivation.intelligence_model_proposal_digest != intelligence_model.proposal_digest
            or derivation.intelligence_model_disposition_id != intelligence_disposition.disposition_id
            or derivation.intelligence_model_disposition_digest != intelligence_disposition.disposition_digest
            or derivation.observation_set_id != observations.observation_set_id
            or derivation.observation_set_digest != observations.observation_set_digest
        ):
            raise BriefingAgentStaleInput("Brief derivation does not bind exact approved inputs")
        evidence = {str(item.observation_id): item for item in observations.observations}
        model_citations = {item.citation_id: item for item in intelligence_model.citations}
        for citation in brief.citations:
            expected = model_citations.get(citation.citation_id)
            observation = evidence.get(citation.observation_id)
            if (
                expected != citation
                or observation is None
                or citation.observation_digest != observation.observation_digest
            ):
                raise BriefingAgentAttributionError("Brief citation is fabricated or outside admitted evidence")
        statements = {item.statement_id: item for item in intelligence_model.epistemic_statements}
        for item in brief.items:
            bound = [statements.get(statement_id) for statement_id in item.statement_ids]
            if any(statement is None for statement in bound):
                raise BriefingAgentAttributionError("Brief item contains a claim without an approved statement")
            if item.epistemic_classification not in {statement.classification for statement in bound if statement}:
                raise BriefingAgentAttributionError("Brief item changes the approved epistemic classification")
        disclosed_disagreement_observations = {
            model_citations[citation_id].observation_id
            for item in brief.items
            if item.epistemic_classification is EpistemicClassification.DISAGREEMENT
            for citation_id in item.citation_ids
        }
        required_disagreement_observations = {
            str(observation.observation_id)
            for observation in observations.observations
            if observation.disagrees_with_observation_ids
        } | {
            target for observation in observations.observations for target in observation.disagrees_with_observation_ids
        }
        if not required_disagreement_observations.issubset(disclosed_disagreement_observations):
            raise BriefingAgentAttributionError("Brief silently suppresses admitted source disagreement")

    async def create_first_brief(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        actor_ref: str,
        occurred_at: datetime,
    ) -> BriefingAgentOutcome:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage is not OnboardingStage.INTELLIGENCE_MODEL_APPROVED:
            raise BriefingAgentError("Briefing Agent requires intelligence_model_approved state")
        try:
            model, model_disposition, intelligence, intelligence_disposition_exact, evidence = await self._exact_inputs(
                session,
                concept_model=concept_model,
                concept_disposition=concept_disposition,
                intelligence_model=intelligence_model,
                intelligence_disposition=intelligence_disposition,
                observations=observations,
                occurred_at=occurred_at,
            )
        except BriefingAgentStaleInput:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.STALE_INTELLIGENCE_INPUT,
                actor_ref=actor_ref,
                safe_diagnostic="Brief synthesis inputs are no longer the exact approved handoff",
                occurred_at=occurred_at,
            )
            return BriefingAgentOutcome(None, blocked, OnboardingBlockReason.STALE_INTELLIGENCE_INPUT)
        if not evidence.closure_complete:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.INSUFFICIENT_EVIDENCE_CLOSURE,
                actor_ref=actor_ref,
                safe_diagnostic="Brief synthesis requires complete admitted evidence closure",
                occurred_at=occurred_at,
            )
            return BriefingAgentOutcome(None, blocked, OnboardingBlockReason.INSUFFICIENT_EVIDENCE_CLOSURE)
        try:
            raw = await self.strategy.synthesize(
                session=session,
                concept_model=model,
                concept_disposition=model_disposition,
                intelligence_model=intelligence,
                intelligence_disposition=intelligence_disposition_exact,
                observations=evidence,
                generated_at=occurred_at,
            )
        except Exception:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.SYNTHESIS_FAILURE,
                actor_ref=actor_ref,
                safe_diagnostic="first-Brief synthesis failed before producing valid material",
                occurred_at=occurred_at,
            )
            return BriefingAgentOutcome(None, blocked, OnboardingBlockReason.SYNTHESIS_FAILURE)
        if raw is None:
            blocked = await self.sessions.block(
                session,
                reason=OnboardingBlockReason.NO_MATERIAL_SHIFTS,
                actor_ref=actor_ref,
                safe_diagnostic="no material items were available for the first Brief",
                occurred_at=occurred_at,
            )
            return BriefingAgentOutcome(None, blocked, OnboardingBlockReason.NO_MATERIAL_SHIFTS)
        try:
            brief = FirstBriefingPreviewV1.model_validate(raw.model_dump(mode="python"))
            self._validate_attribution(
                brief,
                session=session,
                concept_model=model,
                concept_disposition=model_disposition,
                intelligence_model=intelligence,
                intelligence_disposition=intelligence_disposition_exact,
                observations=evidence,
            )
        except (BriefingAgentAttributionError, BriefingAgentStaleInput):
            raise
        except Exception:
            raise BriefingAgentError("first-Brief output failed exact structured validation") from None
        admission = await self.sessions.persist_artifact(product_id=session.product_id, artifact=brief)
        brief_ref = OnboardingArtifactReferenceV1(
            artifact_kind=OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW,
            artifact_id=str(brief.brief_id),
            artifact_digest=str(brief.brief_digest),
        )
        artifacts = tuple(
            item
            for item in session.artifacts
            if item.artifact_kind is not OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW
        ) + (brief_ref,)
        next_session = await self.sessions.advance(
            session,
            stage=OnboardingStage.FIRST_BRIEFING_READY,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return BriefingAgentOutcome(FirstBriefingAdmission(brief, admission, next_session), None, None)


__all__ = [
    "BriefingAgent",
    "BriefingAgentAttributionError",
    "BriefingAgentError",
    "BriefingAgentOutcome",
    "BriefingAgentStaleInput",
    "BriefingStrategy",
    "FirstBriefingAdmission",
]
