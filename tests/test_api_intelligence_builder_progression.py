"""API tests for the WS3 thin host Builder-session progression routes (PI13 addendum 9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_builder_concept_progression import (
    IntelligenceBuilderConceptProgressionRuntime,
    intelligence_builder_concept_progression_runtime,
)
from core.engine.core.intelligence_builder_intelligence_progression import (
    IntelligenceBuilderIntelligenceProgressionRuntime,
    intelligence_builder_intelligence_progression_runtime,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    local_source_connect_scope_progression_runtime,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
_OTHER_ACTOR = "principal:not-the-local-owner"


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):
        raise AssertionError("WS3 progression never resolves a grant through this delegate")


class _RaisingLoadStore(InMemoryImmutableRecordStore):
    """A durable store double whose reads always fail, to exercise the 503 path."""

    async def load_record(self, *args, **kwargs):
        raise RuntimeError("storage unavailable")

    async def load_transaction_receipt(self, *args, **kwargs):
        raise RuntimeError("storage unavailable")


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
    digest = canonical_hash({"pack": "ws3-api-progression-fixture"})
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
        authorized_root="/nonexistent/pi13-ws3-api-progression/host-local-root",
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


class _SpyProvider:
    """Deterministic in-test structured-completion double."""

    def __init__(self, respond: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.respond = respond
        self.calls = 0

    async def complete_json(self, prompt: str, *, model: str | None, max_tokens: int) -> dict[str, Any]:
        self.calls += 1
        return self.respond(json.loads(prompt))


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


def _app(
    *,
    claims: dict,
    store: InMemoryImmutableRecordStore,
    repository: LocalSourceConnectRecordRepository,
    concept_provider,
    intelligence_provider,
    connect_records: InMemoryImmutableRecordStore | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[local_source_connect_scope_progression_runtime] = lambda: (
        LocalSourceConnectScopeProgressionRuntime(
            records=connect_records or store,
            repository=repository,
            grants=_NoGrantAuthority(),
        )
    )
    app.dependency_overrides[intelligence_builder_concept_progression_runtime] = lambda: (
        IntelligenceBuilderConceptProgressionRuntime(
            records=store, grants=_NoGrantAuthority(), provider=concept_provider
        )
    )
    app.dependency_overrides[intelligence_builder_intelligence_progression_runtime] = lambda: (
        IntelligenceBuilderIntelligenceProgressionRuntime(
            records=store, grants=_NoGrantAuthority(), repository=repository, provider=intelligence_provider
        )
    )
    return app


async def _started_session(store: InMemoryImmutableRecordStore, *, correlation_id: str):
    sessions = IntelligenceBuilderSessionService(store=store)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id=correlation_id,
        goal_ref="goal:bounded-orientation",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=_AUTHORIZED_AT,
    )
    return started.revision


def test_route_registration_exposes_all_seven_builder_progression_routes() -> None:
    paths = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    expected = {
        ("/v1/intelligence/builds/builder/source/propose", ("POST",)),
        ("/v1/intelligence/builds/builder/source/approve-connect", ("POST",)),
        ("/v1/intelligence/builds/builder/concept/propose", ("POST",)),
        ("/v1/intelligence/builds/builder/concept/approve", ("POST",)),
        ("/v1/intelligence/builds/builder/intelligence/propose", ("POST",)),
        ("/v1/intelligence/builds/builder/intelligence/approve", ("POST",)),
        ("/v1/intelligence/builds/builder/first-brief/prepare", ("POST",)),
    }
    assert expected.issubset(paths)


@pytest.mark.asyncio
async def test_source_and_concept_progression_chain_succeeds_via_http_and_hides_persistence_internals() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-chain")

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        propose_resp = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert propose_resp.status_code == 200, propose_resp.text
        propose_body = propose_resp.json()
        assert propose_body["contract"] == "ace.http.builder-source-scope-propose-result/v1alpha1"
        assert set(propose_body) == {"contract", "proposal", "session_revision"}
        proposed_session = propose_body["session_revision"]
        assert proposed_session["stage"] == OnboardingStage.SOURCES_CONNECTING.value

        approved_at = (_AUTHORIZED_AT + timedelta(seconds=1)).isoformat()
        approve_connect_resp = await client.post(
            "/v1/intelligence/builds/builder/source/approve-connect",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "approval": {
                    "decision": "approve",
                    "current": proposed_session,
                    "proposal": propose_body["proposal"],
                    "approved_at": approved_at,
                },
            },
        )
        assert approve_connect_resp.status_code == 200, approve_connect_resp.text
        approve_connect_body = approve_connect_resp.json()
        assert approve_connect_body["contract"] == "ace.http.builder-source-scope-approve-connect-result/v1alpha1"
        assert set(approve_connect_body) == {
            "contract",
            "reviewed_approval",
            "profile",
            "session_revision",
            "blocked_reason",
        }
        assert approve_connect_body["blocked_reason"] is None
        assert approve_connect_body["profile"] is not None
        sources_ready_session = approve_connect_body["session_revision"]
        assert sources_ready_session["stage"] == OnboardingStage.SOURCES_READY.value
        reviewed_source_scope_approval = approve_connect_body["reviewed_approval"]
        assert set(reviewed_source_scope_approval) == {
            "contract",
            "approval",
            "session_revision_id",
            "session_revision_digest",
            "proposal_id",
            "proposal_digest",
        }

        concept_proposed_at = (_AUTHORIZED_AT + timedelta(seconds=2)).isoformat()
        concept_propose_resp = await client.post(
            "/v1/intelligence/builds/builder/concept/propose",
            json={
                "current": sources_ready_session,
                "source_profile": approve_connect_body["profile"],
                "user_intent": "Understand the status and value of approved source-grounded records.",
                "organization_terminology": [],
                "proposed_at": concept_proposed_at,
            },
        )
        assert concept_propose_resp.status_code == 200, concept_propose_resp.text
        concept_propose_body = concept_propose_resp.json()
        assert concept_propose_body["contract"] == "ace.http.builder-concept-model-propose-result/v1alpha1"
        assert set(concept_propose_body) == {"contract", "proposal", "session_revision"}
        concept_proposed_session = concept_propose_body["session_revision"]
        assert concept_proposed_session["stage"] == OnboardingStage.CONCEPT_MODEL_PROPOSED.value

        concept_approved_at = (_AUTHORIZED_AT + timedelta(seconds=3)).isoformat()
        concept_approve_resp = await client.post(
            "/v1/intelligence/builds/builder/concept/approve",
            json={
                "decision": "approve",
                "current": concept_proposed_session,
                "proposal": concept_propose_body["proposal"],
                "approved_at": concept_approved_at,
            },
        )
        assert concept_approve_resp.status_code == 200, concept_approve_resp.text
        concept_approve_body = concept_approve_resp.json()
        assert concept_approve_body["contract"] == "ace.http.builder-concept-model-approve-result/v1alpha1"
        assert set(concept_approve_body) == {
            "contract",
            "reviewed_approval",
            "proposal",
            "disposition",
            "session_revision",
        }
        concept_approved_session = concept_approve_body["session_revision"]
        assert concept_approved_session["stage"] == OnboardingStage.CONCEPT_MODEL_APPROVED.value


@pytest.mark.asyncio
async def test_intelligence_and_first_brief_progression_chain_succeeds_via_http_and_hides_persistence_internals() -> (
    None
):
    """Drives the remaining three routes (intelligence propose/approve, first-brief
    prepare) over one real CONCEPT_MODEL_APPROVED chain, reusing the existing
    proven coordinator-level fixture rather than re-deriving the Ontology
    Agent's own strict structured-completion schema in this API test."""

    from tests.test_intelligence_builder_intelligence_progression import (
        _brief_response as _reused_brief_response,
    )
    from tests.test_intelligence_builder_intelligence_progression import (
        _concept_model_approved_chain,
    )
    from tests.test_intelligence_builder_intelligence_progression import (
        _intelligence_response as _reused_intelligence_response,
    )

    def _dispatching_response(parsed: dict[str, Any]) -> dict[str, Any]:
        trusted_context = parsed["trusted_context"]
        if "concept_model" in trusted_context:
            return _reused_intelligence_response(parsed)
        return _reused_brief_response(parsed)

    chain = await _concept_model_approved_chain()
    store: InMemoryImmutableRecordStore = chain["store"]
    repository: LocalSourceConnectRecordRepository = chain["repository"]

    # Derive the exact admitted evidence closure the propose route itself
    # will derive, using the same existing observation-admission host
    # adapter, before any HTTP call advances the session past this exact
    # revision -- this is never a client-authored observation set.
    from ace.application.intelligence_agent_contracts import AuthorizedObservationSetV1
    from core.engine.core.intelligence_builder_observation_admission import admit_local_source_observations

    intelligence_proposed_at = (chain["connect_at"] + timedelta(seconds=10)).isoformat()
    observation_admission = await admit_local_source_observations(
        request=chain["request"],
        result=chain["result"],
        session=chain["session"],
        source_profile=chain["source_profile"],
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        user=_owner(),
        admitted_at=datetime.fromisoformat(intelligence_proposed_at),
        repository=repository,
        sessions=IntelligenceBuilderSessionService(store=store),
    )
    observations = observation_admission.observation_set
    assert isinstance(observations, AuthorizedObservationSetV1)

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_dispatching_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intelligence_propose_resp = await client.post(
            "/v1/intelligence/builds/builder/intelligence/propose",
            json={
                "current": json.loads(chain["session"].model_dump_json()),
                "connect_request": json.loads(chain["request"].model_dump_json()),
                "connect_result": json.loads(chain["result"].model_dump_json()),
                "source_profile": json.loads(chain["source_profile"].model_dump_json()),
                "concept_model": json.loads(chain["concept_model"].model_dump_json()),
                "concept_disposition": json.loads(chain["concept_disposition"].model_dump_json()),
                "user_intent": "Understand the status and value of approved source-grounded records.",
                "audience_constraints": [],
                "cadence_constraints": [],
                "proposed_at": intelligence_proposed_at,
            },
        )
        assert intelligence_propose_resp.status_code == 200, intelligence_propose_resp.text
        intelligence_propose_body = intelligence_propose_resp.json()
        assert intelligence_propose_body["contract"] == "ace.http.builder-intelligence-model-propose-result/v1alpha1"
        assert set(intelligence_propose_body) == {"contract", "proposal", "session_revision"}
        intelligence_proposed_session = intelligence_propose_body["session_revision"]
        assert intelligence_proposed_session["stage"] == OnboardingStage.INTELLIGENCE_MODEL_PROPOSED.value

        intelligence_approved_at = (chain["connect_at"] + timedelta(seconds=11)).isoformat()
        intelligence_approve_resp = await client.post(
            "/v1/intelligence/builds/builder/intelligence/approve",
            json={
                "decision": "approve",
                "current": intelligence_proposed_session,
                "proposal": intelligence_propose_body["proposal"],
                "approved_at": intelligence_approved_at,
            },
        )
        assert intelligence_approve_resp.status_code == 200, intelligence_approve_resp.text
        intelligence_approve_body = intelligence_approve_resp.json()
        assert intelligence_approve_body["contract"] == "ace.http.builder-intelligence-model-approve-result/v1alpha1"
        assert set(intelligence_approve_body) == {
            "contract",
            "reviewed_approval",
            "proposal",
            "disposition",
            "session_revision",
        }
        intelligence_approved_session = intelligence_approve_body["session_revision"]
        assert intelligence_approved_session["stage"] == OnboardingStage.INTELLIGENCE_MODEL_APPROVED.value

        first_brief_generated_at = (chain["connect_at"] + timedelta(seconds=12)).isoformat()
        first_brief_resp = await client.post(
            "/v1/intelligence/builds/builder/first-brief/prepare",
            json={
                "current": intelligence_approved_session,
                "concept_model": json.loads(chain["concept_model"].model_dump_json()),
                "concept_disposition": json.loads(chain["concept_disposition"].model_dump_json()),
                "intelligence_model": intelligence_approve_body["proposal"],
                "intelligence_disposition": intelligence_approve_body["disposition"],
                "observations": json.loads(observations.model_dump_json()),
                "generated_at": first_brief_generated_at,
            },
        )
        assert first_brief_resp.status_code == 200, first_brief_resp.text
        first_brief_body = first_brief_resp.json()
        assert first_brief_body["contract"] == "ace.http.builder-first-brief-prepare-result/v1alpha1"
        assert set(first_brief_body) == {"contract", "brief", "session_revision"}
        assert first_brief_body["session_revision"]["stage"] == OnboardingStage.FIRST_BRIEFING_READY.value


