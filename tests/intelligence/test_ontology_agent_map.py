from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.intelligence_builder import (
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceProfileProposalV1,
)
from ace.application.ontology_agent import (
    OntologyAgent,
    OntologyAgentAttributionError,
    OntologyAgentError,
    OntologyAgentStaleProposal,
)
from ace.application.ontology_agent_contracts import (
    ConceptCitationV1,
    ConceptConflictV1,
    ConceptEntityTypeV1,
    ConceptModelProposalV1,
    ConceptRelationshipTypeV1,
)
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver, exercise_connection_agent_restart
from ace.testing.ontology_agent import (
    FixtureConceptModelStrategy,
    edited_fixture_proposal,
    exercise_ontology_agent_restart,
)

pytestmark = pytest.mark.unit

_MAP_AT = datetime(2026, 8, 11, 12, 1, tzinfo=UTC)
_INTENT = "Understand approved source-grounded records."


async def _map_setup(*, strategy=None, approved=True):
    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)
    approval_ref = "approval:concept-model"
    authority = FixtureCoreAuthorityResolver(
        approved_receipt_refs=(approval_ref,) if approved else (),
    )
    exact_strategy = strategy or FixtureConceptModelStrategy()
    agent = OntologyAgent(sessions=sessions, authority=authority, strategy=exact_strategy)
    outcome = await agent.propose(
        connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent=_INTENT,
        actor_ref="agent:ontology",
        occurred_at=_MAP_AT,
    )
    return connected, sessions, agent, exact_strategy, approval_ref, outcome


@pytest.mark.asyncio
async def test_provider_free_map_edit_approval_restart_and_deterministic_identity():
    first = await exercise_ontology_agent_restart()
    second = await exercise_ontology_agent_restart()

    assert first.initial.proposal.revision == 1
    assert len(first.initial.proposal.citations) == 4
    assert first.edited.proposal.revision == 2
    assert first.edited.proposal.prior_proposal_id == first.initial.proposal.proposal_id
    assert first.edited.proposal.semantic_diff == ("terminology.added:tracked_record",)
    assert first.approved.session.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED
    assert first.restarted_proposal == first.edited.proposal
    assert first.restarted_disposition == first.approved.disposition
    assert first.restarted_session_id == first.approved.session.revision.revision_id
    assert first.initial.proposal.proposal_id == second.initial.proposal.proposal_id
    assert first.edited.proposal.proposal_id == second.edited.proposal.proposal_id
    assert first.approved.disposition.disposition_id == second.approved.disposition.disposition_id
    with pytest.raises(ValidationError):
        first.initial.proposal.user_intent = "Silently mutated intent"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_missing_or_widened_source_profile_is_refused():
    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)
    agent = OntologyAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=()),
        strategy=FixtureConceptModelStrategy(),
    )
    with pytest.raises(OntologyAgentStaleProposal, match="missing"):
        await agent.propose(
            connected.restarted_session,
            source_profile=None,  # type: ignore[arg-type]
            user_intent=_INTENT,
            actor_ref="agent:ontology",
            occurred_at=_MAP_AT,
        )

    material = connected.restarted_profile.model_dump(mode="python")
    sample = material["samples"][0]
    sample["scopes"] = (*sample["scopes"], "unapproved_scope")
    sample.pop("sample_id")
    sample.pop("sample_digest")
    material.pop("proposal_id")
    material.pop("proposal_digest")
    widened = SourceProfileProposalV1.model_validate(material)
    with pytest.raises(OntologyAgentStaleProposal, match="not the current exact handoff"):
        await agent.propose(
            connected.restarted_session,
            source_profile=widened,
            user_intent=_INTENT,
            actor_ref="agent:ontology",
            occurred_at=_MAP_AT,
        )


