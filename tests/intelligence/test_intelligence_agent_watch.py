from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.intelligence_agent import (
    IntelligenceAgent,
    IntelligenceAgentAttributionError,
    IntelligenceAgentError,
    IntelligenceAgentStaleInput,
)
from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    DetectorProposalV1,
    IntelligenceCitationV1,
    IntelligenceModelProposalV1,
    MaterialityRuleV1,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionError, IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import (
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
)
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver
from ace.testing.ontology_agent import exercise_ontology_agent_restart
from ace.testing.watch_brief import (
    FixtureIntelligenceModelStrategy,
    edited_fixture_intelligence_model,
    exercise_watch_brief_restart,
    fixture_observations,
)

pytestmark = pytest.mark.unit

_WATCH_AT = datetime(2026, 8, 11, 12, 3, tzinfo=UTC)
_INTENT = "Watch material changes in approved source-grounded records."


async def _watch_setup(*, strategy=None, approved=True, closure_complete=True):
    mapped = await exercise_ontology_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    approval_ref = "approval:intelligence-model"
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=(approval_ref,) if approved else ())
    agent = IntelligenceAgent(
        sessions=sessions,
        authority=authority,
        strategy=strategy or FixtureIntelligenceModelStrategy(),
    )
    observations = fixture_observations(mapped, admitted_at=_WATCH_AT)
    if not closure_complete:
        observations = AuthorizedObservationSetV1(
            **observations.model_dump(
                mode="python",
                exclude={"observation_set_id", "observation_set_digest", "closure_complete"},
            ),
            closure_complete=False,
        )
    admitted = await agent.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=observations,
        occurred_at=_WATCH_AT,
    )
    outcome = await agent.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=observations,
        user_intent=_INTENT,
        actor_ref="agent:intelligence",
        occurred_at=_WATCH_AT + timedelta(seconds=1),
    )
    return mapped, sessions, agent, approval_ref, admitted, outcome


@pytest.mark.asyncio
async def test_provider_free_watch_edit_approval_restart_and_deterministic_identity():
    first = await exercise_watch_brief_restart()
    second = await exercise_watch_brief_restart()

    assert first.initial.proposal.revision == 1
    assert first.edited.proposal.revision == 2
    assert first.edited.proposal.semantic_diff == ("materiality_rules.changed:value_materiality",)
    assert first.approved.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
    assert first.briefing.session.revision.stage is OnboardingStage.FIRST_BRIEFING_READY
    assert first.restarted_intelligence_model == first.edited.proposal
    assert first.restarted_intelligence_disposition == first.approved.disposition
    assert first.restarted_brief == first.briefing.brief
    assert (
        first.observations.observation_set.observation_set_id == second.observations.observation_set.observation_set_id
    )
    assert first.initial.proposal.proposal_id == second.initial.proposal.proposal_id
    assert first.edited.proposal.proposal_id == second.edited.proposal.proposal_id
    assert first.approved.disposition.disposition_id == second.approved.disposition.disposition_id
    assert first.briefing.brief.brief_id == second.briefing.brief.brief_id


@pytest.mark.asyncio
async def test_widened_observation_and_unadmitted_observation_set_fail_closed():
    mapped = await exercise_ontology_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    agent = IntelligenceAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=()),
        strategy=FixtureIntelligenceModelStrategy(),
    )
    observations = fixture_observations(mapped, admitted_at=_WATCH_AT)
    first = observations.observations[0]
    widened_attributes = first.attributes.__class__(value_json='{"invented":true,"status":"ready","value":72}')
    widened_first = first.__class__(
        **first.model_dump(
            mode="python",
            exclude={"observation_id", "observation_digest", "attributes"},
        ),
        attributes=widened_attributes,
    )
    second = observations.observations[1]
    widened_second = second.__class__(
        **second.model_dump(
            mode="python",
            exclude={"observation_id", "observation_digest", "disagrees_with_observation_ids"},
        ),
        disagrees_with_observation_ids=(str(widened_first.observation_id),),
    )
    widened = AuthorizedObservationSetV1(
        **observations.model_dump(
            mode="python",
            exclude={"observation_set_id", "observation_set_digest", "observations"},
        ),
        observations=(widened_first, widened_second),
    )
    with pytest.raises(IntelligenceAgentAttributionError, match="exact source-profile"):
        await agent.admit_observations(
            mapped.approved.session.revision,
            concept_model=mapped.restarted_proposal,
            concept_disposition=mapped.restarted_disposition,
            source_profile=mapped.source_profile,
            observations=widened,
            occurred_at=_WATCH_AT,
        )

    outcome = await agent.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=observations,
        user_intent=_INTENT,
        actor_ref="agent:intelligence",
        occurred_at=_WATCH_AT,
    )
    assert outcome.blocked_reason is OnboardingBlockReason.STALE_INTELLIGENCE_INPUT
    assert outcome.blocked_session.revision.resume_stage is OnboardingStage.CONCEPT_MODEL_APPROVED


class _InvalidCitationStrategy(FixtureIntelligenceModelStrategy):
    async def propose(self, **kwargs):
        proposal = await super().propose(**kwargs)
        citation = proposal.citations[0]
        invalid = IntelligenceCitationV1(
            **citation.model_dump(mode="python", exclude={"source_ref"}),
            source_ref="source:invented",
        )
        return IntelligenceModelProposalV1(
            **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_digest", "citations"}),
            citations=(invalid, *proposal.citations[1:]),
        )


