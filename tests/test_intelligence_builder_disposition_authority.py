"""Production-safe reviewed Builder disposition approval and resolver tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.intelligence_agent import IntelligenceAgent
from ace.application.intelligence_builder import ConnectionAgent, IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import (
    ConnectionEffect,
    OnboardingStage,
    SourceScopeSelectionV1,
)
from ace.application.ontology_agent import OntologyAgent
from ace.application.ontology_agent_contracts import OrganizationTerminologyV1
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1, immutable_record_storage_id
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from ace.testing.intelligence_builder import (
    FixtureRegisteredSourceOptionProvider,
    provider_free_source_catalog,
)
from ace.testing.ontology_agent import FixtureConceptModelStrategy
from ace.testing.watch_brief import FixtureIntelligenceModelStrategy, fixture_observations
from core.engine.core.intelligence_builder_disposition_authority import (
    _KIND_CONFIG,
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderDispositionApprovalConflict,
    BuilderDispositionApprovalDenied,
    BuilderDispositionApprovalUnavailable,
    BuilderDispositionKind,
    BuilderIntelligenceModelApproveRequestV1Alpha1,
    BuilderSourceScopeApproveRequestV1Alpha1,
    RecordedIntelligenceBuilderDispositionAuthority,
    approve_builder_concept_model,
    approve_builder_intelligence_model,
    approve_builder_source_scope,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID

pytestmark = pytest.mark.unit

_START = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):
        return "delegated-grant-result"


def _owner() -> dict:
    return {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["intelligence_build", "observe_read"],
        "local_owner": True,
    }


async def _scope_setup():
    store = InMemoryImmutableRecordStore()
    catalog, profiles = provider_free_source_catalog()
    provider = FixtureRegisteredSourceOptionProvider(catalog=catalog, profiles=profiles)
    resolver = RecordedIntelligenceBuilderDispositionAuthority(records=store, grants=_NoGrantAuthority())
    sessions = IntelligenceBuilderSessionService(store=store)
    agent = ConnectionAgent(sessions=sessions, authority=resolver, provider=provider)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id="correlation:disposition-test",
        goal_ref="goal:bounded-orientation",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=_START,
    )
    discovered = await agent.discover()
    selections = tuple(
        SourceScopeSelectionV1(
            option_id=option.option_id,
            permissions=("read_records",),
            scopes=("field_shape", "recent_records"),
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
        occurred_at=_START,
    )
    return store, resolver, sessions, agent, scope


@pytest.mark.asyncio
async def test_source_scope_disposition_round_trip_retries_idempotently_and_agent_connects():
    store, resolver, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)
    request = BuilderSourceScopeApproveRequestV1Alpha1(
        decision="approve",
        current=scope.session.revision,
        proposal=scope.proposal,
        approved_at=approved_at,
    )

    before = len(store.records)
    first = await approve_builder_source_scope(request=request, user=_owner(), records=store)
    after_first = len(store.records)
    replay = await approve_builder_source_scope(request=request, user=_owner(), records=store)

    assert first.model_dump(mode="json") == replay.model_dump(mode="json")
    assert first.approval.subject_ref == scope.proposal.proposal_id
    assert first.approval.receipt_ref.startswith("approval:builder-source-scope:")
    assert after_first == before + 1
    assert len(store.records) == after_first

    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=first.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=approved_at + timedelta(seconds=1),
    )
    assert outcome.connected is True
    assert outcome.session.revision.approval_receipt_ref == first.approval.receipt_ref


@pytest.mark.asyncio
async def test_source_scope_disposition_fails_closed_on_stale_session_crossed_proposal_and_different_material():
    store, _, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)

    revised = await agent.propose_scope(
        scope.session.revision,
        catalog=await agent.discover(),
        selections=scope.proposal.selections,
        actor_ref="agent:connection",
        occurred_at=approved_at,
    )

    with pytest.raises(BuilderDispositionApprovalConflict, match="stale"):
        await approve_builder_source_scope(
            request=BuilderSourceScopeApproveRequestV1Alpha1(
                decision="approve",
                current=scope.session.revision,
                proposal=scope.proposal,
                approved_at=approved_at,
            ),
            user=_owner(),
            records=store,
        )

    with pytest.raises(BuilderDispositionApprovalConflict, match="current session handoff"):
        await approve_builder_source_scope(
            request=BuilderSourceScopeApproveRequestV1Alpha1(
                decision="approve",
                current=revised.session.revision,
                proposal=scope.proposal,
                approved_at=approved_at,
            ),
            user=_owner(),
            records=store,
        )

    approved = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=revised.session.revision,
            proposal=revised.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        records=store,
    )

    other_owner = {**_owner(), "sub": "user:someone-else"}
    with pytest.raises(BuilderDispositionApprovalDenied):
        await approve_builder_source_scope(
            request=BuilderSourceScopeApproveRequestV1Alpha1(
                decision="approve",
                current=revised.session.revision,
                proposal=revised.proposal,
                approved_at=approved_at,
            ),
            user=other_owner,
            records=store,
        )
    assert approved.approval.subject_ref == revised.proposal.proposal_id


@pytest.mark.asyncio
async def test_resolver_fails_closed_on_missing_wrong_scope_future_and_unrecognized_receipt():
    store, resolver, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)
    approved = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=scope.session.revision,
            proposal=scope.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        records=store,
    )

    with pytest.raises(BuilderDispositionApprovalDenied, match="unrecognized"):
        await resolver.resolve_approval(
            receipt_ref="approval:builder-unknown-kind:deadbeef",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )

    with pytest.raises(BuilderDispositionApprovalDenied, match="not recorded"):
        await resolver.resolve_approval(
            receipt_ref="approval:builder-source-scope:not-recorded",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )

    with pytest.raises(BuilderDispositionApprovalDenied):
        await resolver.resolve_approval(
            receipt_ref=approved.approval.receipt_ref,
            product_id="product:some-other-product",
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )

    with pytest.raises(BuilderDispositionApprovalDenied, match="stale or mismatched"):
        await resolver.resolve_approval(
            receipt_ref=approved.approval.receipt_ref,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref="source_scope_proposal:some-other-proposal",
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )

    with pytest.raises(BuilderDispositionApprovalDenied, match="stale or mismatched"):
        await resolver.resolve_approval(
            receipt_ref=approved.approval.receipt_ref,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at - timedelta(seconds=1),
        )

    resolved = await resolver.resolve_grant(
        grant_ref="authority_grant:anything",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        authority="intelligence_build",
        effective_at=approved_at,
    )
    assert resolved == "delegated-grant-result"


@pytest.mark.asyncio
async def test_resolver_fails_closed_on_tampered_stored_payload():
    store, resolver, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)
    approved = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=scope.session.revision,
            proposal=scope.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        records=store,
    )
    config = _KIND_CONFIG[BuilderDispositionKind.SOURCE_SCOPE]
    storage_id = immutable_record_storage_id(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=config.record_space,
        record_kind=config.record_kind,
        record_key=approved.approval.receipt_ref,
    )
    stored = store.records[storage_id]
    tampered_payload = dict(stored.payload)
    tampered_payload["actor_ref"] = "user:tampered"
    store.records[storage_id] = stored.model_construct(
        **{**stored.model_dump(mode="python"), "payload": tampered_payload}
    )

    with pytest.raises(BuilderDispositionApprovalUnavailable):
        await resolver.resolve_approval(
            receipt_ref=approved.approval.receipt_ref,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_resolver_fails_closed_on_tampered_record_envelope_not_only_payload():
    store, resolver, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)
    approved = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=scope.session.revision,
            proposal=scope.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        records=store,
    )
    config = _KIND_CONFIG[BuilderDispositionKind.SOURCE_SCOPE]
    storage_id = immutable_record_storage_id(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=config.record_space,
        record_kind=config.record_kind,
        record_key=approved.approval.receipt_ref,
    )
    stored = store.records[storage_id]

    for field, value in (
        ("as_of", approved_at - timedelta(seconds=5)),
        ("available_at", approved_at + timedelta(seconds=5)),
    ):
        rehashed = ImmutableRecordV1(
            **{
                **stored.model_dump(mode="python", exclude={"storage_id", "material_hash"}),
                field: value,
            }
        )
        store.records[storage_id] = rehashed
        with pytest.raises(BuilderDispositionApprovalDenied, match="stale or mismatched"):
            await resolver.resolve_approval(
                receipt_ref=approved.approval.receipt_ref,
                product_id=LOCAL_OWNER_PRODUCT_ID,
                subject_ref=str(scope.proposal.proposal_id),
                actor_ref=LOCAL_OWNER_ACTOR_REF,
                effective_at=approved_at + timedelta(seconds=10),
            )
        store.records[storage_id] = stored

    # The envelope must also agree on its own recorded scope, not only the payload.
    store.records[storage_id] = stored.model_construct(
        **{**stored.model_dump(mode="python"), "record_kind": "some-other-kind"}
    )
    with pytest.raises(BuilderDispositionApprovalDenied, match="not recorded"):
        await resolver.resolve_approval(
            receipt_ref=approved.approval.receipt_ref,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(scope.proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_disposition_denies_retained_older_artifact_approved_at_a_later_stage():
    store, resolver, sessions, agent, scope = await _scope_setup()
    approved_at = _START + timedelta(seconds=1)
    approved = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=scope.session.revision,
            proposal=scope.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        records=store,
    )
    connected = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approved.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=approved_at + timedelta(seconds=1),
    )
    assert connected.connected is True

    # The source-scope artifact reference is still retained in the session's
    # artifact list after the session progressed past sources_connecting; it
    # must not be newly approvable there.
    with pytest.raises(BuilderDispositionApprovalConflict, match="exact stage"):
        await approve_builder_source_scope(
            request=BuilderSourceScopeApproveRequestV1Alpha1(
                decision="approve",
                current=connected.session.revision,
                proposal=scope.proposal,
                approved_at=approved_at + timedelta(seconds=2),
            ),
            user=_owner(),
            records=store,
        )


@pytest.mark.asyncio
async def test_disposition_fails_closed_when_storage_returns_a_mismatched_receipt():
    class _MisreportingReceiptStore(InMemoryImmutableRecordStore):
        async def append(self, request: AppendOnlyTransactionRequestV1):
            receipt = await super().append(request)
            return receipt.model_construct(
                **{**receipt.model_dump(mode="python"), "committed_at": receipt.committed_at + timedelta(seconds=99)}
            )

    catalog_store, _, _, _, proposed_scope = await _scope_setup()

    misreporting = _MisreportingReceiptStore()
    misreporting.records = dict(catalog_store.records)
    misreporting.receipts = dict(catalog_store.receipts)
    misreporting.governed_state_heads = catalog_store.governed_state_heads

    approved_at = _START + timedelta(seconds=1)
    with pytest.raises(BuilderDispositionApprovalUnavailable, match="does not match the exact append request"):
        await approve_builder_source_scope(
            request=BuilderSourceScopeApproveRequestV1Alpha1(
                decision="approve",
                current=proposed_scope.session.revision,
                proposal=proposed_scope.proposal,
                approved_at=approved_at,
            ),
            user=_owner(),
            records=misreporting,
        )


@pytest.mark.asyncio
async def test_concept_model_and_intelligence_model_dispositions_stay_separate_and_agents_consume_unchanged():
    store, resolver, sessions, agent, scope = await _scope_setup()
    connect_at = _START + timedelta(seconds=1)
    scope_approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve",
            current=scope.session.revision,
            proposal=scope.proposal,
            approved_at=connect_at,
        ),
        user=_owner(),
        records=store,
    )
    connected = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=scope_approval.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=connect_at,
    )
    assert connected.connected is True

    ontology_agent = OntologyAgent(
        sessions=sessions,
        authority=resolver,
        strategy=FixtureConceptModelStrategy(),
    )
    mapped_at = connect_at + timedelta(seconds=1)
    proposed = await ontology_agent.propose(
        connected.session.revision,
        source_profile=connected.profile,
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
    assert proposed.proposed is True and proposed.proposal is not None

    concept_current = proposed.proposal.session.revision
    concept_proposal = proposed.proposal.proposal
    concept_approved_at = mapped_at + timedelta(seconds=1)
    concept_approval = await approve_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve",
            current=concept_current,
            proposal=concept_proposal,
            approved_at=concept_approved_at,
        ),
        user=_owner(),
        records=store,
    )
    assert concept_approval.approval.receipt_ref.startswith("approval:builder-concept-model:")

    concept_approved = await ontology_agent.approve(
        concept_current,
        proposal=concept_proposal,
        approval_receipt_ref=concept_approval.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=concept_approved_at,
    )

    # A source-scope receipt cannot stand in for the concept-model subject it never approved.
    with pytest.raises(BuilderDispositionApprovalDenied):
        await resolver.resolve_approval(
            receipt_ref=scope_approval.approval.receipt_ref,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(concept_proposal.proposal_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=concept_approved_at,
        )

    intelligence_agent = IntelligenceAgent(
        sessions=sessions,
        authority=resolver,
        strategy=FixtureIntelligenceModelStrategy(),
    )
    watch_at = concept_approved_at + timedelta(seconds=1)

    # Build the observation set directly against the concept-model artifact this
    # session actually admitted, matching how the production Briefing Agent seam
    # is exercised in tests/intelligence/test_intelligence_agent_watch.py.
    class _Mapped:
        approved = concept_approved
        restarted_proposal = concept_proposal
        restarted_disposition = concept_approved.disposition
        source_profile = connected.profile

    observations = fixture_observations(_Mapped(), admitted_at=watch_at)
    await intelligence_agent.admit_observations(
        concept_approved.session.revision,
        concept_model=concept_proposal,
        concept_disposition=concept_approved.disposition,
        source_profile=connected.profile,
        observations=observations,
        occurred_at=watch_at,
    )
    intelligence_outcome = await intelligence_agent.propose(
        concept_approved.session.revision,
        concept_model=concept_proposal,
        concept_disposition=concept_approved.disposition,
        observations=observations,
        user_intent="Watch material changes in approved source-grounded records.",
        actor_ref="agent:intelligence",
        occurred_at=watch_at + timedelta(seconds=1),
    )
    assert intelligence_outcome.proposed is True and intelligence_outcome.proposal is not None
    intelligence_current = intelligence_outcome.proposal.session.revision
    intelligence_proposal = intelligence_outcome.proposal.proposal

    intelligence_approved_at = watch_at + timedelta(seconds=2)
    intelligence_approval = await approve_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve",
            current=intelligence_current,
            proposal=intelligence_proposal,
            approved_at=intelligence_approved_at,
        ),
        user=_owner(),
        records=store,
    )
    assert intelligence_approval.approval.receipt_ref.startswith("approval:builder-intelligence-model:")
    assert intelligence_approval.approval.receipt_ref != concept_approval.approval.receipt_ref

    intelligence_approved = await intelligence_agent.approve(
        intelligence_current,
        proposal=intelligence_proposal,
        approval_receipt_ref=intelligence_approval.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=intelligence_approved_at,
    )
    assert intelligence_approved.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
