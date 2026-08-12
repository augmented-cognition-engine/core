from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.briefing_agent import (
    BriefingAgent,
    BriefingAgentAttributionError,
    BriefingAgentError,
)
from ace.application.briefing_agent_contracts import BriefingItemV1, FirstBriefingPreviewV1
from ace.application.intelligence_agent import IntelligenceAgent
from ace.application.intelligence_agent_contracts import IntelligenceModelDispositionV1
from ace.application.intelligence_builder import (
    IntelligenceBuilderSessionReplayConflict,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import OnboardingBlockReason, OnboardingStage
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver
from ace.testing.ontology_agent import exercise_ontology_agent_restart
from ace.testing.watch_brief import (
    FixtureBriefingStrategy,
    FixtureIntelligenceModelStrategy,
    edited_fixture_intelligence_model,
    exercise_watch_brief_restart,
    fixture_observations,
)

pytestmark = pytest.mark.unit

_WATCH_AT = datetime(2026, 8, 11, 12, 3, tzinfo=UTC)


async def _approved_watch():
    mapped = await exercise_ontology_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    approval_ref = "approval:briefing-test-intelligence-model"
    intelligence = IntelligenceAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=(approval_ref,)),
        strategy=FixtureIntelligenceModelStrategy(),
    )
    evidence = fixture_observations(mapped, admitted_at=_WATCH_AT)
    await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=_WATCH_AT,
    )
    outcome = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes in approved source-grounded records.",
        actor_ref="agent:intelligence",
        occurred_at=_WATCH_AT + timedelta(seconds=1),
    )
    initial = outcome.proposal
    edited_model = edited_fixture_intelligence_model(
        initial.proposal,
        created_at=_WATCH_AT + timedelta(seconds=2),
    )
    edited = await intelligence.revise(
        initial.session.revision,
        prior=initial.proposal,
        edited=edited_model,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=2),
    )
    approved = await intelligence.approve(
        edited.session.revision,
        proposal=edited.proposal,
        approval_receipt_ref=approval_ref,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=3),
    )
    return mapped, sessions, evidence, approved


async def _create(strategy):
    mapped, sessions, evidence, approved = await _approved_watch()
    agent = BriefingAgent(sessions=sessions, strategy=strategy)
    outcome = await agent.create_first_brief(
        approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=_WATCH_AT + timedelta(seconds=4),
    )
    return mapped, sessions, evidence, approved, agent, outcome


@pytest.mark.asyncio
async def test_first_brief_exposes_materiality_provenance_uncertainty_disagreement_and_unknown():
    result = await exercise_watch_brief_restart()
    brief = result.briefing.brief

    assert brief.executive_summary
    assert brief.as_of <= brief.generated_at
    assert len(brief.citations) == 4
    assert all(item.why_it_matters and item.uncertainty for item in brief.items)
    assert any(item.item_kind.value == "shift" for item in brief.items)
    assert {item.epistemic_classification.value for item in brief.items} == {
        "observation",
        "claim",
        "inference",
        "disagreement",
        "unknown",
    }
    assert result.restarted_brief == brief
    assert result.restarted_session_id == result.briefing.session.revision.revision_id
    assert not hasattr(BriefingAgent, "deliver")
    assert not hasattr(BriefingAgent, "execute_action")
    assert not hasattr(BriefingAgent, "activate")


class _FabricatedClaimStrategy(FixtureBriefingStrategy):
    async def synthesize(self, **kwargs):
        brief = await super().synthesize(**kwargs)
        first = brief.items[0]
        fabricated = BriefingItemV1(
            **first.model_dump(mode="python", exclude={"statement_ids"}),
            statement_ids=("invented_claim",),
        )
        return FirstBriefingPreviewV1(
            **brief.model_dump(mode="python", exclude={"brief_id", "brief_digest", "items"}),
            items=(fabricated, *brief.items[1:]),
        )


@pytest.mark.asyncio
async def test_fabricated_claim_without_approved_statement_fails_closed():
    with pytest.raises(BriefingAgentAttributionError, match="without an approved statement"):
        await _create(_FabricatedClaimStrategy())


class _CitationGapStrategy(FixtureBriefingStrategy):
    async def synthesize(self, **kwargs):
        brief = await super().synthesize(**kwargs)
        payload = brief.model_dump(mode="python", exclude={"brief_id", "brief_digest"})
        payload["citations"] = payload["citations"][:-1]

        class _Malformed:
            def model_dump(self, **_):
                return payload

        return _Malformed()


@pytest.mark.asyncio
async def test_citation_gap_fails_structured_validation_before_persistence():
    with pytest.raises(BriefingAgentError, match="structured validation"):
        await _create(_CitationGapStrategy())


@pytest.mark.asyncio
async def test_contract_refuses_hidden_disagreement_and_imperative_content():
    _, _, _, _, _, outcome = await _create(FixtureBriefingStrategy())
    brief = outcome.briefing.brief
    without_disagreement = tuple(item for item in brief.items if item.epistemic_classification.value != "disagreement")
    with pytest.raises(ValidationError):
        FirstBriefingPreviewV1(
            **brief.model_dump(mode="python", exclude={"brief_id", "brief_digest", "items"}),
            items=without_disagreement,
        )
    payload = brief.model_dump(mode="python", exclude={"brief_id", "brief_digest"})
    payload["send"] = {"channel": "external"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FirstBriefingPreviewV1.model_validate(payload)


class _NoMaterialStrategy:
    async def synthesize(self, **kwargs):
        return None


class _FailedStrategy:
    async def synthesize(self, **kwargs):
        raise RuntimeError("provider failed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "reason"),
    [
        (_NoMaterialStrategy(), OnboardingBlockReason.NO_MATERIAL_SHIFTS),
        (_FailedStrategy(), OnboardingBlockReason.SYNTHESIS_FAILURE),
    ],
)
async def test_no_material_items_and_synthesis_failure_are_resumable(strategy, reason):
    _, sessions, _, _, _, outcome = await _create(strategy)
    assert outcome.ready is False
    assert outcome.blocked_reason is reason
    assert outcome.blocked_session.revision.resume_stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
    retrying = await sessions.retry(
        outcome.blocked_session.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=5),
    )
    resumed = await sessions.resume(
        retrying.revision,
        actor_ref="principal:builder",
        occurred_at=_WATCH_AT + timedelta(seconds=6),
    )
    assert resumed.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED


@pytest.mark.asyncio
async def test_stale_intelligence_disposition_blocks_and_stale_session_fork_fails():
    mapped, sessions, evidence, approved = await _approved_watch()
    stale_disposition = IntelligenceModelDispositionV1(
        **approved.disposition.model_dump(
            mode="python",
            exclude={"disposition_id", "disposition_digest", "approval_receipt_ref"},
        ),
        approval_receipt_ref="approval:stale",
    )
    agent = BriefingAgent(sessions=sessions, strategy=FixtureBriefingStrategy())
    blocked = await agent.create_first_brief(
        approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=stale_disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=_WATCH_AT + timedelta(seconds=4),
    )
    assert blocked.blocked_reason is OnboardingBlockReason.STALE_INTELLIGENCE_INPUT

    fresh = await _approved_watch()
    mapped, sessions, evidence, approved = fresh
    agent = BriefingAgent(sessions=sessions, strategy=FixtureBriefingStrategy())
    first = await agent.create_first_brief(
        approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=_WATCH_AT + timedelta(seconds=4),
    )
    assert first.ready
    with pytest.raises(IntelligenceBuilderSessionReplayConflict, match="stale"):
        await agent.create_first_brief(
            approved.session.revision,
            concept_model=mapped.restarted_proposal,
            concept_disposition=mapped.restarted_disposition,
            intelligence_model=approved.proposal,
            intelligence_disposition=approved.disposition,
            observations=evidence,
            actor_ref="agent:briefing",
            occurred_at=_WATCH_AT + timedelta(seconds=5),
        )
