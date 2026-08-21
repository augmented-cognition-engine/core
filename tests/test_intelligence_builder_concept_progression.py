"""Tests for the Builder-to-Ontology-Agent concept progression coordinator (PI13 addendum 9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest

from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingStage
from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingScope,
    authorize_local_source_connect,
    preview_local_source_connect,
)
from ace.application.ontology_agent_contracts import OrganizationTerminologyV1
from ace.core.contracts import canonical_hash
from ace.core.records import ImmutableRecordV1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.intelligence_builder_concept_progression import (
    ConceptModelProposeRequestV1Alpha1,
    IntelligenceBuilderConceptProgressionConflict,
    IntelligenceBuilderConceptProgressionDenied,
    IntelligenceBuilderConceptProgressionRuntime,
    _persist_proposal_intent,
    _proposal_intent_key,
    approve_intelligence_builder_concept_model,
    propose_intelligence_builder_concept_model,
)
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderSourceScopeApproveRequestV1Alpha1,
    approve_builder_source_scope,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    connect_local_source_connect_scope,
    propose_local_source_connect_scope,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):
        raise AssertionError("concept-model approval never resolves a grant through this delegate")


class JsonRoundTripImmutableRecordStore(InMemoryImmutableRecordStore):
    """Reserializes appended payloads to their real stored JSON shape (Surreal-compatible round trip)."""

    async def append(self, request):
        receipt = await super().append(request)
        self.records = {
            storage_id: ImmutableRecordV1.model_validate_json(record.model_dump_json())
            for storage_id, record in self.records.items()
        }
        return receipt


class _SpyProvider:
    """Deterministic in-test structured-completion double; counts every exact call."""

    def __init__(self, respond: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.respond = respond
        self.calls = 0
        self.prompts: list[str] = []

    async def complete_json(self, prompt: str, *, model: str | None, max_tokens: int) -> dict[str, Any]:
        self.prompts.append(prompt)
        self.calls += 1
        return self.respond(json.loads(prompt))


class _RaisingProvider:
    async def complete_json(self, prompt: str, *, model: str | None, max_tokens: int) -> dict[str, Any]:
        raise RuntimeError("secret transport detail")


def _concept_response(parsed: dict[str, Any]) -> dict[str, Any]:
    source_profile = parsed["trusted_context"]["source_profile"]
    citations: list[dict[str, str]] = []
    for index, sample in enumerate(source_profile["samples"]):
        field = sample["fields"][0]
        citations.append(
            {
                "citation_id": f"sample_{index}_{field['field_path'].removeprefix('/')}",
                "source_sample_id": sample["sample_id"],
                "field_path": field["field_path"],
            }
        )
    return {
        "citations": citations,
        "entity_types": [
            {
                "type_id": "record",
                "display_name": "Record",
                "definition": "A source-grounded item captured from an approved local source.",
                "aliases": [],
                "attributes": [],
                "citation_ids": [item["citation_id"] for item in citations],
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


def _low_confidence_response(parsed: dict[str, Any]) -> dict[str, Any]:
    material = _concept_response(parsed)
    material["confidence"] = 0.1
    return material


def _owner(**overrides) -> dict:
    values = {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["intelligence_build", "observe_read"],
        "local_owner": True,
    }
    values.update(overrides)
    return values


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "concept-progression-fixture"})
    return CompiledPackRefV1(
        pack_id="pack-a",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _scope(mapping_id: str = "mapping-a", include: tuple[str, ...] = ("notes/*.md",)) -> LocalSourceMappingScope:
    return LocalSourceMappingScope(
        mapping_id=mapping_id,
        source_definition_ref="source-def-a",
        source_type_ref="source_type:local_files",
        subject_binding_id="subject-a",
        entity_type_id="entity-a",
        include=include,
    )


def _preview_request(**overrides) -> LocalSourceConnectPreviewRequest:
    values = dict(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        pack=_pack(),
        profile_id="profile-a",
        profile_digest=f"sha256:{canonical_hash({'profile': 'a'})}",
        source_group_id="source-group-a",
        expected_contribution="A cited orientation over the exact authorized local scope.",
        authorized_root="/nonexistent/pi13-concept-progression/host-local-root",
        mapping_scopes=(_scope(),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewRequest(**values)


def _authorization_request(**preview_overrides) -> LocalSourceConnectAuthorizationRequest:
    preview = preview_local_source_connect(_preview_request(**preview_overrides))
    return LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=_AUTHORIZED_AT)


def _acquired_markdown_file(relative_path: str, payload: str = '{"text":"hello"}', **overrides) -> AcquiredLocalFile:
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(payload),
        status="acquired",
        structured_payload_json=payload,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


class _SnapshotProvider:
    def __init__(self, files: tuple[AcquiredLocalFile, ...]) -> None:
        from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

        self.artifact_identity = CapabilityArtifactIdentityV1Alpha1(
            capability="source_snapshot",
            contract="ace.source.snapshot/v1alpha1",
            implementation_id="spy-provider",
            implementation_version="1.0.0",
            artifact_digest=f"sha256:{canonical_hash({'provider': 'spy'})}",
        )
        self.files = files

    async def snapshot(self, request):
        return self.files


async def _build_result(request, files):
    return await authorize_local_source_connect(request, _SnapshotProvider(files))


async def _sources_ready_chain(store):
    """Build a real SOURCES_READY session by driving the existing local-source-connect
    progression coordinator and the separate existing source-scope approval step."""

    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)

    sessions = IntelligenceBuilderSessionService(store=store)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id="correlation:concept-progression",
        goal_ref="goal:bounded-orientation",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=_AUTHORIZED_AT,
    )
    connect_runtime = LocalSourceConnectScopeProgressionRuntime(
        records=store,
        repository=repository,
        grants=_NoGrantAuthority(),
    )
    scope = await propose_local_source_connect_scope(
        request=request,
        result=result,
        session=started.revision,
        user=_owner(),
        runtime=connect_runtime,
        occurred_at=_AUTHORIZED_AT,
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    connected_at = approved_at + timedelta(seconds=1)
    outcome = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=connect_runtime,
        occurred_at=connected_at,
    )
    assert outcome.connected is True
    assert outcome.session.revision.stage is OnboardingStage.SOURCES_READY
    return outcome.session.revision, outcome.profile, connected_at


def _runtime(store, provider) -> IntelligenceBuilderConceptProgressionRuntime:
    return IntelligenceBuilderConceptProgressionRuntime(records=store, grants=_NoGrantAuthority(), provider=provider)


def _propose_request(session, profile, *, proposed_at, provider_respond=_concept_response, **overrides):
    values = dict(
        current=session,
        source_profile=profile,
        user_intent="Understand the status and value of approved source-grounded records.",
        organization_terminology=(
            OrganizationTerminologyV1(
                term_id="record",
                preferred_term="Record",
                definition="A bounded source-grounded item.",
                synonyms=("item",),
            ),
        ),
        proposed_at=proposed_at,
    )
    values.update(overrides)
    return ConceptModelProposeRequestV1Alpha1(**values), provider_respond


# --- propose_intelligence_builder_concept_model ---


async def test_propose_produces_concept_model_via_selected_provider():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)

    result = await propose_intelligence_builder_concept_model(
        request=request, user=_owner(), runtime=_runtime(store, provider)
    )

    assert provider.calls == 1
    assert result.session.revision.stage is OnboardingStage.CONCEPT_MODEL_PROPOSED
    assert len(result.proposal.entity_types) == 1


async def test_propose_calls_the_provider_exactly_once():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)

    await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=_runtime(store, provider))

    assert provider.calls == 1


async def test_propose_is_idempotent_on_retry_without_another_provider_call():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    runtime = _runtime(store, provider)

    first = await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)
    second = await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_propose_retry_fails_closed_on_changed_time():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    runtime = _runtime(store, provider)

    await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)

    changed = ConceptModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "proposed_at": proposed_at + timedelta(seconds=1)}
    )
    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await propose_intelligence_builder_concept_model(request=changed, user=_owner(), runtime=runtime)


async def test_propose_retry_fails_closed_on_changed_material():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    runtime = _runtime(store, provider)

    await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)

    changed = ConceptModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "user_intent": "A materially different exact user intent."}
    )
    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await propose_intelligence_builder_concept_model(request=changed, user=_owner(), runtime=runtime)


async def test_propose_fails_closed_on_advanced_session_chain():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    runtime = _runtime(store, provider)

    proposed = await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)
    approved_at = proposed_at + timedelta(seconds=1)
    await approve_intelligence_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve",
            current=proposed.session.revision,
            proposal=proposed.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        runtime=runtime,
    )

    # Retried "as of" a time after the real approval must observe the advanced
    # chain and fail closed rather than reopening the stale proposed material.
    raced = ConceptModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "proposed_at": approved_at + timedelta(seconds=1)}
    )
    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await propose_intelligence_builder_concept_model(request=raced, user=_owner(), runtime=runtime)


async def test_propose_fails_closed_on_wrong_owner():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)

    with pytest.raises(IntelligenceBuilderConceptProgressionDenied):
        await propose_intelligence_builder_concept_model(
            request=request, user=_owner(sub="user:someone-else"), runtime=_runtime(store, provider)
        )


async def test_propose_fails_closed_on_low_confidence_without_creating_a_proposed_session():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_low_confidence_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)

    with pytest.raises(IntelligenceBuilderConceptProgressionDenied):
        await propose_intelligence_builder_concept_model(
            request=request, user=_owner(), runtime=_runtime(store, provider)
        )

    sessions = IntelligenceBuilderSessionService(store=store)
    latest = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=session.session_id, available_at=proposed_at
    )
    assert latest is not None
    assert latest.stage is not OnboardingStage.CONCEPT_MODEL_PROPOSED


async def test_proposal_intent_admits_only_one_of_two_different_requests_for_same_prior_revision():
    """The exclusive intent key is derived only from (product_id, session_id,
    prior_revision_id, prior_revision_digest) -- never request content -- so
    it acts as a lock: a genuinely different request against the same prior
    revision must collide on the intent record itself, before any provider
    call happens."""

    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    request_a, _ = _propose_request(session, profile, proposed_at=proposed_at)
    request_b, _ = _propose_request(
        session,
        profile,
        proposed_at=proposed_at + timedelta(seconds=2),
        user_intent="A materially different exact user intent for this same prior revision.",
    )
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=session)

    await _persist_proposal_intent(
        records=store, intent_key=key, product_id=LOCAL_OWNER_PRODUCT_ID, session=session, request=request_a
    )
    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await _persist_proposal_intent(
            records=store, intent_key=key, product_id=LOCAL_OWNER_PRODUCT_ID, session=session, request=request_b
        )


async def test_proposal_intent_is_benign_on_identical_concurrent_resubmission():
    """Two concurrent submissions of the exact same request must not error on
    content mismatch: the second resolves to the same already-admitted
    intent instead of raising."""

    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=session)

    first = await _persist_proposal_intent(
        records=store, intent_key=key, product_id=LOCAL_OWNER_PRODUCT_ID, session=session, request=request
    )
    second = await _persist_proposal_intent(
        records=store, intent_key=key, product_id=LOCAL_OWNER_PRODUCT_ID, session=session, request=request
    )
    assert first == second


async def test_propose_two_different_requests_for_same_prior_revision_only_one_calls_provider():
    """End-to-end: two different exact requests against the same prior
    SOURCES_READY revision must not both durably win. Only the first calls
    the selected provider; the second fails closed."""

    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    runtime = _runtime(store, provider)
    request_a, _ = _propose_request(session, profile, proposed_at=proposed_at)
    request_b, _ = _propose_request(
        session,
        profile,
        proposed_at=proposed_at,
        user_intent="A materially different exact user intent for this same prior revision.",
    )

    await propose_intelligence_builder_concept_model(request=request_a, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await propose_intelligence_builder_concept_model(request=request_b, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_recovers_from_crash_after_agent_success_without_another_provider_call(monkeypatch):
    """A crash after the Ontology Agent's durable transition succeeds but
    before this coordinator returns must be recoverable on retry, without
    ever calling the selected provider again."""

    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(_concept_response)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    runtime = _runtime(store, provider)

    from ace.application.ontology_agent import OntologyAgent

    original_propose = OntologyAgent.propose

    async def crashing_propose(self, *args, **kwargs):
        outcome = await original_propose(self, *args, **kwargs)
        raise RuntimeError("simulated crash after the durable agent transition already succeeded")

    monkeypatch.setattr(OntologyAgent, "propose", crashing_propose)
    with pytest.raises(RuntimeError, match="simulated crash"):
        await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    monkeypatch.setattr(OntologyAgent, "propose", original_propose)
    retried = await propose_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert retried.session.revision.stage is OnboardingStage.CONCEPT_MODEL_PROPOSED


async def test_propose_fails_closed_on_provider_failure():
    store = JsonRoundTripImmutableRecordStore()
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)

    from core.engine.core.intelligence_builder_concept_progression import (
        IntelligenceBuilderConceptProgressionUnavailable,
    )

    with pytest.raises(IntelligenceBuilderConceptProgressionUnavailable):
        await propose_intelligence_builder_concept_model(
            request=request, user=_owner(), runtime=_runtime(store, _RaisingProvider())
        )

    sessions = IntelligenceBuilderSessionService(store=store)
    latest = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=session.session_id, available_at=proposed_at
    )
    assert latest is not None
    assert latest.stage is not OnboardingStage.CONCEPT_MODEL_PROPOSED


# --- approve_intelligence_builder_concept_model ---


async def _proposed_chain(store, provider_respond=_concept_response):
    session, profile, connected_at = await _sources_ready_chain(store)
    proposed_at = connected_at + timedelta(seconds=1)
    provider = _SpyProvider(provider_respond)
    request, _ = _propose_request(session, profile, proposed_at=proposed_at)
    proposed = await propose_intelligence_builder_concept_model(
        request=request, user=_owner(), runtime=_runtime(store, provider)
    )
    return proposed, proposed_at


async def test_approve_persists_its_own_separate_reviewed_receipt():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)

    result = await approve_intelligence_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=_runtime(store, provider=None),
    )

    assert result.approval.session.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED
    assert result.reviewed_approval.approval.receipt_ref.startswith("approval:builder-concept-model:")
    assert result.approval.disposition.approval_receipt_ref == result.reviewed_approval.approval.receipt_ref
    # The reviewed receipt and the agent's own disposition are two separate durable artifacts.
    assert result.reviewed_approval.proposal_id == result.approval.disposition.proposal_id


async def test_approve_is_idempotent_on_retry_without_another_call():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(store, provider=None)
    request = BuilderConceptModelApproveRequestV1Alpha1(
        decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
    )

    first = await approve_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)
    second = await approve_intelligence_builder_concept_model(request=request, user=_owner(), runtime=runtime)

    assert first.approval.session.revision.revision_id == second.approval.session.revision.revision_id
    assert first.reviewed_approval.approval.receipt_ref == second.reviewed_approval.approval.receipt_ref


async def test_approve_retry_fails_closed_on_changed_time():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(store, provider=None)

    await approve_intelligence_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=runtime,
    )

    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await approve_intelligence_builder_concept_model(
            request=BuilderConceptModelApproveRequestV1Alpha1(
                decision="approve",
                current=proposed.session.revision,
                proposal=proposed.proposal,
                approved_at=approved_at + timedelta(seconds=1),
            ),
            user=_owner(),
            runtime=runtime,
        )


async def test_approve_fails_closed_on_stale_session():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(store, provider=None)

    session, profile, connected_at = await _sources_ready_chain(JsonRoundTripImmutableRecordStore())  # unrelated store
    with pytest.raises(IntelligenceBuilderConceptProgressionConflict):
        await approve_intelligence_builder_concept_model(
            request=BuilderConceptModelApproveRequestV1Alpha1(
                decision="approve",
                current=session,  # stale: not the proposed revision on this store
                proposal=proposed.proposal,
                approved_at=approved_at,
            ),
            user=_owner(),
            runtime=runtime,
        )


async def test_approve_fails_closed_on_wrong_owner():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)

    with pytest.raises(IntelligenceBuilderConceptProgressionDenied):
        await approve_intelligence_builder_concept_model(
            request=BuilderConceptModelApproveRequestV1Alpha1(
                decision="approve",
                current=proposed.session.revision,
                proposal=proposed.proposal,
                approved_at=approved_at,
            ),
            user=_owner(sub="user:someone-else"),
            runtime=_runtime(store, provider=None),
        )


async def test_approve_never_creates_a_grant():
    store = JsonRoundTripImmutableRecordStore()
    proposed, proposed_at = await _proposed_chain(store)
    approved_at = proposed_at + timedelta(seconds=1)

    class _AssertingGrantAuthority(_NoGrantAuthority):
        pass

    runtime = IntelligenceBuilderConceptProgressionRuntime(
        records=store, grants=_AssertingGrantAuthority(), provider=None
    )
    # If the coordinator ever tried to mint or resolve a grant, the delegate above raises.
    result = await approve_intelligence_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=runtime,
    )
    assert result.approval.session.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED
