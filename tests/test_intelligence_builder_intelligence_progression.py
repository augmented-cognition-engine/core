"""Tests for the Builder-to-Intelligence/Briefing-Agent progression coordinator (PI13 addendum 9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from ace.application.intelligence_agent_contracts import ProposedCadence
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingArtifactKind, OnboardingStage
from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingScope,
    authorize_local_source_connect,
    preview_local_source_connect,
)
from ace.application.ontology_agent import OntologyAgent
from ace.application.ontology_agent_contracts import OrganizationTerminologyV1
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.records import ImmutableRecordV1, immutable_record_storage_id
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from ace.testing.ontology_agent import FixtureConceptModelStrategy
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderIntelligenceModelApproveRequestV1Alpha1,
    BuilderSourceScopeApproveRequestV1Alpha1,
    RecordedIntelligenceBuilderDispositionAuthority,
    approve_builder_concept_model,
    approve_builder_source_scope,
)
from core.engine.core.intelligence_builder_intelligence_progression import (
    _BRIEF_INTENT_RECORD_KIND,
    _BRIEF_INTENT_RECORD_SPACE,
    _PROPOSAL_INTENT_RECORD_KIND,
    _PROPOSAL_INTENT_RECORD_SPACE,
    FirstBriefPrepareRequestV1Alpha1,
    IntelligenceBuilderIntelligenceProgressionConflict,
    IntelligenceBuilderIntelligenceProgressionDenied,
    IntelligenceBuilderIntelligenceProgressionRuntime,
    IntelligenceBuilderIntelligenceProgressionUnavailable,
    IntelligenceModelProposeRequestV1Alpha1,
    _brief_intent_key,
    _build_first_briefing_intent,
    _build_proposal_intent,
    _expected_intent_record,
    _persist_proposal_intent,
    _proposal_intent_key,
    approve_intelligence_builder_intelligence_model,
    prepare_intelligence_builder_first_brief,
    propose_intelligence_builder_intelligence_model,
)
from core.engine.core.intelligence_builder_observation_admission import admit_local_source_observations
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID
from core.engine.core.local_source_connect import (
    LocalSourceConnectRecordRepository,
    LocalSourceConnectRecordUnavailable,
)
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    connect_local_source_connect_scope,
    propose_local_source_connect_scope,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

_ALPHA_PAYLOAD = {
    "status": "ready",
    "value": 42,
    "notes": ["- Reviewed the exact recorded source material.", "- Confirmed status against captured evidence."],
}
_BETA_PAYLOAD = {
    "status": "pending",
    "value": 7,
    "notes": ["- Needs one more pass before it is considered ready."],
}


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):
        raise AssertionError("intelligence progression never resolves a grant through this delegate")


def _owner(**overrides) -> dict:
    values = {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["intelligence_build", "observe_read"],
        "local_owner": True,
    }
    values.update(overrides)
    return values


def _pack(name: str = "pi13-ws3-intelligence-progression") -> CompiledPackRefV1:
    digest = canonical_hash({"pack": name})
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
        authorized_root="/nonexistent/pi13-intelligence-progression/host-local-root",
        mapping_scopes=(_scope(),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewRequest(**values)


def _authorization_request(**preview_overrides) -> LocalSourceConnectAuthorizationRequest:
    preview = preview_local_source_connect(_preview_request(**preview_overrides))
    return LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=_AUTHORIZED_AT)


def _provider_identity(**overrides) -> CapabilityArtifactIdentityV1Alpha1:
    values = dict(
        capability="source_snapshot",
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="spy-provider",
        implementation_version="1.0.0",
        artifact_digest=f"sha256:{canonical_hash({'provider': 'spy'})}",
    )
    values.update(overrides)
    return CapabilityArtifactIdentityV1Alpha1(**values)


class _SnapshotProvider:
    def __init__(self, files: tuple[AcquiredLocalFile, ...] = ()) -> None:
        self.artifact_identity = _provider_identity()
        self.files = files

    async def snapshot(self, request):
        return self.files


def _acquired_markdown_file(relative_path: str, payload: object, **overrides) -> AcquiredLocalFile:
    payload_json = canonical_json(payload)
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(payload_json),
        status="acquired",
        structured_payload_json=payload_json,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


async def _build_result(request, files):
    return await authorize_local_source_connect(request, _SnapshotProvider(files=files))


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


def _intelligence_response(parsed: dict[str, Any]) -> dict[str, Any]:
    observations = parsed["trusted_context"]["observations"]["observations"]
    concept_model = parsed["trusted_context"]["concept_model"]
    entity_type_id = concept_model["entity_types"][0]["type_id"]
    citations = []
    for index, observation in enumerate(observations):
        attributes = json.loads(observation["attributes"]["value_json"])
        field_path = f"/{next(iter(attributes))}"
        citations.append(
            {
                "citation_id": f"obs_{index}",
                "observation_id": observation["observation_id"],
                "field_path": field_path,
            }
        )
    citation_ids = [item["citation_id"] for item in citations]
    return {
        "citations": citations,
        "watch_targets": [
            {
                "target_id": "watch-status",
                "target_kind": "attribute",
                "entity_type_id": entity_type_id,
                "member_id": "status",
                "citation_ids": citation_ids,
            }
        ],
        "baselines": [
            {
                "baseline_id": "baseline-status",
                "target_id": "watch-status",
                "value": {"value_json": json.dumps({"status": "ready"})},
                "as_of": observations[0]["as_of"],
                "citation_ids": citation_ids,
            }
        ],
        "detectors": [
            {
                "detector_id": "detector-status-shift",
                "target_id": "watch-status",
                "strategy": "categorical_transition",
                "configuration": {"value_json": json.dumps({"field": "status"})},
                "citation_ids": citation_ids,
            }
        ],
        "materiality_rules": [
            {
                "rule_id": "materiality-status",
                "detector_id": "detector-status-shift",
                "minimum_change": 1.0,
                "minimum_confidence": 0.5,
                "rationale": "Any status shift is material.",
                "citation_ids": citation_ids,
            }
        ],
        "audiences": [
            {
                "audience_id": "audience-owner",
                "display_name": "Local Owner",
                "purpose": "The local Intelligence owner.",
            }
        ],
        "routes": [
            {
                "route_id": "route-owner-on-demand",
                "audience_ids": ["audience-owner"],
                "target_ids": ["watch-status"],
                "cadence": "daily",
                "minimum_confidence": 0.5,
            }
        ],
        "suppression_grouping_rules": [
            {
                "rule_id": "suppress-duplicate-status",
                "target_ids": ["watch-status"],
                "suppress_below_confidence": 0.3,
                "rationale": "Suppress duplicate status shift notices within one pass.",
            }
        ],
        "epistemic_statements": [
            {
                "statement_id": f"statement-{classification}",
                "classification": classification,
                "statement": f"A bounded {classification} statement over the admitted evidence.",
                "citation_ids": (
                    citation_ids if classification == "disagreement" else [citation_ids[index % len(citation_ids)]]
                ),
                "confidence": 0.9,
            }
            for index, classification in enumerate(("observation", "claim", "inference", "disagreement", "unknown"))
        ],
        "conflicts": [],
        "unknowns": ["No unknowns beyond the bounded admitted evidence closure."],
        "exclusions": [
            "No source credentials, connector configuration, monitoring policy, or activation authority.",
        ],
        "confidence": 0.9,
    }


def _low_confidence_intelligence_response(parsed: dict[str, Any]) -> dict[str, Any]:
    material = _intelligence_response(parsed)
    material["confidence"] = 0.1
    return material


_ITEM_KIND_BY_CLASSIFICATION = {
    "observation": "current_state",
    "claim": "signal",
    "inference": "shift",
    "disagreement": "disagreement",
    "unknown": "unknown",
}


def _brief_response(parsed: dict[str, Any]) -> dict[str, Any]:
    intelligence_model = parsed["trusted_context"]["intelligence_model"]
    materiality_rule_id = intelligence_model["materiality_rules"][0]["rule_id"]
    items = []
    for statement in intelligence_model["epistemic_statements"]:
        classification = statement["classification"]
        item_kind = _ITEM_KIND_BY_CLASSIFICATION[classification]
        item = {
            "item_id": f"item-{classification}",
            "item_kind": item_kind,
            "title": f"A bounded {classification} item over admitted evidence.",
            "summary": f"The admitted evidence supports this {classification} item.",
            "why_it_matters": "Confirms the bounded orientation the owner requested.",
            "epistemic_classification": classification,
            "statement_ids": [statement["statement_id"]],
            "citation_ids": list(statement["citation_ids"]),
            "counterevidence_citation_ids": [],
            "confidence": 0.9,
            "uncertainty": "None beyond the cited admitted evidence.",
        }
        if item_kind in {"signal", "shift"}:
            item["materiality_rule_id"] = materiality_rule_id
        items.append(item)
    return {
        "title": "First Brief",
        "executive_summary": "A bounded first Brief over the exact admitted evidence.",
        "items": items,
        "freshness_statement": "As of the exact admitted evidence timestamps.",
    }


def _no_material_shifts_response(parsed: dict[str, Any]) -> dict[str, Any]:
    return {"no_material_shifts": True}


def _runtime(store, repository, provider) -> IntelligenceBuilderIntelligenceProgressionRuntime:
    return IntelligenceBuilderIntelligenceProgressionRuntime(
        records=store, grants=_NoGrantAuthority(), repository=repository, provider=provider
    )


async def _concept_model_approved_chain(
    *,
    correlation_id: str = "correlation:ws3-intelligence-progression",
    mapping_id: str = "mapping-a",
    alpha_payload: dict = _ALPHA_PAYLOAD,
    beta_payload: dict = _BETA_PAYLOAD,
):
    """Build one real durable sequence through CONCEPT_MODEL_APPROVED, mirroring
    the observation-admission test's fixture chain (reused deliberately)."""

    request = _authorization_request(mapping_scopes=(_scope(mapping_id=mapping_id),))
    result = await _build_result(
        request,
        (
            _acquired_markdown_file("notes/alpha.md", alpha_payload),
            _acquired_markdown_file("notes/beta.md", beta_payload),
        ),
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)

    sessions = IntelligenceBuilderSessionService(store=store)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id=correlation_id,
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
    scope_approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    connect_at = approved_at + timedelta(seconds=1)
    connected = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=scope_approval.approval.receipt_ref,
        user=_owner(),
        runtime=connect_runtime,
        occurred_at=connect_at,
    )
    assert connected.connected is True

    resolver = RecordedIntelligenceBuilderDispositionAuthority(records=store, grants=_NoGrantAuthority())
    ontology_agent = OntologyAgent(sessions=sessions, authority=resolver, strategy=FixtureConceptModelStrategy())
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
            decision="approve", current=concept_current, proposal=concept_proposal, approved_at=concept_approved_at
        ),
        user=_owner(),
        records=store,
    )
    concept_approved = await ontology_agent.approve(
        concept_current,
        proposal=concept_proposal,
        approval_receipt_ref=concept_approval.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=concept_approved_at,
    )
    assert concept_approved.session.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED

    return {
        "request": request,
        "result": result,
        "store": store,
        "sessions": sessions,
        "repository": repository,
        "session": concept_approved.session.revision,
        "wrong_stage_session": concept_current,
        "source_profile": connected.profile,
        "concept_model": concept_proposal,
        "concept_disposition": concept_approved.disposition,
        "connect_at": connect_at,
    }