class _UnattributedStrategy(FixtureConceptModelStrategy):
    async def propose(self, **kwargs):
        proposal = await super().propose(**kwargs)
        citation = proposal.citations[0]
        bad = ConceptCitationV1(
            **citation.model_dump(mode="python", exclude={"source_ref"}),
            source_ref="source:invented",
        )
        return ConceptModelProposalV1(
            **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_digest", "citations"}),
            citations=(bad, *proposal.citations[1:]),
        )


@pytest.mark.asyncio
async def test_invented_or_invalid_citation_fails_before_persistence():
    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)
    agent = OntologyAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=()),
        strategy=_UnattributedStrategy(),
    )
    with pytest.raises(OntologyAgentAttributionError, match="exact admitted"):
        await agent.propose(
            connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent=_INTENT,
            actor_ref="agent:ontology",
            occurred_at=_MAP_AT,
        )
    latest = await sessions.load_latest(
        product_id=connected.restarted_session.product_id,
        session_id=connected.restarted_session.session_id,
        available_at=_MAP_AT,
    )
    assert latest == connected.restarted_session


def test_duplicate_and_colliding_type_ids_and_imperative_content_fail_validation():
    entity = ConceptEntityTypeV1(
        type_id="record",
        display_name="Record",
        definition="A cited item.",
        citation_ids=("citation_one",),
        confidence=0.9,
    )
    citation = ConceptCitationV1(
        citation_id="citation_one",
        source_profile_proposal_id="source_profile_proposal:fixture",
        source_profile_proposal_digest="sha256:" + "a" * 64,
        source_sample_id="source_sample:fixture",
        source_sample_digest="sha256:" + "b" * 64,
        source_ref="source:fixture",
        field_path="/status",
        evidence_digest="sha256:" + "c" * 64,
    )
    common = {
        "session_id": "session:fixture",
        "correlation_id": "correlation:fixture",
        "goal_ref": "goal:fixture",
        "user_intent": "Understand records.",
        "source_profile_proposal_id": "source_profile_proposal:fixture",
        "source_profile_proposal_digest": "sha256:" + "a" * 64,
        "revision": 1,
        "citations": (citation,),
        "exclusions": ("No activation.",),
        "confidence": 0.9,
        "created_at": _MAP_AT,
    }
    with pytest.raises(ValidationError, match="unique identifiers"):
        ConceptModelProposalV1(entity_types=(entity, entity), **common)
    with pytest.raises(ValidationError, match="must not collide"):
        ConceptModelProposalV1(
            entity_types=(entity,),
            relationship_types=(
                ConceptRelationshipTypeV1(
                    type_id="record",
                    display_name="Record relation",
                    definition="A relation.",
                    from_type_id="record",
                    to_type_id="record",
                    citation_ids=("citation_one",),
                    confidence=0.9,
                ),
            ),
            **common,
        )
    payload = {**common, "entity_types": (entity,), "execute": "import os"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConceptModelProposalV1.model_validate(payload)

    schema = ConceptModelProposalV1.model_json_schema()
    assert schema["properties"]["contract"]["const"] == "ace.application.concept-model-proposal/v1alpha1"
    assert "execute" not in schema["properties"]


@pytest.mark.asyncio
async def test_edit_is_immutable_and_stale_revision_cannot_be_approved():
    _, _, agent, _, approval_ref, outcome = await _map_setup()
    assert outcome.proposal is not None
    initial = outcome.proposal
    edited_model = edited_fixture_proposal(initial.proposal, created_at=_MAP_AT + timedelta(seconds=1))
    edited = await agent.revise(
        initial.session.revision,
        prior=initial.proposal,
        edited=edited_model,
        actor_ref="principal:builder",
        occurred_at=_MAP_AT + timedelta(seconds=1),
    )
    assert initial.proposal.revision == 1
    assert initial.proposal.proposal_id != edited.proposal.proposal_id
    with pytest.raises(OntologyAgentStaleProposal, match="exact current"):
        await agent.approve(
            edited.session.revision,
            proposal=initial.proposal,
            approval_receipt_ref=approval_ref,
            actor_ref="principal:builder",
            occurred_at=_MAP_AT + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_edit_cannot_hide_actual_changes_behind_a_silent_semantic_diff():
    _, _, agent, _, _, outcome = await _map_setup()
    assert outcome.proposal is not None
    initial = outcome.proposal
    honest = edited_fixture_proposal(initial.proposal, created_at=_MAP_AT + timedelta(seconds=1))
    dishonest = ConceptModelProposalV1(
        **honest.model_dump(
            mode="python",
            exclude={"proposal_id", "proposal_digest", "semantic_diff"},
        ),
        semantic_diff=("unknowns.added:nothing_material",),
    )
    with pytest.raises(OntologyAgentError, match="does not match exact revision changes"):
        await agent.revise(
            initial.session.revision,
            prior=initial.proposal,
            edited=dishonest,
            actor_ref="principal:builder",
            occurred_at=_MAP_AT + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_agent_cannot_self_approve_and_denied_approval_does_not_advance():
    _, sessions, agent, _, approval_ref, outcome = await _map_setup(approved=False)
    assert outcome.proposal is not None
    proposed = outcome.proposal
    with pytest.raises(OntologyAgentError, match="Core resolution"):
        await agent.approve(
            proposed.session.revision,
            proposal=proposed.proposal,
            approval_receipt_ref=approval_ref,
            actor_ref="agent:ontology",
            occurred_at=_MAP_AT + timedelta(seconds=1),
        )
    latest = await sessions.load_latest(
        product_id=proposed.session.revision.product_id,
        session_id=proposed.session.revision.session_id,
        available_at=_MAP_AT + timedelta(seconds=2),
    )
    assert latest.stage is OnboardingStage.CONCEPT_MODEL_PROPOSED
    with pytest.raises(IntelligenceBuilderSessionError, match="different boundary"):
        await sessions.advance(
            latest,
            stage=OnboardingStage.CONCEPT_MODEL_APPROVED,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref="agent:ontology",
            occurred_at=_MAP_AT + timedelta(seconds=2),
        )


class _ConflictingStrategy(FixtureConceptModelStrategy):
    async def propose(self, **kwargs):
        proposal = await super().propose(**kwargs)
        return ConceptModelProposalV1(
            **proposal.model_dump(
                mode="python",
                exclude={"proposal_id", "proposal_digest", "conflicts"},
            ),
            conflicts=(
                ConceptConflictV1(
                    conflict_id="status_disagreement",
                    description="Approved sources disagree about status meaning.",
                    citation_ids=("source_alpha_status", "source_beta_status"),
                    blocks_mapping=True,
                ),
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "reason"),
    [
        (FixtureConceptModelStrategy(confidence=0.4), OnboardingBlockReason.LOW_CONFIDENCE_MAPPING),
        (_ConflictingStrategy(), OnboardingBlockReason.CONFLICTING_SOURCES),
    ],
)
async def test_low_confidence_and_contradictory_input_persist_resumable_blocked_state(strategy, reason):
    connected, sessions, _, _, _, outcome = await _map_setup(strategy=strategy)
    assert outcome.proposed is False
    assert outcome.blocked_reason is reason
    assert outcome.blocked_session.revision.resume_stage is OnboardingStage.SOURCES_READY
    restarted = IntelligenceBuilderSessionService(store=connected.store)
    loaded = await restarted.load_latest(
        product_id=connected.restarted_session.product_id,
        session_id=connected.restarted_session.session_id,
        available_at=_MAP_AT + timedelta(seconds=1),
    )
    assert loaded == outcome.blocked_session.revision
    retrying = await restarted.retry(loaded, actor_ref="principal:builder", occurred_at=_MAP_AT + timedelta(seconds=1))
    resumed = await restarted.resume(
        retrying.revision,
        actor_ref="principal:builder",
        occurred_at=_MAP_AT + timedelta(seconds=2),
    )
    assert resumed.revision.stage is OnboardingStage.SOURCES_READY
