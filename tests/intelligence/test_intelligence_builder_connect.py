from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.intelligence_builder import (
    ConnectionAgent,
    ConnectionAgentStaleProposal,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionReplayConflict,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    ConnectionEffect,
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceSampleV1,
    SourceScopeProposalV1,
    SourceScopeSelectionV1,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from ace.testing.intelligence_builder import (
    FixtureCoreAuthorityResolver,
    FixtureRegisteredSourceOptionProvider,
    exercise_connection_agent_restart,
    provider_free_source_catalog,
)

pytestmark = pytest.mark.unit

_START = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
_APPROVAL = "approval:fixture-source-scope"


async def _connection_setup(*, approved: bool = True, provider=None):
    store = InMemoryImmutableRecordStore()
    catalog, profiles = provider_free_source_catalog()
    exact_provider = provider or FixtureRegisteredSourceOptionProvider(
        catalog=catalog,
        profiles=profiles,
    )
    authority = FixtureCoreAuthorityResolver(
        approved_receipt_refs=(_APPROVAL,) if approved else (),
    )
    sessions = IntelligenceBuilderSessionService(store=store)
    agent = ConnectionAgent(sessions=sessions, authority=authority, provider=exact_provider)
    started = await sessions.start(
        product_id="product:intelligence-builder-test",
        correlation_id="correlation:connect-test",
        goal_ref="goal:bounded-orientation",
        actor_ref="principal:builder",
        occurred_at=_START,
    )
    discovered = await agent.discover()
    selections = tuple(
        SourceScopeSelectionV1(
            option_id=option.option_id,
            permissions=("read_records",),
            scopes=("field_shape",),
            effects=(ConnectionEffect.CONNECTION_TEST, ConnectionEffect.BOUNDED_SAMPLE),
            sample_records=2,
        )
        for option in discovered.options
    )
    scope = await agent.propose_scope(
        started.revision,
        catalog=discovered,
        selections=selections,
        actor_ref="agent:connection",
        occurred_at=_START + timedelta(seconds=1),
    )
    return store, sessions, agent, exact_provider, discovered, scope


@pytest.mark.asyncio
async def test_provider_free_connect_reproduces_two_sources_and_restart_identity():
    first = await exercise_connection_agent_restart()
    second = await exercise_connection_agent_restart()

    assert first.outcome.connected is True
    assert first.outcome.session.revision.stage is OnboardingStage.SOURCES_READY
    assert len(first.outcome.profile.samples) == 2
    assert first.provider.sample_calls == 1
    assert first.restarted_session == first.outcome.session.revision
    assert first.restarted_scope == first.scope.proposal
    assert first.restarted_profile == first.outcome.profile
    assert first.scope.proposal_admission.artifact_id == first.scope.proposal.proposal_id
    assert first.outcome.profile_admission.artifact_id == first.outcome.profile.proposal_id
    assert first.scope.proposal.proposal_id == second.scope.proposal.proposal_id
    assert first.outcome.profile.proposal_id == second.outcome.profile.proposal_id
    assert first.outcome.session.revision.revision_id == second.outcome.session.revision.revision_id


@pytest.mark.asyncio
async def test_denied_access_performs_no_connector_effect_and_resumes_after_restart():
    store, _, agent, provider, _, scope = await _connection_setup(approved=False)

    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=_APPROVAL,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=2),
    )

    assert outcome.connected is False
    assert outcome.blocked_reason is OnboardingBlockReason.INSUFFICIENT_PERMISSION
    assert provider.sample_calls == 0
    restarted = IntelligenceBuilderSessionService(store=store)
    loaded = await restarted.load_latest(
        product_id=outcome.session.revision.product_id,
        session_id=outcome.session.revision.session_id,
        available_at=_START + timedelta(seconds=3),
    )
    assert loaded == outcome.session.revision
    retrying = await restarted.retry(
        loaded,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=3),
    )
    resumed = await restarted.resume(
        retrying.revision,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=4),
    )
    assert resumed.revision.stage is OnboardingStage.SOURCES_CONNECTING
    assert resumed.revision.session_id == outcome.session.revision.session_id
    assert resumed.revision.correlation_id == outcome.session.revision.correlation_id


@pytest.mark.asyncio
async def test_stale_scope_proposal_is_refused_before_authority_or_connector_use():
    _, _, agent, provider, catalog, first = await _connection_setup()
    revised = await agent.propose_scope(
        first.session.revision,
        catalog=catalog,
        selections=first.proposal.selections,
        actor_ref="agent:connection",
        occurred_at=_START + timedelta(seconds=2),
    )

    with pytest.raises(ConnectionAgentStaleProposal, match="not the current session handoff"):
        await agent.connect(
            revised.session.revision,
            proposal=first.proposal,
            approval_receipt_ref=_APPROVAL,
            actor_ref="principal:builder",
            occurred_at=_START + timedelta(seconds=3),
        )

    assert provider.sample_calls == 0


class _ScopeWideningProvider(FixtureRegisteredSourceOptionProvider):
    async def test_and_sample(self, proposal):
        samples = await super().test_and_sample(proposal)
        first = samples[0]
        widened = SourceSampleV1(
            **first.model_dump(
                mode="python",
                exclude={"sample_id", "sample_digest", "scopes"},
            ),
            scopes=("field_shape", "recent_records"),
        )
        return (widened, *samples[1:])


class _SourceIdentityWideningProvider(FixtureRegisteredSourceOptionProvider):
    async def test_and_sample(self, proposal):
        samples = await super().test_and_sample(proposal)
        first = samples[0]
        widened = SourceSampleV1(
            **first.model_dump(
                mode="python",
                exclude={"sample_id", "sample_digest", "source_ref"},
            ),
            source_ref="source:unapproved-neighbor",
        )
        return (widened, *samples[1:])