def _propose_request(chain, *, proposed_at, **overrides) -> IntelligenceModelProposeRequestV1Alpha1:
    values = dict(
        current=chain["session"],
        connect_request=chain["request"],
        connect_result=chain["result"],
        source_profile=chain["source_profile"],
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        user_intent="Understand the status and value of approved source-grounded records.",
        proposed_at=proposed_at,
    )
    values.update(overrides)
    return IntelligenceModelProposeRequestV1Alpha1(**values)


async def _alternate_connect_material(
    *, mapping_id: str = "mapping-alt-connect"
) -> tuple[LocalSourceConnectAuthorizationRequest, LocalSourceConnectAuthorizationResult]:
    request = _authorization_request(mapping_scopes=(_scope(mapping_id=mapping_id),))
    result = await _build_result(
        request,
        (_acquired_markdown_file("notes/alt.md", {"status": "ready", "value": 99, "notes": ["- an alternate note."]}),),
    )
    return request, result


def _tamper_stored_intent_record(store: InMemoryImmutableRecordStore, *, record_space: str) -> None:
    for storage_id, record in list(store.records.items()):
        if record.record_space == record_space:
            tampered = ImmutableRecordV1(
                product_id=record.product_id,
                record_space=record.record_space,
                record_kind=record.record_kind,
                record_key=record.record_key,
                payload_contract=record.payload_contract,
                payload=record.payload,
                as_of=record.as_of,
                available_at=record.available_at + timedelta(seconds=1),
                processing_order=record.processing_order,
            )
            store.records[storage_id] = tampered
            return
    raise AssertionError("no stored intent record found to tamper")


# --- propose_intelligence_builder_intelligence_model ---


async def test_propose_produces_intelligence_model_via_selected_provider_and_admits_observations():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)

    result = await propose_intelligence_builder_intelligence_model(
        request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
    )

    assert provider.calls == 1
    assert result.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_PROPOSED
    assert len(result.proposal.watch_targets) == 1
    assert result.proposal.observation_set_id


async def test_propose_calls_the_provider_exactly_once():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)

    await propose_intelligence_builder_intelligence_model(
        request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
    )

    assert provider.calls == 1


async def test_propose_is_idempotent_on_retry_without_another_provider_call():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    first = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    second = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_propose_retry_fails_closed_on_changed_time():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    changed = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "proposed_at": proposed_at + timedelta(seconds=1)}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=changed, user=_owner(), runtime=runtime)


async def test_propose_retry_fails_closed_on_changed_material():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    changed = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "user_intent": "A materially different exact user intent."}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=changed, user=_owner(), runtime=runtime)


async def test_propose_fails_closed_on_advanced_session_chain():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    proposed = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    approved_at = proposed_at + timedelta(seconds=1)
    await approve_intelligence_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve",
            current=proposed.session.revision,
            proposal=proposed.proposal,
            approved_at=approved_at,
        ),
        user=_owner(),
        runtime=runtime,
    )

    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "proposed_at": approved_at + timedelta(seconds=1)}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)


