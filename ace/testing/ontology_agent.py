"""Provider-free fixtures for the public 0.7C Ontology Agent seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import (
    OnboardingArtifactKind,
    OnboardingStage,
    SourceProfileProposalV1,
)
from ace.application.ontology_agent import (
    ConceptModelApprovalAdmission,
    ConceptModelProposalAdmission,
    OntologyAgent,
)
from ace.application.ontology_agent_contracts import (
    ConceptAttributeV1,
    ConceptCitationV1,
    ConceptEntityTypeV1,
    ConceptModelDispositionV1,
    ConceptModelProposalV1,
    ConceptRelationshipTypeV1,
    ConceptTerminologyV1,
    ConceptValueKind,
    OrganizationTerminologyV1,
)
from ace.core.records import ImmutableRecordStore
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver, exercise_connection_agent_restart


class FixtureConceptModelStrategy:
    """Deterministic concept mapping with no model, network, clock, or mutable state."""

    def __init__(self, *, confidence: float = 0.92) -> None:
        self.confidence = confidence
        self.calls = 0

    async def propose(
        self,
        *,
        session,
        source_profile,
        user_intent,
        organization_terminology,
        created_at,
    ) -> ConceptModelProposalV1:
        self.calls += 1
        citations = []
        field_citations: dict[str, list[str]] = {}
        for sample in source_profile.samples:
            for field in sample.fields:
                citation_id = f"{sample.option_id}_{field.field_path.removeprefix('/').replace('/', '_')}"
                citations.append(
                    ConceptCitationV1(
                        citation_id=citation_id,
                        source_profile_proposal_id=str(source_profile.proposal_id),
                        source_profile_proposal_digest=str(source_profile.proposal_digest),
                        source_sample_id=str(sample.sample_id),
                        source_sample_digest=str(sample.sample_digest),
                        source_ref=sample.source_ref,
                        field_path=field.field_path,
                        evidence_digest=sample.evidence_digest,
                    )
                )
                field_citations.setdefault(field.field_path, []).append(citation_id)
        terms = tuple(
            ConceptTerminologyV1(
                term_id=item.term_id,
                preferred_term=item.preferred_term,
                definition=item.definition,
                synonyms=item.synonyms,
            )
            for item in organization_terminology
        ) or (
            ConceptTerminologyV1(
                term_id="record",
                preferred_term="Record",
                definition="One bounded item described by an approved source profile.",
                synonyms=("item",),
            ),
        )
        status_citations = tuple(field_citations["/status"])
        value_citations = tuple(field_citations["/value"])
        return ConceptModelProposalV1(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            goal_ref=session.goal_ref,
            user_intent=user_intent,
            source_profile_proposal_id=str(source_profile.proposal_id),
            source_profile_proposal_digest=str(source_profile.proposal_digest),
            revision=1,
            citations=tuple(citations),
            entity_types=(
                ConceptEntityTypeV1(
                    type_id="record",
                    display_name="Record",
                    definition="A source-grounded item whose status and value can be compared over time.",
                    aliases=("item",),
                    attributes=(
                        ConceptAttributeV1(
                            attribute_id="status",
                            display_name="Status",
                            value_kind=ConceptValueKind.STRING,
                            citation_ids=status_citations,
                            confidence=self.confidence,
                        ),
                        ConceptAttributeV1(
                            attribute_id="value",
                            display_name="Value",
                            value_kind=ConceptValueKind.NUMBER,
                            citation_ids=value_citations,
                            confidence=self.confidence,
                        ),
                    ),
                    citation_ids=tuple(item.citation_id for item in citations),
                    confidence=self.confidence,
                ),
            ),
            relationship_types=(
                ConceptRelationshipTypeV1(
                    type_id="related_record",
                    display_name="Related record",
                    definition="A source-grounded relation between records; its semantics remain to be confirmed.",
                    from_type_id="record",
                    to_type_id="record",
                    aliases=("related item",),
                    citation_ids=status_citations,
                    confidence=self.confidence,
                ),
            ),
            terminology=terms,
            exclusions=("No source credentials, connector configuration, monitoring policy, or activation authority.",),
            unknowns=("The fixture source profiles describe shape, not record identity or relationship semantics.",),
            confidence=self.confidence,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class OntologyAgentReferenceResult:
    initial: ConceptModelProposalAdmission
    edited: ConceptModelProposalAdmission
    approved: ConceptModelApprovalAdmission
    restarted_session_id: str
    restarted_proposal: ConceptModelProposalV1
    restarted_disposition: ConceptModelDispositionV1
    source_profile: SourceProfileProposalV1
    store: ImmutableRecordStore


def edited_fixture_proposal(
    proposal: ConceptModelProposalV1,
    *,
    created_at: datetime,
) -> ConceptModelProposalV1:
    terms = tuple(proposal.terminology) + (
        ConceptTerminologyV1(
            term_id="tracked_record",
            preferred_term="Tracked record",
            definition="Organization-preferred name for an approved source-grounded record.",
            synonyms=("watched item",),
        ),
    )
    return ConceptModelProposalV1(
        **proposal.model_dump(
            mode="python",
            exclude={
                "proposal_id",
                "proposal_digest",
                "revision",
                "prior_proposal_id",
                "prior_proposal_digest",
                "edit_summary",
                "semantic_diff",
                "terminology",
                "created_at",
            },
        ),
        revision=proposal.revision + 1,
        prior_proposal_id=str(proposal.proposal_id),
        prior_proposal_digest=str(proposal.proposal_digest),
        edit_summary="Use the organization's preferred tracked-record terminology.",
        semantic_diff=("terminology.added:tracked_record",),
        terminology=terms,
        created_at=created_at,
    )


async def exercise_ontology_agent_restart() -> OntologyAgentReferenceResult:
    """Connect, Map, edit, approve, and reopen exact proposal/disposition material."""

    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)
    approval_ref = "approval:fixture-concept-model"
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=(approval_ref,))
    strategy = FixtureConceptModelStrategy()
    agent = OntologyAgent(sessions=sessions, authority=authority, strategy=strategy)
    mapped_at = datetime(2026, 8, 11, 12, 1, tzinfo=UTC)
    proposed = await agent.propose(
        connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent="Understand the status and value of approved source-grounded records.",
        organization_terminology=(
            OrganizationTerminologyV1(
                term_id="record",
                preferred_term="Record",
                definition="A bounded source-grounded item.",
                synonyms=("item",),
            ),
        ),
        actor_ref="agent:ontology",
        occurred_at=mapped_at,
    )
    if not proposed.proposed or proposed.proposal is None:
        raise AssertionError("provider-free Ontology Agent did not produce a concept model")
    initial = proposed.proposal
    edited_model = edited_fixture_proposal(initial.proposal, created_at=mapped_at + timedelta(seconds=1))
    edited = await agent.revise(
        initial.session.revision,
        prior=initial.proposal,
        edited=edited_model,
        actor_ref="principal:fixture-builder",
        occurred_at=mapped_at + timedelta(seconds=1),
    )
    approved = await agent.approve(
        edited.session.revision,
        proposal=edited.proposal,
        approval_receipt_ref=approval_ref,
        actor_ref="principal:fixture-builder",
        occurred_at=mapped_at + timedelta(seconds=2),
    )
    restarted = IntelligenceBuilderSessionService(store=connected.store)
    reopened_session = await restarted.load_latest(
        product_id=approved.session.revision.product_id,
        session_id=approved.session.revision.session_id,
        available_at=mapped_at + timedelta(seconds=3),
    )
    if reopened_session is None or reopened_session.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED:
        raise AssertionError("fresh service did not reopen approved concept-model state")
    proposal_ref = next(
        item
        for item in reopened_session.artifacts
        if item.artifact_kind is OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL
    )
    disposition_ref = next(
        item
        for item in reopened_session.artifacts
        if item.artifact_kind is OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION
    )
    reopened_proposal = await restarted.load_artifact(
        product_id=reopened_session.product_id,
        reference=proposal_ref,
        artifact_type=ConceptModelProposalV1,
        available_at=mapped_at + timedelta(seconds=3),
    )
    reopened_disposition = await restarted.load_artifact(
        product_id=reopened_session.product_id,
        reference=disposition_ref,
        artifact_type=ConceptModelDispositionV1,
        available_at=mapped_at + timedelta(seconds=3),
    )
    if reopened_proposal != edited.proposal or reopened_disposition != approved.disposition:
        raise AssertionError("fresh service did not reopen exact approved proposal handoff")
    return OntologyAgentReferenceResult(
        initial=initial,
        edited=edited,
        approved=approved,
        restarted_session_id=reopened_session.revision_id,
        restarted_proposal=reopened_proposal,
        restarted_disposition=reopened_disposition,
        source_profile=connected.restarted_profile,
        store=connected.store,
    )


__all__ = [
    "FixtureConceptModelStrategy",
    "OntologyAgentReferenceResult",
    "edited_fixture_proposal",
    "exercise_ontology_agent_restart",
]
