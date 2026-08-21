"""Production selected-provider Builder strategy adapters: exact Agent satisfaction and fail-closed rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest

from ace.application.briefing_agent import BriefingAgent
from ace.application.briefing_agent_contracts import BriefingItemKind
from ace.application.intelligence_agent import IntelligenceAgent
from ace.application.intelligence_agent_contracts import EpistemicClassification, ProposedCadence
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingArtifactKind, OnboardingStage
from ace.application.ontology_agent import OntologyAgent
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver, exercise_connection_agent_restart
from ace.testing.ontology_agent import OntologyAgentReferenceResult, exercise_ontology_agent_restart
from ace.testing.watch_brief import FixtureIntelligenceModelStrategy, fixture_observations
from core.engine.core.intelligence_builder_strategies import (
    SelectedBriefingStrategy,
    SelectedBuilderStrategyConflict,
    SelectedBuilderStrategyUnavailable,
    SelectedConceptModelStrategy,
    SelectedIntelligenceModelStrategy,
)

pytestmark = pytest.mark.unit


class _SpyProvider:
    """Deterministic in-test structured-completion double; records every exact prompt."""

    def __init__(self, respond: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.respond = respond
        self.prompts: list[str] = []
        self.calls = 0

    async def complete_json(self, prompt: str, *, model: str | None, max_tokens: int) -> dict[str, Any]:
        self.prompts.append(prompt)
        self.calls += 1
        parsed = json.loads(prompt)
        return self.respond(parsed)


class _RaisingProvider:
    async def complete_json(self, prompt: str, *, model: str | None, max_tokens: int) -> dict[str, Any]:
        raise RuntimeError("secret transport detail")


def _concept_response(parsed: dict[str, Any]) -> dict[str, Any]:
    source_profile = parsed["trusted_context"]["source_profile"]
    citations: list[dict[str, str]] = []
    field_citations: dict[str, list[str]] = {}
    for sample in source_profile["samples"]:
        for field in sample["fields"]:
            citation_id = f"{sample['option_id']}_{field['field_path'].removeprefix('/')}"
            citations.append(
                {
                    "citation_id": citation_id,
                    "source_sample_id": sample["sample_id"],
                    "field_path": field["field_path"],
                }
            )
            field_citations.setdefault(field["field_path"], []).append(citation_id)
    status_citations = field_citations["/status"]
    value_citations = field_citations["/value"]
    all_citation_ids = [item["citation_id"] for item in citations]
    return {
        "citations": citations,
        "entity_types": [
            {
                "type_id": "record",
                "display_name": "Record",
                "definition": "A source-grounded item whose status and value can be compared over time.",
                "aliases": ["item"],
                "attributes": [
                    {
                        "attribute_id": "status",
                        "display_name": "Status",
                        "value_kind": "string",
                        "required": False,
                        "citation_ids": status_citations,
                        "confidence": 0.9,
                    },
                    {
                        "attribute_id": "value",
                        "display_name": "Value",
                        "value_kind": "number",
                        "required": False,
                        "citation_ids": value_citations,
                        "confidence": 0.9,
                    },
                ],
                "citation_ids": all_citation_ids,
                "confidence": 0.9,
            }
        ],
        "relationship_types": [],
        "terminology": [],
        "exclusions": [
            "No source credentials, connector configuration, monitoring policy, or activation authority.",
        ],
        "conflicts": [],
        "unknowns": [],
        "confidence": 0.9,
    }


def _intelligence_response(parsed: dict[str, Any]) -> dict[str, Any]:
    observations = parsed["trusted_context"]["observations"]["observations"]
    by_source = {item["source_ref"]: item for item in observations}
    alpha, beta = (by_source[key] for key in sorted(by_source))
    citations = [
        {"citation_id": "source_alpha_status", "observation_id": alpha["observation_id"], "field_path": "/status"},
        {"citation_id": "source_alpha_value", "observation_id": alpha["observation_id"], "field_path": "/value"},
        {"citation_id": "source_beta_status", "observation_id": beta["observation_id"], "field_path": "/status"},
        {"citation_id": "source_beta_value", "observation_id": beta["observation_id"], "field_path": "/value"},
    ]
    status_citations = ["source_alpha_status", "source_beta_status"]
    value_citations = ["source_alpha_value", "source_beta_value"]
    return {
        "citations": citations,
        "watch_targets": [
            {
                "target_id": "record_status",
                "target_kind": "attribute",
                "entity_type_id": "record",
                "member_id": "status",
                "citation_ids": status_citations,
            },
            {
                "target_id": "record_value",
                "target_kind": "attribute",
                "entity_type_id": "record",
                "member_id": "value",
                "citation_ids": value_citations,
            },
        ],
        "baselines": [
            {
                "baseline_id": "status_baseline",
                "target_id": "record_status",
                "value": {"contract": "ace.intelligence.canonical-json-value/v1alpha1", "value_json": '"pending"'},
                "as_of": alpha["observed_at"],
                "citation_ids": ["source_alpha_status"],
            },
        ],
        "detectors": [
            {
                "detector_id": "status_transition",
                "target_id": "record_status",
                "strategy": "categorical_transition",
                "configuration": {
                    "contract": "ace.intelligence.canonical-json-value/v1alpha1",
                    "value_json": '{"allowed_transitions":["pending->ready","pending->paused"]}',
                },
                "citation_ids": status_citations,
            },
        ],
        "materiality_rules": [
            {
                "rule_id": "status_materiality",
                "detector_id": "status_transition",
                "minimum_change": 1.0,
                "minimum_confidence": 0.7,
                "rationale": "A categorical transition changes the current operating state.",
                "citation_ids": status_citations,
            },
        ],
        "audiences": [
            {
                "audience_id": "reviewer",
                "display_name": "Reviewer",
                "purpose": "Review material source-grounded changes.",
            },
        ],
        "routes": [
            {
                "route_id": "reviewer_updates",
                "audience_ids": ["reviewer"],
                "target_ids": ["record_status", "record_value"],
                "cadence": "daily",
                "minimum_confidence": 0.7,
            },
        ],
        "suppression_grouping_rules": [
            {
                "rule_id": "group_record_updates",
                "target_ids": ["record_status", "record_value"],
                "group_by": ["subject_ref"],
                "suppress_below_confidence": 0.7,
                "rationale": "Group related updates and suppress only explicitly low-confidence items.",
            },
        ],
        "epistemic_statements": [
            {
                "statement_id": "status_observation",
                "classification": "observation",
                "statement": "The admitted observations report explicit current status values.",
                "citation_ids": status_citations,
                "confidence": 0.9,
            },
            {
                "statement_id": "value_claim",
                "classification": "claim",
                "statement": "The admitted values differ materially from the stated baseline.",
                "citation_ids": value_citations,
                "confidence": 0.9,
            },
            {
                "statement_id": "value_inference",
                "classification": "inference",
                "statement": "The value difference may warrant additional review under the proposed threshold.",
                "citation_ids": value_citations,
                "confidence": 0.76,
            },
            {
                "statement_id": "status_disagreement",
                "classification": "disagreement",
                "statement": "The two authorized sources disagree about the same subject's current status.",
                "citation_ids": status_citations,
                "confidence": 0.88,
            },
            {
                "statement_id": "relationship_unknown",
                "classification": "unknown",
                "statement": "The admitted evidence does not resolve the proposed relationship semantics.",
                "citation_ids": status_citations,
                "confidence": 0.55,
            },
        ],
        "conflicts": [
            {
                "conflict_id": "status_disagreement",
                "description": "Authorized sources report different status values for the same subject.",
                "citation_ids": status_citations,
                "blocks_proposal": False,
            },
        ],
        "unknowns": ["Relationship semantics remain unresolved by the admitted observations."],
        "exclusions": [
            "No scheduling, connector access, delivery, activation, grant creation, or authoritative monitor state.",
        ],
        "confidence": 0.9,
    }


def _brief_response(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "First source-grounded briefing",
        "executive_summary": (
            "Admitted values exceed the proposed materiality threshold, while authorized sources disagree "
            "about current status and relationship semantics remain unknown."
        ),
        "items": [
            {
                "item_id": "observed_current_status",
                "item_kind": "current_state",
                "title": "Current status observations",
                "summary": "The authorized sources each provide a current status observation.",
                "why_it_matters": "The observations establish the exact evidence behind the later disagreement.",
                "epistemic_classification": "observation",
                "statement_ids": ["status_observation"],
                "citation_ids": ["source_alpha_status", "source_beta_status"],
                "confidence": 0.91,
                "uncertainty": "The observations are source reports and do not resolve source authority.",
            },
            {
                "item_id": "material_value_shift",
                "item_kind": "shift",
                "title": "Material value difference",
                "summary": "Both admitted values differ from the proposed baseline by at least the material threshold.",
                "why_it_matters": "The difference warrants reviewer attention under the approved intelligence model.",
                "epistemic_classification": "claim",
                "statement_ids": ["value_claim"],
                "citation_ids": ["source_alpha_value", "source_beta_value"],
                "confidence": 0.91,
                "uncertainty": "The fixture establishes bounded values, not their broader causal explanation.",
                "materiality_rule_id": "value_materiality",
            },
            {
                "item_id": "explicit_status_disagreement",
                "item_kind": "disagreement",
                "title": "Authorized sources disagree on status",
                "summary": "One source reports ready while the other reports paused for the same subject.",
                "why_it_matters": "A reviewer should see the conflict before relying on either status.",
                "epistemic_classification": "disagreement",
                "statement_ids": ["status_disagreement"],
                "citation_ids": ["source_alpha_status", "source_beta_status"],
                "confidence": 0.88,
                "uncertainty": "The evidence does not establish which source is current or authoritative.",
            },
            {
                "item_id": "relationship_unknown",
                "item_kind": "unknown",
                "title": "Relationship semantics remain unknown",
                "summary": "The admitted observations do not establish how records relate.",
                "why_it_matters": "Relationship monitoring should remain provisional until supported evidence arrives.",
                "epistemic_classification": "unknown",
                "statement_ids": ["relationship_unknown"],
                "citation_ids": ["source_alpha_status"],
                "confidence": 0.55,
                "uncertainty": "No authorized relationship evidence is present in the bounded fixture.",
            },
        ],
        "freshness_statement": "Evidence current through the admitted observations.",
    }


async def _mapped() -> OntologyAgentReferenceResult:
    return await exercise_ontology_agent_restart()


NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_concept_strategy_satisfies_ontology_agent_exact_proposal() -> None:
    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-concept-model",))
    provider = _SpyProvider(_concept_response)
    agent = OntologyAgent(
        sessions=sessions, authority=authority, strategy=SelectedConceptModelStrategy(provider=provider)
    )
    outcome = await agent.propose(
        connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent="Understand the status and value of approved source-grounded records.",
        actor_ref="agent:ontology",
        occurred_at=NOW,
    )
    assert outcome.proposed
    assert outcome.proposal is not None
    assert provider.calls == 1
    assert len(outcome.proposal.proposal.entity_types) == 1


@pytest.mark.asyncio
async def test_intelligence_strategy_satisfies_intelligence_agent_exact_proposal() -> None:
    mapped = await _mapped()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-intelligence-model",))
    provider = _SpyProvider(_intelligence_response)
    agent = IntelligenceAgent(
        sessions=sessions,
        authority=authority,
        strategy=SelectedIntelligenceModelStrategy(provider=provider),
    )
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    await agent.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    outcome = await agent.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material status and value changes for approved source-grounded records.",
        audience_constraints=("Review material changes without executing decisions.",),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert outcome.proposed
    assert outcome.proposal is not None
    assert provider.calls == 1
    statements = {item.statement_id: item.classification for item in outcome.proposal.proposal.epistemic_statements}
    assert set(EpistemicClassification) == set(statements.values())


@pytest.mark.asyncio
async def test_briefing_strategy_satisfies_briefing_agent_exact_first_brief() -> None:
    mapped = await _mapped()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-intelligence-model",))
    intelligence = IntelligenceAgent(
        sessions=sessions,
        authority=authority,
        strategy=FixtureIntelligenceModelStrategy(),
    )
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    proposed = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material status and value changes for approved source-grounded records.",
        audience_constraints=("Review material changes without executing decisions.",),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert proposed.proposal is not None
    approved = await intelligence.approve(
        proposed.proposal.session.revision,
        proposal=proposed.proposal.proposal,
        approval_receipt_ref="approval:fixture-intelligence-model",
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at,
    )
    provider = _SpyProvider(_brief_response)
    briefing_agent = BriefingAgent(sessions=sessions, strategy=SelectedBriefingStrategy(provider=provider))
    outcome = await briefing_agent.create_first_brief(
        approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=admitted_at,
    )
    assert outcome.ready
    assert outcome.briefing is not None
    assert provider.calls == 1
    kinds = {item.item_kind for item in outcome.briefing.brief.items}
    assert BriefingItemKind.DISAGREEMENT in kinds
    assert BriefingItemKind.UNKNOWN in kinds


@pytest.mark.asyncio
async def test_one_shared_provider_drives_all_three_strategy_ports() -> None:
    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        stage = parsed["stage"]
        if stage == "concept_model_proposal":
            return _concept_response(parsed)
        if stage == "intelligence_model_proposal":
            return _intelligence_response(parsed)
        if stage == "first_briefing_preview":
            return _brief_response(parsed)
        raise AssertionError(f"unexpected stage {stage}")

    provider = _SpyProvider(respond)
    connected = await exercise_connection_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=connected.store)

    ontology = OntologyAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:concept",)),
        strategy=SelectedConceptModelStrategy(provider=provider),
    )
    mapped = await ontology.propose(
        connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent="Understand approved source-grounded records.",
        actor_ref="agent:ontology",
        occurred_at=NOW,
    )
    assert mapped.proposal is not None
    concept_approved = await ontology.approve(
        mapped.proposal.session.revision,
        proposal=mapped.proposal.proposal,
        approval_receipt_ref="approval:concept",
        actor_ref="principal:fixture-builder",
        occurred_at=NOW,
    )

    intelligence = IntelligenceAgent(
        sessions=sessions,
        authority=FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:intelligence",)),
        strategy=SelectedIntelligenceModelStrategy(provider=provider),
    )

    class _MappedShim:
        approved = concept_approved
        restarted_proposal = concept_approved.proposal
        restarted_disposition = concept_approved.disposition
        source_profile = connected.restarted_profile

    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(_MappedShim(), admitted_at=admitted_at)
    await intelligence.admit_observations(
        concept_approved.session.revision,
        concept_model=concept_approved.proposal,
        concept_disposition=concept_approved.disposition,
        source_profile=connected.restarted_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    watched = await intelligence.propose(
        concept_approved.session.revision,
        concept_model=concept_approved.proposal,
        concept_disposition=concept_approved.disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=("Review material changes.",),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert watched.proposal is not None
    intelligence_approved = await intelligence.approve(
        watched.proposal.session.revision,
        proposal=watched.proposal.proposal,
        approval_receipt_ref="approval:intelligence",
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at,
    )

    briefing_agent = BriefingAgent(sessions=sessions, strategy=SelectedBriefingStrategy(provider=provider))
    brief_outcome = await briefing_agent.create_first_brief(
        intelligence_approved.session.revision,
        concept_model=concept_approved.proposal,
        concept_disposition=concept_approved.disposition,
        intelligence_model=intelligence_approved.proposal,
        intelligence_disposition=intelligence_approved.disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=admitted_at,
    )
    assert brief_outcome.ready
    assert provider.calls == 3
    restarted = IntelligenceBuilderSessionService(store=connected.store)
    reopened = await restarted.load_latest(
        product_id=brief_outcome.briefing.session.revision.product_id,
        session_id=brief_outcome.briefing.session.revision.session_id,
        available_at=admitted_at,
    )
    assert reopened is not None
    assert reopened.stage is OnboardingStage.FIRST_BRIEFING_READY
    assert any(item.artifact_kind is OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW for item in reopened.artifacts)


@pytest.mark.asyncio
async def test_concept_strategy_rejects_protected_key_in_provider_output() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        material["session_id"] = "session:forged"
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="unsupported fields"):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_strategy_rejects_extra_key_inside_entity_type() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        material["entity_types"][0]["fabricated_field"] = True
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_strategy_rejects_wrong_citation_selection() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        material["citations"][0]["source_sample_id"] = "source_sample:does-not-exist"
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="unknown source sample"):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_strategy_rejects_wrong_field_path_selection() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        material["citations"][0]["field_path"] = "/does-not-exist"
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="unknown source-sample field"):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_strategy_rejects_duplicate_citation_selection() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        material["citations"].append(dict(material["citations"][0]))
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="duplicate citation selection"):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_strategy_rejects_unused_citation_selection() -> None:
    connected = await exercise_connection_agent_restart()

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _concept_response(parsed)
        sample = parsed["trusted_context"]["source_profile"]["samples"][0]
        material["citations"].append(
            {"citation_id": "unused_citation", "source_sample_id": sample["sample_id"], "field_path": "/status"}
        )
        return material

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_intelligence_strategy_rejects_unsupported_watch_target_member() -> None:
    mapped = await _mapped()
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _intelligence_response(parsed)
        material["watch_targets"][0]["member_id"] = "undeclared_attribute"
        return material

    strategy = SelectedIntelligenceModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="undeclared entity attribute"):
        await strategy.propose(
            session=mapped.approved.session.revision,
            concept_model=mapped.restarted_proposal,
            concept_disposition=mapped.restarted_disposition,
            observations=evidence,
            user_intent="Watch material changes.",
            audience_constraints=(),
            cadence_constraints=(),
            created_at=admitted_at,
        )


@pytest.mark.asyncio
async def test_intelligence_strategy_rejects_wrong_observation_field() -> None:
    mapped = await _mapped()
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _intelligence_response(parsed)
        material["citations"][0]["field_path"] = "/does-not-exist"
        return material

    strategy = SelectedIntelligenceModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="unknown observation field"):
        await strategy.propose(
            session=mapped.approved.session.revision,
            concept_model=mapped.restarted_proposal,
            concept_disposition=mapped.restarted_disposition,
            observations=evidence,
            user_intent="Watch material changes.",
            audience_constraints=(),
            cadence_constraints=(),
            created_at=admitted_at,
        )


@pytest.mark.asyncio
async def test_briefing_strategy_rejects_invalid_statement_binding() -> None:
    mapped = await _mapped()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-intelligence-model",))
    intelligence = IntelligenceAgent(
        sessions=sessions, authority=authority, strategy=FixtureIntelligenceModelStrategy()
    )
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    proposed = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=(),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert proposed.proposal is not None
    approved = await intelligence.approve(
        proposed.proposal.session.revision,
        proposal=proposed.proposal.proposal,
        approval_receipt_ref="approval:fixture-intelligence-model",
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at,
    )

    def respond(parsed: dict[str, Any]) -> dict[str, Any]:
        material = _brief_response(parsed)
        material["items"][0]["statement_ids"] = ["undeclared_statement"]
        return material

    strategy = SelectedBriefingStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyConflict, match="undeclared epistemic statement"):
        await strategy.synthesize(
            session=approved.session.revision,
            concept_model=mapped.restarted_proposal,
            concept_disposition=mapped.restarted_disposition,
            intelligence_model=approved.proposal,
            intelligence_disposition=approved.disposition,
            observations=evidence,
            generated_at=admitted_at,
        )


@pytest.mark.asyncio
async def test_briefing_strategy_no_material_shifts_returns_none() -> None:
    mapped = await _mapped()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-intelligence-model",))
    intelligence = IntelligenceAgent(
        sessions=sessions, authority=authority, strategy=FixtureIntelligenceModelStrategy()
    )
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    proposed = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=(),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert proposed.proposal is not None
    approved = await intelligence.approve(
        proposed.proposal.session.revision,
        proposal=proposed.proposal.proposal,
        approval_receipt_ref="approval:fixture-intelligence-model",
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at,
    )
    provider = _SpyProvider(lambda _parsed: {"no_material_shifts": True})
    strategy = SelectedBriefingStrategy(provider=provider)
    result = await strategy.synthesize(
        session=approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        generated_at=admitted_at,
    )
    assert result is None


@pytest.mark.asyncio
async def test_provider_exception_becomes_unavailable_and_is_sanitized() -> None:
    connected = await exercise_connection_agent_restart()
    strategy = SelectedConceptModelStrategy(provider=_RaisingProvider())
    with pytest.raises(SelectedBuilderStrategyUnavailable) as exc:
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )
    assert "secret transport detail" not in str(exc.value)


@pytest.mark.asyncio
async def test_provider_non_object_output_fails_closed_as_unavailable() -> None:
    connected = await exercise_connection_agent_restart()
    provider = _SpyProvider(lambda _parsed: [])  # type: ignore[arg-type, return-value]

    async def complete_json(prompt: str, *, model: str | None, max_tokens: int):
        return []

    provider.complete_json = complete_json  # type: ignore[method-assign]
    strategy = SelectedConceptModelStrategy(provider=provider)
    with pytest.raises(SelectedBuilderStrategyUnavailable):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_concept_prompt_is_deterministic_and_carries_no_credentials() -> None:
    connected = await exercise_connection_agent_restart()
    provider = _SpyProvider(_concept_response)
    strategy = SelectedConceptModelStrategy(provider=provider)
    await strategy.propose(
        session=connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent="Understand records.",
        organization_terminology=(),
        created_at=NOW,
    )
    await strategy.propose(
        session=connected.restarted_session,
        source_profile=connected.restarted_profile,
        user_intent="Understand records.",
        organization_terminology=(),
        created_at=NOW + timedelta(days=1),
    )
    assert len(provider.prompts) == 2
    assert provider.prompts[0] == provider.prompts[1]
    parsed = json.loads(provider.prompts[0])
    assert parsed["stage"] == "concept_model_proposal"
    assert set(parsed) == {"attribution_rules", "output_contract", "stage", "trusted_context"}
    lowered = provider.prompts[0].lower()
    for forbidden in ("password", "api_key", "connector_secret", "bearer ", "authorization:"):
        assert forbidden not in lowered
    assert "see contract" not in lowered
    contract = parsed["output_contract"]
    assert contract["type"] == "object"
    assert contract["additionalProperties"] is False
    assert set(contract["required"]) == {"citations", "entity_types", "exclusions", "confidence"}
    entity_type_schema = contract["properties"]["entity_types"]["items"]
    assert entity_type_schema["additionalProperties"] is False
    assert "attributes" in entity_type_schema["properties"]
    attribute_schema = entity_type_schema["properties"]["attributes"]["items"]
    assert attribute_schema["additionalProperties"] is False
    assert set(attribute_schema["required"]) >= {"attribute_id", "value_kind", "citation_ids", "confidence"}
    for protected in ("session_id", "correlation_id", "proposal_id", "proposal_digest", "revision"):
        assert protected not in contract["properties"]


def _walk_schema_strings(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_walk_schema_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_schema_strings(item))
    elif isinstance(node, str):
        found.append(node)
    return found


@pytest.mark.asyncio
async def test_intelligence_prompt_schema_has_no_placeholders_and_hides_protected_bindings() -> None:
    mapped = await _mapped()
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    provider = _SpyProvider(_intelligence_response)
    strategy = SelectedIntelligenceModelStrategy(provider=provider)
    await strategy.propose(
        session=mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=(),
        cadence_constraints=(),
        created_at=admitted_at,
    )
    parsed = json.loads(provider.prompts[0])
    contract = parsed["output_contract"]
    for value in _walk_schema_strings(contract):
        assert "see contract" not in value.lower()
    assert contract["additionalProperties"] is False
    watch_target_schema = contract["properties"]["watch_targets"]["items"]
    assert watch_target_schema["additionalProperties"] is False
    assert set(watch_target_schema["required"]) == {
        "target_id",
        "target_kind",
        "entity_type_id",
        "member_id",
        "citation_ids",
    }
    for protected in ("session_id", "concept_model_proposal_id", "observation_set_digest"):
        assert protected not in contract["properties"]


@pytest.mark.asyncio
async def test_briefing_prompt_schema_expresses_no_material_shifts_as_one_of() -> None:
    mapped = await _mapped()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=("approval:fixture-intelligence-model",))
    intelligence = IntelligenceAgent(
        sessions=sessions, authority=authority, strategy=FixtureIntelligenceModelStrategy()
    )
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    proposed = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=(),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at,
    )
    assert proposed.proposal is not None
    approved = await intelligence.approve(
        proposed.proposal.session.revision,
        proposal=proposed.proposal.proposal,
        approval_receipt_ref="approval:fixture-intelligence-model",
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at,
    )
    provider = _SpyProvider(_brief_response)
    strategy = SelectedBriefingStrategy(provider=provider)
    await strategy.synthesize(
        session=approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        generated_at=admitted_at,
    )
    parsed = json.loads(provider.prompts[0])
    contract = parsed["output_contract"]
    assert "oneOf" in contract
    variants = contract["oneOf"]
    assert len(variants) == 2
    material_variant = next(v for v in variants if "items" in v["properties"])
    shift_free_variant = next(v for v in variants if v is not material_variant)
    assert material_variant["additionalProperties"] is False
    assert set(material_variant["required"]) == {"title", "executive_summary", "items", "freshness_statement"}
    assert shift_free_variant["properties"]["no_material_shifts"] == {"const": True}
    item_schema = material_variant["properties"]["items"]["items"]
    assert item_schema["additionalProperties"] is False
    assert "statement_ids" in item_schema["required"]
    for value in _walk_schema_strings(contract):
        assert "see contract" not in value.lower()


@pytest.mark.asyncio
async def test_over_bound_prompt_fails_closed_without_calling_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.engine.core.intelligence_builder_strategies as strategies_module

    monkeypatch.setattr(strategies_module, "_MAX_PROMPT_BYTES", 16)
    connected = await exercise_connection_agent_restart()

    def respond(_parsed: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("the selected provider must not be called once the prompt exceeds the bound")

    strategy = SelectedConceptModelStrategy(provider=_SpyProvider(respond))
    with pytest.raises(SelectedBuilderStrategyUnavailable, match="exceeded the bounded safe size"):
        await strategy.propose(
            session=connected.restarted_session,
            source_profile=connected.restarted_profile,
            user_intent="Understand records.",
            organization_terminology=(),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_intelligence_prompt_carries_no_credentials() -> None:
    mapped = await _mapped()
    admitted_at = NOW + timedelta(minutes=1)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    provider = _SpyProvider(_intelligence_response)
    strategy = SelectedIntelligenceModelStrategy(provider=provider)
    await strategy.propose(
        session=mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material changes.",
        audience_constraints=(),
        cadence_constraints=(),
        created_at=admitted_at,
    )
    lowered = provider.prompts[0].lower()
    for forbidden in ("password", "api_key", "connector_secret", "bearer ", "authorization:"):
        assert forbidden not in lowered