async def test_propose_fails_closed_on_wrong_owner():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionDenied):
        await propose_intelligence_builder_intelligence_model(
            request=request,
            user=_owner(sub="user:someone-else"),
            runtime=_runtime(chain["store"], chain["repository"], provider),
        )


async def test_propose_fails_closed_on_wrong_stage():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at, current=chain["wrong_stage_session"])

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(
            request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
        )


async def test_propose_fails_closed_on_low_confidence_without_creating_a_proposed_session():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_low_confidence_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionDenied):
        await propose_intelligence_builder_intelligence_model(
            request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
        )

    latest = await chain["sessions"].load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=chain["session"].session_id, available_at=proposed_at
    )
    assert latest is not None
    assert latest.stage is not OnboardingStage.INTELLIGENCE_MODEL_PROPOSED


async def test_propose_fails_closed_on_provider_failure_and_sanitizes_the_error():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    request = _propose_request(chain, proposed_at=proposed_at)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionUnavailable) as excinfo:
        await propose_intelligence_builder_intelligence_model(
            request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], _RaisingProvider())
        )
    assert "secret transport detail" not in str(excinfo.value)

    latest = await chain["sessions"].load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=chain["session"].session_id, available_at=proposed_at
    )
    assert latest is not None
    assert latest.stage is not OnboardingStage.INTELLIGENCE_MODEL_PROPOSED


async def test_proposal_intent_admits_only_one_of_two_different_requests_for_same_prior_revision():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    request_a = _propose_request(chain, proposed_at=proposed_at)
    request_b = _propose_request(
        chain,
        proposed_at=proposed_at + timedelta(seconds=2),
        user_intent="A materially different exact user intent for this same prior revision.",
    )
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=chain["session"])
    admission = await admit_local_source_observations(
        request=chain["request"],
        result=chain["result"],
        session=chain["session"],
        source_profile=chain["source_profile"],
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        user=_owner(),
        admitted_at=proposed_at,
        repository=chain["repository"],
        sessions=chain["sessions"],
    )

    await _persist_proposal_intent(
        records=chain["store"],
        intent_key=key,
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session=chain["session"],
        request=request_a,
        observations=admission.observation_set,
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await _persist_proposal_intent(
            records=chain["store"],
            intent_key=key,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            session=chain["session"],
            request=request_b,
            observations=admission.observation_set,
        )


async def test_propose_two_different_requests_for_same_prior_revision_only_one_calls_provider():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    runtime = _runtime(chain["store"], chain["repository"], provider)
    request_a = _propose_request(chain, proposed_at=proposed_at)
    request_b = _propose_request(
        chain,
        proposed_at=proposed_at,
        user_intent="A materially different exact user intent for this same prior revision.",
    )

    await propose_intelligence_builder_intelligence_model(request=request_a, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=request_b, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_recovers_from_crash_after_agent_success_without_another_provider_call(monkeypatch):
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    from ace.application.intelligence_agent import IntelligenceAgent

    original_propose = IntelligenceAgent.propose

    async def crashing_propose(self, *args, **kwargs):
        outcome = await original_propose(self, *args, **kwargs)
        raise RuntimeError("simulated crash after the durable agent transition already succeeded")

    monkeypatch.setattr(IntelligenceAgent, "propose", crashing_propose)
    with pytest.raises(RuntimeError, match="simulated crash"):
        await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    monkeypatch.setattr(IntelligenceAgent, "propose", original_propose)
    retried = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert retried.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_PROPOSED


# --- approve_intelligence_builder_intelligence_model ---


async def _proposed_chain(chain, provider_respond=_intelligence_response):
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(provider_respond)
    request = _propose_request(chain, proposed_at=proposed_at)
    proposed = await propose_intelligence_builder_intelligence_model(
        request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
    )
    return proposed, proposed_at


async def test_approve_persists_its_own_separate_reviewed_receipt():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)

    result = await approve_intelligence_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=_runtime(chain["store"], chain["repository"], provider=None),
    )

    assert result.approval.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
    assert result.reviewed_approval.approval.receipt_ref.startswith("approval:builder-intelligence-model:")
    assert result.approval.disposition.approval_receipt_ref == result.reviewed_approval.approval.receipt_ref
    assert result.reviewed_approval.proposal_id == result.approval.disposition.proposal_id