@pytest.mark.asyncio
async def test_connector_scope_widening_is_blocked_and_never_becomes_ready():
    catalog, profiles = provider_free_source_catalog()
    provider = _ScopeWideningProvider(catalog=catalog, profiles=profiles)
    _, _, agent, _, _, scope = await _connection_setup(provider=provider)

    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=_APPROVAL,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=2),
    )

    assert provider.sample_calls == 1
    assert outcome.connected is False
    assert outcome.blocked_reason is OnboardingBlockReason.INSUFFICIENT_PERMISSION
    assert outcome.session.revision.stage is OnboardingStage.BLOCKED


@pytest.mark.asyncio
async def test_connector_cannot_substitute_an_unapproved_source_identity():
    catalog, profiles = provider_free_source_catalog()
    provider = _SourceIdentityWideningProvider(catalog=catalog, profiles=profiles)
    _, _, agent, _, _, scope = await _connection_setup(provider=provider)

    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=_APPROVAL,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=2),
    )

    assert provider.sample_calls == 1
    assert outcome.connected is False
    assert outcome.blocked_reason is OnboardingBlockReason.INSUFFICIENT_PERMISSION


@pytest.mark.asyncio
async def test_connector_failure_is_durable_and_retryable():
    catalog, profiles = provider_free_source_catalog()
    provider = FixtureRegisteredSourceOptionProvider(catalog=catalog, profiles=profiles, fail=True)
    _, _, agent, _, _, scope = await _connection_setup(provider=provider)

    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=_APPROVAL,
        actor_ref="principal:builder",
        occurred_at=_START + timedelta(seconds=2),
    )

    assert provider.sample_calls == 1
    assert outcome.blocked_reason is OnboardingBlockReason.FAILED_CONNECTOR
    assert outcome.session.revision.resume_stage is OnboardingStage.SOURCES_CONNECTING


@pytest.mark.asyncio
async def test_agent_cannot_self_dispose_the_sources_ready_transition():
    _, sessions, _, _, _, scope = await _connection_setup()

    with pytest.raises(IntelligenceBuilderSessionError, match="requires a different boundary"):
        await sessions.advance(
            scope.session.revision,
            stage=OnboardingStage.SOURCES_READY,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref="agent:connection",
            occurred_at=_START + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_stale_session_revision_cannot_fork_the_durable_chain():
    _, sessions, _, _, _, scope = await _connection_setup()
    blocked = await sessions.block(
        scope.session.revision,
        reason=OnboardingBlockReason.FAILED_CONNECTOR,
        actor_ref="agent:connection",
        safe_diagnostic="registered connector failed",
        occurred_at=_START + timedelta(seconds=2),
    )
    assert blocked.revision.stage is OnboardingStage.BLOCKED

    with pytest.raises(IntelligenceBuilderSessionReplayConflict, match="stale session revision"):
        await sessions.block(
            scope.session.revision,
            reason=OnboardingBlockReason.FAILED_CONNECTOR,
            actor_ref="agent:connection",
            safe_diagnostic="second fork attempt",
            occurred_at=_START + timedelta(seconds=3),
        )


def test_public_contracts_reject_forbidden_effects_credentials_and_imperative_flags():
    with pytest.raises(ValidationError):
        SourceScopeSelectionV1.model_validate(
            {
                "option_id": "source_alpha",
                "permissions": ("read_records",),
                "scopes": ("field_shape",),
                "effects": ("schedule",),
                "sample_records": 1,
            }
        )

    proposal = SourceScopeProposalV1(
        session_id="session:fixture",
        goal_ref="goal:fixture",
        catalog_id="catalog:fixture",
        catalog_digest="sha256:" + "a" * 64,
        selections=(
            SourceScopeSelectionV1(
                option_id="source_alpha",
                permissions=("read_records",),
                scopes=("field_shape",),
                effects=(ConnectionEffect.BOUNDED_SAMPLE,),
                sample_records=1,
            ),
        ),
        created_at=_START,
    )
    material = proposal.model_dump(mode="python")
    material["credentials"] = {"token": "forbidden"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceScopeProposalV1.model_validate(material)

    with pytest.raises(ValidationError):
        SourceSampleV1.model_validate(
            {
                "option_id": "source_alpha",
                "connector_ref": "connector:fixture-alpha",
                "connector_digest": "sha256:" + "b" * 64,
                "source_ref": "source:fixture-alpha",
                "scope_proposal_id": proposal.proposal_id,
                "scope_proposal_digest": proposal.proposal_digest,
                "permissions": ("read_records",),
                "scopes": ("field_shape",),
                "effects_performed": (ConnectionEffect.BOUNDED_SAMPLE,),
                "sample_records": 1,
                "fields": (),
                "evidence_digest": "sha256:" + "c" * 64,
                "observed_at": _START,
                "scheduled": True,
            }
        )


def test_public_contracts_publish_machine_readable_schema_without_credential_fields():
    schema = SourceScopeProposalV1.model_json_schema()

    assert schema["properties"]["contract"]["const"] == ("ace.application.source-scope-proposal/v1alpha1")
    assert "credentials" not in schema["properties"]
    selection = schema["$defs"]["SourceScopeSelectionV1"]
    effect_ref = selection["properties"]["effects"]["items"]["$ref"]
    effect_name = effect_ref.rsplit("/", maxsplit=1)[-1]
    assert schema["$defs"][effect_name]["enum"] == ["connection_test", "bounded_sample"]