@pytest.mark.asyncio
async def test_verified_user_injection_denies_a_non_local_owner() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-wrong-owner")

    app = _app(
        claims=_owner(sub=_OTHER_ACTOR, local_owner=False),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_propose_source_scope_conflict_on_stale_session() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-stale")

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {
            "connect_request": json.loads(request.model_dump_json()),
            "connect_result": json.loads(result.model_dump_json()),
            "current": json.loads(session.model_dump_json()),
            "occurred_at": _AUTHORIZED_AT.isoformat(),
        }
        first = await client.post("/v1/intelligence/builds/builder/source/propose", json=body)
        assert first.status_code == 200

        stale = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={**body, "occurred_at": (_AUTHORIZED_AT + timedelta(seconds=30)).isoformat()},
        )
        assert stale.status_code == 409


@pytest.mark.asyncio
async def test_propose_source_scope_not_found_for_unrecorded_connect_result() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    # Deliberately never persisted, so no authorized Connect result is durably recorded.
    session = await _started_session(store, correlation_id="correlation:ws3-api-not-found")

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_propose_source_scope_unavailable_on_broken_record_storage() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-unavailable")

    raising_store = _RaisingLoadStore()
    raising_repository = LocalSourceConnectRecordRepository(raising_store)
    app = _app(
        claims=_owner(),
        store=store,
        repository=raising_repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
        connect_records=raising_store,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_approve_connect_route_performs_approval_before_connect_in_order() -> None:
    """The approve-connect route must record the source-scope approval receipt
    before it ever calls connect: the connect step is only reachable using
    that exact freshly-minted receipt reference, so a successful connect
    response is itself proof the approval ran first."""

    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-order")

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        propose_resp = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert propose_resp.status_code == 200
        propose_body = propose_resp.json()

        approve_connect_resp = await client.post(
            "/v1/intelligence/builds/builder/source/approve-connect",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "approval": {
                    "decision": "approve",
                    "current": propose_body["session_revision"],
                    "proposal": propose_body["proposal"],
                    "approved_at": (_AUTHORIZED_AT + timedelta(seconds=1)).isoformat(),
                },
            },
        )
        assert approve_connect_resp.status_code == 200
        body = approve_connect_resp.json()
        # Connect succeeded using the exact receipt the approval step minted --
        # unreachable unless approval ran strictly before connect.
        receipt_ref = body["reviewed_approval"]["approval"]["receipt_ref"]
        assert receipt_ref.startswith("approval:builder-source-scope:")
        assert body["session_revision"]["stage"] == OnboardingStage.SOURCES_READY.value