async def test_approve_is_idempotent_on_retry_without_another_call():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(chain["store"], chain["repository"], provider=None)
    request = BuilderIntelligenceModelApproveRequestV1Alpha1(
        decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
    )

    first = await approve_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    second = await approve_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    assert first.approval.session.revision.revision_id == second.approval.session.revision.revision_id
    assert first.reviewed_approval.approval.receipt_ref == second.reviewed_approval.approval.receipt_ref


async def test_approve_retry_fails_closed_on_changed_time():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(chain["store"], chain["repository"], provider=None)

    await approve_intelligence_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=runtime,
    )

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await approve_intelligence_builder_intelligence_model(
            request=BuilderIntelligenceModelApproveRequestV1Alpha1(
                decision="approve",
                current=proposed.session.revision,
                proposal=proposed.proposal,
                approved_at=approved_at + timedelta(seconds=1),
            ),
            user=_owner(),
            runtime=runtime,
        )


async def test_approve_fails_closed_on_stale_session():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)
    runtime = _runtime(chain["store"], chain["repository"], provider=None)

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-unrelated", mapping_id="mapping-unrelated"
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await approve_intelligence_builder_intelligence_model(
            request=BuilderIntelligenceModelApproveRequestV1Alpha1(
                decision="approve",
                current=other_chain["session"],
                proposal=proposed.proposal,
                approved_at=approved_at,
            ),
            user=_owner(),
            runtime=runtime,
        )


async def test_approve_fails_closed_on_wrong_owner():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionDenied):
        await approve_intelligence_builder_intelligence_model(
            request=BuilderIntelligenceModelApproveRequestV1Alpha1(
                decision="approve",
                current=proposed.session.revision,
                proposal=proposed.proposal,
                approved_at=approved_at,
            ),
            user=_owner(sub="user:someone-else"),
            runtime=_runtime(chain["store"], chain["repository"], provider=None),
        )


async def test_approve_never_creates_a_grant():
    chain = await _concept_model_approved_chain()
    proposed, proposed_at = await _proposed_chain(chain)
    approved_at = proposed_at + timedelta(seconds=1)

    class _AssertingGrantAuthority(_NoGrantAuthority):
        pass

    runtime = IntelligenceBuilderIntelligenceProgressionRuntime(
        records=chain["store"], grants=_AssertingGrantAuthority(), repository=chain["repository"], provider=None
    )
    result = await approve_intelligence_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=runtime,
    )
    assert result.approval.session.revision.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED


# --- prepare_intelligence_builder_first_brief ---


async def _intelligence_model_approved_chain(chain, provider_respond=_intelligence_response):
    proposed, proposed_at = await _proposed_chain(chain, provider_respond=provider_respond)
    approved_at = proposed_at + timedelta(seconds=1)
    approved = await approve_intelligence_builder_intelligence_model(
        request=BuilderIntelligenceModelApproveRequestV1Alpha1(
            decision="approve", current=proposed.session.revision, proposal=proposed.proposal, approved_at=approved_at
        ),
        user=_owner(),
        runtime=_runtime(chain["store"], chain["repository"], provider=None),
    )
    return approved, approved_at


async def _load_admitted_observations(chain, session):
    """Reopen the exact ``AuthorizedObservationSetV1`` already admitted during
    proposal, from its durable artifact reference on the current session --
    never by calling ``admit_local_source_observations`` again (which
    requires the exact CONCEPT_MODEL_APPROVED session, already advanced
    past by this point in these tests)."""

    from ace.application.intelligence_agent_contracts import AuthorizedObservationSetV1

    reference = next(
        item for item in session.artifacts if item.artifact_kind is OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET
    )
    return await chain["sessions"].load_artifact(
        product_id=session.product_id,
        reference=reference,
        artifact_type=AuthorizedObservationSetV1,
        available_at=session.occurred_at,
    )


async def test_prepare_first_brief_via_selected_provider():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )

    result = await prepare_intelligence_builder_first_brief(
        request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
    )

    assert provider.calls == 1
    assert result.session.revision.stage is OnboardingStage.FIRST_BRIEFING_READY
    assert result.brief.title == "First Brief"