@pytest.mark.asyncio
async def test_invalid_intelligence_citation_fails_before_proposal_persistence():
    with pytest.raises(IntelligenceAgentAttributionError, match="exact admitted evidence"):
        await _watch_setup(strategy=_InvalidCitationStrategy())


def test_unsupported_detector_and_imperative_effects_fail_contract_validation():
    with pytest.raises(ValidationError):
        DetectorProposalV1(
            detector_id="unsupported",
            target_id="record_value",
            strategy="execute_shell",  # type: ignore[arg-type]
            configuration={"contract": "ace.intelligence.canonical-json-value/v1alpha1", "value_json": "{}"},
            citation_ids=("citation",),
        )
    schema = IntelligenceModelProposalV1.model_json_schema()
    assert schema["properties"]["contract"]["const"] == "ace.application.intelligence-model-proposal/v1alpha1"
    assert "execute" not in schema["properties"]


@pytest.mark.asyncio
async def test_materiality_edit_requires_exact_computed_diff_and_stale_revision_cannot_approve():
    _, _, agent, approval_ref, _, outcome = await _watch_setup()
    assert outcome.proposal is not None
    initial = outcome.proposal
    honest = edited_fixture_intelligence_model(initial.proposal, created_at=_WATCH_AT + timedelta(seconds=2))
    dishonest = IntelligenceModelProposalV1(
        **honest.model_dump(mode="python", exclude={"proposal_id", "proposal_digest", "semantic_diff"}),
        semantic_diff=("unknowns.added:no_change",),
    )
    with pytest.raises(IntelligenceAgentError, match="semantic diff"):
        await agent.revise(
            initial.session.revision,
            prior=initial.proposal,
            edited=dishonest,
            actor_ref="principal:builder",
            occurred_at=_WATCH_AT + timedelta(seconds=2),
        )
    edited = await agent.revise(
        initial.session.revision,
        prior=initial.proposal,
        edited=honest,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=2),
    )
    with pytest.raises(IntelligenceAgentStaleInput, match="exact current"):
        await agent.approve(
            edited.session.revision,
            proposal=initial.proposal,
            approval_receipt_ref=approval_ref,
            actor_ref="principal:builder",
            occurred_at=_WATCH_AT + timedelta(seconds=3),
        )
    with pytest.raises(IntelligenceAgentStaleInput, match="stale session"):
        await agent.revise(
            initial.session.revision,
            prior=initial.proposal,
            edited=honest,
            actor_ref="principal:builder",
            occurred_at=_WATCH_AT + timedelta(seconds=3),
        )


@pytest.mark.asyncio
async def test_denied_self_approval_cannot_advance_or_bypass_boundary():
    _, sessions, agent, approval_ref, _, outcome = await _watch_setup(approved=False)
    assert outcome.proposal is not None
    proposed = outcome.proposal
    with pytest.raises(IntelligenceAgentError, match="Core resolution"):
        await agent.approve(
            proposed.session.revision,
            proposal=proposed.proposal,
            approval_receipt_ref=approval_ref,
            actor_ref="agent:intelligence",
            occurred_at=_WATCH_AT + timedelta(seconds=2),
        )
    latest = await sessions.load_latest(
        product_id=proposed.session.revision.product_id,
        session_id=proposed.session.revision.session_id,
        available_at=_WATCH_AT + timedelta(seconds=3),
    )
    assert latest.stage is OnboardingStage.INTELLIGENCE_MODEL_PROPOSED
    with pytest.raises(IntelligenceBuilderSessionError, match="different boundary"):
        await sessions.advance(
            latest,
            stage=OnboardingStage.INTELLIGENCE_MODEL_APPROVED,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref="agent:intelligence",
            occurred_at=_WATCH_AT + timedelta(seconds=3),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "reason"),
    [
        (FixtureIntelligenceModelStrategy(confidence=0.4), OnboardingBlockReason.LOW_CONFIDENCE_INTELLIGENCE_MODEL),
        (FixtureIntelligenceModelStrategy(blocking_conflict=True), OnboardingBlockReason.CONFLICTING_EVIDENCE),
    ],
)
async def test_low_confidence_and_blocking_conflict_are_resumable(strategy, reason):
    mapped, sessions, _, _, _, outcome = await _watch_setup(strategy=strategy)
    assert outcome.proposed is False
    assert outcome.blocked_reason is reason
    assert outcome.blocked_session.revision.resume_stage is OnboardingStage.CONCEPT_MODEL_APPROVED
    retrying = await sessions.retry(
        outcome.blocked_session.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=2),
    )
    resumed = await sessions.resume(
        retrying.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=3),
    )
    assert resumed.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED
    assert resumed.revision.session_id == mapped.approved.session.revision.session_id


@pytest.mark.asyncio
async def test_incomplete_evidence_closure_blocks_and_resumes():
    _, sessions, _, _, _, outcome = await _watch_setup(closure_complete=False)
    assert outcome.blocked_reason is OnboardingBlockReason.INSUFFICIENT_EVIDENCE_CLOSURE
    retrying = await sessions.retry(
        outcome.blocked_session.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=2),
    )
    resumed = await sessions.resume(
        retrying.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=3),
    )
    assert resumed.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED


def test_materiality_rule_rejects_unknown_effect_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MaterialityRuleV1.model_validate(
            {
                "rule_id": "value_materiality",
                "detector_id": "value_delta",
                "minimum_change": 10.0,
                "minimum_confidence": 0.7,
                "rationale": "Bounded threshold.",
                "citation_ids": ("citation",),
                "schedule": "run now",
            }
        )