@pytest.mark.asyncio
async def test_approve_connect_route_conflict_when_no_matching_proposal_was_approved() -> None:
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-approve-conflict")

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=_SpyProvider(_concept_response),
        intelligence_provider=_SpyProvider(_intelligence_response),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        propose_resp = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "current": json.loads(session.model_dump_json()),
                "occurred_at": _AUTHORIZED_AT.isoformat(),
            },
        )
        assert propose_resp.status_code == 200
        propose_body = propose_resp.json()

        # ``current`` is deliberately the pre-proposal (stale) session revision
        # instead of the exact proposed revision, so the approval must fail closed.
        response = await client.post(
            "/v1/intelligence/builds/builder/source/approve-connect",
            json={
                "connect_request": json.loads(request.model_dump_json()),
                "connect_result": json.loads(result.model_dump_json()),
                "approval": {
                    "decision": "approve",
                    "current": json.loads(session.model_dump_json()),
                    "proposal": propose_body["proposal"],
                    "approved_at": (_AUTHORIZED_AT + timedelta(seconds=1)).isoformat(),
                },
            },
        )
        assert response.status_code == 409


@pytest.mark.asyncio
async def test_strict_request_contracts_reject_extra_fields_and_naive_times_with_422() -> None:
    """Every Builder route is ``extra=forbid`` with timezone-aware times: an
    unexpected field or a naive timestamp must be rejected at the transport
    boundary (422) before any coordinator, store, or provider is touched."""

    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    session = await _started_session(store, correlation_id="correlation:ws3-api-422")
    records_before = dict(store.records)
    concept_provider = _SpyProvider(_concept_response)
    intelligence_provider = _SpyProvider(_intelligence_response)

    app = _app(
        claims=_owner(),
        store=store,
        repository=repository,
        concept_provider=concept_provider,
        intelligence_provider=intelligence_provider,
    )

    valid = {
        "connect_request": json.loads(request.model_dump_json()),
        "connect_result": json.loads(result.model_dump_json()),
        "current": json.loads(session.model_dump_json()),
        "occurred_at": _AUTHORIZED_AT.isoformat(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        extra_field = await client.post(
            "/v1/intelligence/builds/builder/source/propose", json={**valid, "actor_ref": LOCAL_OWNER_ACTOR_REF}
        )
        assert extra_field.status_code == 422

        naive_time = await client.post(
            "/v1/intelligence/builds/builder/source/propose",
            json={**valid, "occurred_at": _AUTHORIZED_AT.replace(tzinfo=None).isoformat()},
        )
        assert naive_time.status_code == 422

        for path in (
            "/v1/intelligence/builds/builder/concept/propose",
            "/v1/intelligence/builds/builder/concept/approve",
            "/v1/intelligence/builds/builder/intelligence/propose",
            "/v1/intelligence/builds/builder/intelligence/approve",
            "/v1/intelligence/builds/builder/first-brief/prepare",
        ):
            response = await client.post(path, json={"unexpected": True})
            assert response.status_code == 422, path

    assert store.records == records_before
    assert concept_provider.calls == 0
    assert intelligence_provider.calls == 0