async def test_prepare_first_brief_is_idempotent_on_retry_without_another_provider_call():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )
    runtime = _runtime(chain["store"], chain["repository"], provider)

    first = await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    second = await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert first.brief.brief_id == second.brief.brief_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_prepare_first_brief_retry_fails_closed_on_changed_time():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)

    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "generated_at": generated_at + timedelta(seconds=1)}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)


async def test_prepare_first_brief_fails_closed_on_wrong_owner():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionDenied):
        await prepare_intelligence_builder_first_brief(
            request=request,
            user=_owner(sub="user:someone-else"),
            runtime=_runtime(chain["store"], chain["repository"], provider),
        )


async def test_prepare_first_brief_fails_closed_on_wrong_stage():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=chain[
            "session"
        ],  # real durable session, but at CONCEPT_MODEL_APPROVED, not INTELLIGENCE_MODEL_APPROVED
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(
            request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
        )


async def test_prepare_first_brief_fails_closed_on_no_material_shifts():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_no_material_shifts_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionDenied):
        await prepare_intelligence_builder_first_brief(
            request=request, user=_owner(), runtime=_runtime(chain["store"], chain["repository"], provider)
        )

    latest = await chain["sessions"].load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=chain["session"].session_id, available_at=generated_at
    )
    assert latest is not None
    assert latest.stage is not OnboardingStage.FIRST_BRIEFING_READY


async def test_prepare_first_brief_intent_key_is_bound_to_prior_revision():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    key = _brief_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=approved.approval.session.revision)
    assert key.startswith("first-briefing-intent:")


# --- adversarial review-correction coverage ---


async def test_propose_advanced_retry_fails_closed_on_changed_connect_request():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    alt_request, _ = await _alternate_connect_material()
    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "connect_request": alt_request}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_changed_connect_result():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    _, alt_result = await _alternate_connect_material()
    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "connect_result": alt_result}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_changed_source_profile():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-alt-profile", mapping_id="mapping-alt-profile"
    )
    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "source_profile": other_chain["source_profile"]}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_changed_concept_model():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-alt-model", mapping_id="mapping-alt-model"
    )
    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_model": other_chain["concept_model"]}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_changed_concept_disposition():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-alt-disposition", mapping_id="mapping-alt-disposition"
    )
    raced = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_disposition": other_chain["concept_disposition"]}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=raced, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_reopens_the_same_durable_proposal_on_an_exact_same_retry():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    first = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    second = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_propose_advanced_retry_fails_closed_when_the_connect_transaction_cannot_be_reopened():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    class _UnavailableRepository:
        async def replay(self, *_args, **_kwargs):
            raise LocalSourceConnectRecordUnavailable("simulated Connect transaction storage outage")

    broken_runtime = IntelligenceBuilderIntelligenceProgressionRuntime(
        records=chain["store"], grants=_NoGrantAuthority(), repository=_UnavailableRepository(), provider=provider
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionUnavailable):
        await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=broken_runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_when_a_different_connect_result_replays():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    _, alt_result = await _alternate_connect_material()

    class _MismatchedRepository:
        async def replay(self, *_args, **_kwargs):
            return alt_result

    mismatched_runtime = IntelligenceBuilderIntelligenceProgressionRuntime(
        records=chain["store"], grants=_NoGrantAuthority(), repository=_MismatchedRepository(), provider=provider
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(
            request=request, user=_owner(), runtime=mismatched_runtime
        )
    assert provider.calls == 1


def _first_brief_request(chain, approved, observations, *, generated_at) -> FirstBriefPrepareRequestV1Alpha1:
    return FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )


async def test_prepare_first_brief_retry_fails_closed_on_changed_concept_model():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-alt-model", mapping_id="mapping-brief-alt-model"
    )
    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_model": other_chain["concept_model"]}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_retry_fails_closed_on_changed_concept_disposition():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-alt-disposition",
        mapping_id="mapping-brief-alt-disposition",
    )
    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_disposition": other_chain["concept_disposition"]}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_retry_fails_closed_on_changed_intelligence_model():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-alt-intelligence",
        mapping_id="mapping-brief-alt-intelligence",
    )
    other_approved, _ = await _intelligence_model_approved_chain(other_chain)
    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "intelligence_model": other_approved.approval.proposal}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_retry_fails_closed_on_changed_intelligence_disposition():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-alt-disp2",
        mapping_id="mapping-brief-alt-disp2",
    )
    other_approved, _ = await _intelligence_model_approved_chain(other_chain)
    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "intelligence_disposition": other_approved.approval.disposition}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_retry_fails_closed_on_changed_observations():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-alt-observations",
        mapping_id="mapping-brief-alt-observations",
    )
    other_approved, _ = await _intelligence_model_approved_chain(other_chain)
    other_observations = await _load_admitted_observations(other_chain, other_approved.approval.session.revision)
    changed = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "observations": other_observations}
    )
    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=changed, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_advanced_retry_reopens_the_same_durable_brief_on_an_exact_same_retry():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    first = await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    second = await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert first.brief.brief_id == second.brief.brief_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_propose_replay_conflict_fails_closed_on_tampered_record_envelope():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    request = _propose_request(chain, proposed_at=proposed_at)
    admission = await admit_local_source_observations(
        request=chain["request"],
        result=chain["result"],
        session=chain["session"],
        source_profile=chain["source_profile"],
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        user=_owner(),
        admitted_at=proposed_at,
        repository=chain["repository"],
        sessions=chain["sessions"],
    )
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=chain["session"])
    await _persist_proposal_intent(
        records=chain["store"],
        intent_key=key,
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session=chain["session"],
        request=request,
        observations=admission.observation_set,
    )

    _tamper_stored_intent_record(chain["store"], record_space=_PROPOSAL_INTENT_RECORD_SPACE)
    chain["store"].receipts.clear()

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await _persist_proposal_intent(
            records=chain["store"],
            intent_key=key,
            product_id=LOCAL_OWNER_PRODUCT_ID,
            session=chain["session"],
            request=request,
            observations=admission.observation_set,
        )


async def test_propose_advanced_retry_fails_closed_on_tampered_record_envelope():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    _tamper_stored_intent_record(chain["store"], record_space=_PROPOSAL_INTENT_RECORD_SPACE)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_a_coherently_tampered_intent_record():
    """A maliciously recomputed intent record whose envelope, digests, and
    ``request_material_digest`` are all internally self-consistent with a
    forged retried request must still be rejected once its claimed concept
    model no longer matches the durable artifact this proposal was actually
    bound to."""

    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    proposed = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-forged-model",
        mapping_id="mapping-forged-model",
    )
    observations = await _load_admitted_observations(chain, proposed.session.revision)
    forged_request = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_model": other_chain["concept_model"]}
    )
    forged_intent = _build_proposal_intent(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session=chain["session"],
        request=forged_request,
        observations=observations,
    )
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=chain["session"])
    storage_id = immutable_record_storage_id(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=key,
    )
    forged_record = _expected_intent_record(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=key,
        intent=forged_intent,
        intent_time=forged_intent.proposed_at,
    )
    chain["store"].records[storage_id] = forged_record

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=forged_request, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_propose_advanced_retry_fails_closed_on_a_coherently_forged_source_profile_claim():
    """A coherently recomputed intent/record that consistently claims a
    different source profile than the one this proposal was actually bound
    to must still be rejected: the durable authorized-observation-set this
    proposal actually admitted from still points at its real source
    profile, not the forged one."""

    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    provider = _SpyProvider(_intelligence_response)
    request = _propose_request(chain, proposed_at=proposed_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    proposed = await propose_intelligence_builder_intelligence_model(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-forged-source-profile",
        mapping_id="mapping-forged-source-profile",
    )
    observations = await _load_admitted_observations(chain, proposed.session.revision)
    forged_request = IntelligenceModelProposeRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "source_profile": other_chain["source_profile"]}
    )
    forged_intent = _build_proposal_intent(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session=chain["session"],
        request=forged_request,
        observations=observations,
    )
    key = _proposal_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=chain["session"])
    storage_id = immutable_record_storage_id(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=key,
    )
    forged_record = _expected_intent_record(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=key,
        intent=forged_intent,
        intent_time=forged_intent.proposed_at,
    )
    chain["store"].records[storage_id] = forged_record

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await propose_intelligence_builder_intelligence_model(request=forged_request, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_replay_conflict_fails_closed_on_tampered_record_envelope():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    _tamper_stored_intent_record(chain["store"], record_space=_BRIEF_INTENT_RECORD_SPACE)

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_advanced_retry_fails_closed_on_a_coherently_tampered_intent_record():
    """A maliciously recomputed first-Brief intent record whose envelope,
    digests, and ``request_material_digest`` are all internally
    self-consistent with a forged retried request must still be rejected
    once its claimed concept model no longer matches the durable artifact
    this first Brief was actually bound to."""

    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = _first_brief_request(chain, approved, observations, generated_at=generated_at)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-forged-model",
        mapping_id="mapping-brief-forged-model",
    )
    forged_request = FirstBriefPrepareRequestV1Alpha1(
        **{**request.model_dump(mode="python"), "concept_model": other_chain["concept_model"]}
    )
    forged_intent = _build_first_briefing_intent(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session=approved.approval.session.revision,
        request=forged_request,
    )
    key = _brief_intent_key(product_id=LOCAL_OWNER_PRODUCT_ID, session=approved.approval.session.revision)
    storage_id = immutable_record_storage_id(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=key,
    )
    forged_record = _expected_intent_record(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=key,
        intent=forged_intent,
        intent_time=forged_intent.generated_at,
    )
    chain["store"].records[storage_id] = forged_record

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=forged_request, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_two_different_requests_for_same_prior_revision_only_one_calls_provider():
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    runtime = _runtime(chain["store"], chain["repository"], provider)

    other_chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-intelligence-progression-brief-race", mapping_id="mapping-brief-race"
    )
    request_a = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )
    request_b = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=other_chain["concept_model"],
        concept_disposition=other_chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )

    await prepare_intelligence_builder_first_brief(request=request_a, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    with pytest.raises(IntelligenceBuilderIntelligenceProgressionConflict):
        await prepare_intelligence_builder_first_brief(request=request_b, user=_owner(), runtime=runtime)
    assert provider.calls == 1


async def test_prepare_first_brief_recovers_from_crash_after_agent_success_without_another_provider_call(monkeypatch):
    chain = await _concept_model_approved_chain()
    approved, approved_at = await _intelligence_model_approved_chain(chain)
    generated_at = approved_at + timedelta(seconds=1)
    observations = await _load_admitted_observations(chain, approved.approval.session.revision)
    provider = _SpyProvider(_brief_response)
    request = FirstBriefPrepareRequestV1Alpha1(
        current=approved.approval.session.revision,
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        intelligence_model=approved.approval.proposal,
        intelligence_disposition=approved.approval.disposition,
        observations=observations,
        generated_at=generated_at,
    )
    runtime = _runtime(chain["store"], chain["repository"], provider)

    from ace.application.briefing_agent import BriefingAgent

    original_create_first_brief = BriefingAgent.create_first_brief

    async def crashing_create_first_brief(self, *args, **kwargs):
        outcome = await original_create_first_brief(self, *args, **kwargs)
        raise RuntimeError("simulated crash after the durable agent transition already succeeded")

    monkeypatch.setattr(BriefingAgent, "create_first_brief", crashing_create_first_brief)
    with pytest.raises(RuntimeError, match="simulated crash"):
        await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)
    assert provider.calls == 1

    monkeypatch.setattr(BriefingAgent, "create_first_brief", original_create_first_brief)
    retried = await prepare_intelligence_builder_first_brief(request=request, user=_owner(), runtime=runtime)

    assert provider.calls == 1
    assert retried.session.revision.stage is OnboardingStage.FIRST_BRIEFING_READY


async def test_propose_request_rejects_extra_field_in_nested_connect_request_json():
    chain = await _concept_model_approved_chain()
    proposed_at = chain["connect_at"] + timedelta(seconds=5)
    request = _propose_request(chain, proposed_at=proposed_at)
    tampered_connect_request = {**request.connect_request.model_dump(mode="python"), "unexpected_field": "x"}
    payload = {**request.model_dump(mode="python"), "connect_request": tampered_connect_request}
    with pytest.raises(ValidationError):
        IntelligenceModelProposeRequestV1Alpha1(**payload)


async def test_propose_request_rejects_naive_proposed_at():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(chain, proposed_at=datetime(2026, 8, 21, 12, 0))


async def test_propose_request_rejects_too_many_audience_constraints():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            audience_constraints=tuple(f"audience-{index}" for index in range(65)),
        )


async def test_propose_request_rejects_too_many_cadence_constraints():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            cadence_constraints=(
                ProposedCadence.IMMEDIATE,
                ProposedCadence.DAILY,
                ProposedCadence.WEEKLY,
                ProposedCadence.RECORD_ONLY,
                ProposedCadence.IMMEDIATE,
            ),
        )


async def test_propose_request_rejects_overlong_audience_constraint():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            audience_constraints=("a" * 241,),
        )


async def test_propose_request_rejects_duplicate_audience_constraints():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            audience_constraints=("audience-a", "audience-a"),
        )


async def test_propose_request_rejects_duplicate_cadence_constraints():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            cadence_constraints=(ProposedCadence.DAILY, ProposedCadence.DAILY),
        )


async def test_propose_request_rejects_untrimmed_audience_constraint():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            audience_constraints=(" audience-a ",),
        )


async def test_propose_request_rejects_empty_audience_constraint():
    chain = await _concept_model_approved_chain()
    with pytest.raises(ValidationError):
        _propose_request(
            chain,
            proposed_at=chain["connect_at"] + timedelta(seconds=5),
            audience_constraints=("",),
        )
