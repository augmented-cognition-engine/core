"""Production-safe reviewed activation approval and resolver tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_build_plan_binding import (
    IntelligenceBuildPlanBindingService,
    IntelligenceBuildPlanBindRequestV1Alpha1,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildActivationProposalV1Alpha1,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingBlockReason, OnboardingStage
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import (
    intelligence_activation_approval_records,
    router,
)
from core.engine.core.agent_composition_runtime import GovernedStateRuntimeUseResolver
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_activation_authority import (
    IntelligenceActivationApprovalDenied,
    RecordedIntelligenceActivationAuthority,
)
from core.engine.core.intelligence_build import IntelligenceBuildHttpRuntime, intelligence_build_runtime
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_ACTOR_REF,
    LOCAL_OWNER_GRANTS,
    LOCAL_OWNER_PRODUCT_ID,
    bootstrap_local_owner_authority,
)
from tests.test_api_intelligence_build_plan import (
    _authority,
    _capability,
    _reviewed_plan,
    _ReviewedPackResolver,
)
from tests.test_api_intelligence_builds import (
    _Authority as _BuildAuthority,
)
from tests.test_api_intelligence_builds import (
    _claims as _build_claims,
)
from tests.test_api_intelligence_builds import (
    _Executor as _BuildExecutor,
)
from tests.test_api_intelligence_builds import (
    _request as _start_build_request,
)
from tests.test_local_owner_authority import InMemoryGovernedStateStore

pytestmark = pytest.mark.unit


def _owner() -> dict:
    return {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": [
            "cognition-review",
            *(spec.authority_class.value for spec in LOCAL_OWNER_GRANTS),
        ],
        "local_owner": True,
    }


async def _bound_plan(*, bound_at: datetime):
    fixture = _reviewed_plan()
    request_material = fixture.request.model_dump(mode="python", exclude={"request_id", "request_digest"})
    request_material.update(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        requested_at=bound_at - timedelta(seconds=1),
    )
    request = IntelligenceBuildPlanRequestV1Alpha2(**request_material)
    proposal_material = fixture.activation_proposal.model_dump(
        mode="python",
        exclude={"proposal_id", "proposal_digest"},
    )
    proposal_material["product_id"] = LOCAL_OWNER_PRODUCT_ID
    plan = IntelligenceBuildPlanV1Alpha3(
        request=request,
        planner_artifact=fixture.planner_artifact,
        pack_reference=fixture.pack_reference,
        activation_proposal=IntelligenceBuildActivationProposalV1Alpha1(**proposal_material),
    )
    return await IntelligenceBuildPlanBindingService(packs=_ReviewedPackResolver()).bind(
        IntelligenceBuildPlanBindRequestV1Alpha1(
            plan=plan,
            capability_bindings=(_capability(),),
            authority_bindings=(_authority(),),
            bound_at=bound_at,
        )
    )


@pytest.mark.asyncio
async def test_owner_approval_persists_exact_bound_spec_and_returns_existing_start_shape() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    body = {
        "decision": "approve",
        "bound_plan": bound.model_dump(mode="json"),
        "approved_at": approved_at.isoformat(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/intelligence/builds/approve", json=body)
        replay = await client.post("/v1/intelligence/builds/approve", json=body)

    assert first.status_code == replay.status_code == 200
    result = first.json()
    assert {key: value for key, value in first.json().items() if key != "replayed"} == {
        key: value for key, value in replay.json().items() if key != "replayed"
    }
    assert result["bound_plan_id"] == bound.bound_plan_id
    assert result["bound_plan_digest"] == bound.bound_plan_digest
    assert result["approval"]["subject_ref"] == bound.activation_spec.spec_id
    assert result["start_request"]["activation_approval_receipt_ref"] == result["approval"]["receipt_ref"]
    assert result["start_request"]["activation_approval_subject_ref"] == bound.activation_spec.spec_id
    assert result["start_request"]["authority_grant_ref"] == "authority_grant:atrium-intelligence-build"
    assert result["start_request"]["resource_authority_grant_ref"] == "authority_grant:atrium-observe-read"
    assert len(records.records) == 1


@pytest.mark.asyncio
async def test_recorded_approval_resolves_after_adapter_restart_and_fails_closed_on_cross_scope() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/approve",
            json={
                "decision": "approve",
                "bound_plan": bound.model_dump(mode="json"),
                "approved_at": approved_at.isoformat(),
            },
        )
    approval = response.json()["approval"]

    restarted = RecordedIntelligenceActivationAuthority(records=records, governed_state=governed)
    with pytest.raises(IntelligenceActivationApprovalDenied, match="not recorded"):
        await restarted.resolve_approval(
            receipt_ref="approval:not-recorded",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=str(bound.activation_spec.spec_id),
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )
    resolved = await restarted.resolve_approval(
        receipt_ref=approval["receipt_ref"],
        product_id=LOCAL_OWNER_PRODUCT_ID,
        subject_ref=str(bound.activation_spec.spec_id),
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        effective_at=approved_at + timedelta(seconds=1),
    )
    assert resolved.model_dump(mode="json") == approval

    with pytest.raises(IntelligenceActivationApprovalDenied):
        await restarted.resolve_approval(
            receipt_ref=approval["receipt_ref"],
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref="activation_spec:other",
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            effective_at=approved_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_activation_authority_reuses_current_governed_grants_without_minting_new_ones() -> None:
    approved_at = datetime.now(UTC)
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=approved_at)

    resolver = RecordedIntelligenceActivationAuthority(records=records, governed_state=governed)
    resolved = await resolver.resolve_grant(
        grant_ref="authority_grant:atrium-intelligence-build",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        authority="intelligence_build",
        effective_at=approved_at + timedelta(seconds=1),
    )

    assert resolved.grant_ref == "authority_grant:atrium-intelligence-build"
    assert resolved.product_id == LOCAL_OWNER_PRODUCT_ID
    assert resolved.authority == "intelligence_build"
    assert resolved.effective_at == approved_at + timedelta(seconds=1)
    assert len(governed.heads) == len(LOCAL_OWNER_GRANTS)


@pytest.mark.asyncio
async def test_start_maps_a_missing_recorded_approval_to_permission_denial() -> None:
    resolver = RecordedIntelligenceActivationAuthority(
        records=InMemoryImmutableRecordStore(),
        governed_state=InMemoryGovernedStateStore(),
    )
    response, _ = await _start_build_request(
        claims=_build_claims(),
        authority=_BuildAuthority(),
        executor=_BuildExecutor(),
        activation_authority=resolver,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Intelligence build denied"


@pytest.mark.asyncio
async def test_approved_request_reaches_existing_start_boundary_with_durable_owner_grants() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    claims = {
        **_owner(),
        "exp": (approved_at + timedelta(hours=1)).timestamp(),
    }
    await bootstrap_local_owner_authority(user=claims, store=governed, approved_at=approved_at)
    activation_authority = RecordedIntelligenceActivationAuthority(
        records=records,
        governed_state=governed,
    )
    runtime_use = GovernedStateRuntimeUseResolver(governed_state=governed)
    executor = _BuildExecutor()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    app.dependency_overrides[intelligence_build_runtime] = lambda: IntelligenceBuildHttpRuntime(
        records=records,
        authority=runtime_use,
        activation_authority=activation_authority,
        executor=executor,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await client.post(
            "/v1/intelligence/builds/approve",
            json={
                "decision": "approve",
                "bound_plan": bound.model_dump(mode="json"),
                "approved_at": approved_at.isoformat(),
            },
        )
        started = await client.post(
            "/v1/intelligence/builds/start",
            json=approved.json()["start_request"],
        )

    assert approved.status_code == 200
    assert started.status_code == 200, started.text
    assert started.json()["product_id"] == LOCAL_OWNER_PRODUCT_ID
    assert started.json()["actor_ref"] == LOCAL_OWNER_ACTOR_REF
    assert executor.builds[0].activation_approval.receipt_ref == approved.json()["approval"]["receipt_ref"]


@pytest.mark.asyncio
async def test_approval_rejects_foreign_owner_and_time_before_binding() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {**_owner(), "local_owner": False}
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/intelligence/builds/approve",
            json={
                "decision": "approve",
                "bound_plan": bound.model_dump(mode="json"),
                "approved_at": approved_at.isoformat(),
            },
        )
    assert denied.status_code == 403
    assert records.records == {}

    app.dependency_overrides[get_current_user] = _owner
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stale = await client.post(
            "/v1/intelligence/builds/approve",
            json={
                "decision": "approve",
                "bound_plan": bound.model_dump(mode="json"),
                "approved_at": (approved_at - timedelta(seconds=1)).isoformat(),
            },
        )
    assert stale.status_code == 409
    assert records.records == {}


@pytest.mark.asyncio
async def test_retry_endpoint_uses_exact_blocked_session_state_machine_and_rejects_replay() -> None:
    requested_at = datetime.now(UTC)
    records = InMemoryImmutableRecordStore()
    sessions = IntelligenceBuilderSessionService(store=records)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id="intelligence-build:world-retry",
        goal_ref="goal:world-change",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=requested_at - timedelta(seconds=2),
    )
    blocked = await sessions.block(
        started.revision,
        reason=OnboardingBlockReason.FAILED_CONNECTOR,
        actor_ref="agent:connection",
        safe_diagnostic="The reviewed source connection is temporarily unavailable.",
        occurred_at=requested_at - timedelta(seconds=1),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    body = {
        "current": blocked.revision.model_dump(mode="json"),
        "requested_at": requested_at.isoformat(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        retried = await client.post("/v1/intelligence/builds/retry", json=body)
        replay = await client.post("/v1/intelligence/builds/retry", json=body)

    assert retried.status_code == 200, retried.text
    assert retried.json()["stage"] == "retrying"
    assert retried.json()["resume_stage"] == "goal_selected"
    assert retried.json()["sequence"] == blocked.revision.sequence + 1
    assert replay.status_code == 409
    assert "stale" in replay.json()["detail"]


async def _approve(client: AsyncClient, *, bound, approved_at: datetime) -> dict:
    response = await client.post(
        "/v1/intelligence/builds/approve",
        json={
            "decision": "approve",
            "bound_plan": bound.model_dump(mode="json"),
            "approved_at": approved_at.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_session_associate_admits_first_goal_selected_revision_and_replays_identically() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)
        body = {
            "bound_plan": bound.model_dump(mode="json"),
            "approval_receipt_ref": approved["approval"]["receipt_ref"],
        }
        first = await client.post("/v1/intelligence/builds/session/associate", json=body)
        replay = await client.post("/v1/intelligence/builds/session/associate", json=body)

    assert first.status_code == replay.status_code == 200
    assert {key: value for key, value in first.json().items() if key != "replayed"} == {
        key: value for key, value in replay.json().items() if key != "replayed"
    }
    result = first.json()
    assert result["bound_plan_id"] == bound.bound_plan_id
    assert result["bound_plan_digest"] == bound.bound_plan_digest
    assert result["approval"]["receipt_ref"] == approved["approval"]["receipt_ref"]
    assert result["session"]["stage"] == OnboardingStage.GOAL_SELECTED.value
    assert result["session"]["correlation_id"] == bound.execution_request_id
    assert result["session"]["goal_ref"] == bound.binding_request.plan.request.outcome_id
    assert result["session"]["sequence"] == 1
    assert result["session"]["artifacts"] == []
    assert result["replayed"] is False
    assert replay.json()["replayed"] is True


@pytest.mark.asyncio
async def test_session_associate_maps_exact_correlation_and_goal_identity() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)
        associated = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": approved["approval"]["receipt_ref"],
            },
        )

    assert associated.status_code == 200, associated.text
    session = associated.json()["session"]
    assert session["correlation_id"] == bound.execution_request_id
    assert session["transition_actor_ref"] == LOCAL_OWNER_ACTOR_REF
    assert session["product_id"] == LOCAL_OWNER_PRODUCT_ID


@pytest.mark.asyncio
async def test_session_associate_resolves_recorded_approval_after_service_restart() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)

    restarted_app = FastAPI()
    restarted_app.include_router(router)
    restarted_app.dependency_overrides[get_current_user] = _owner
    restarted_app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    async with AsyncClient(transport=ASGITransport(app=restarted_app), base_url="http://test") as client:
        associated = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": approved["approval"]["receipt_ref"],
            },
        )

    assert associated.status_code == 200, associated.text
    assert associated.json()["replayed"] is False


@pytest.mark.asyncio
async def test_session_associate_fails_closed_on_crossed_receipt_and_bound_plan() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    other_bound = await _bound_plan(bound_at=approved_at + timedelta(seconds=1))
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)
        other_approved = await _approve(client, bound=other_bound, approved_at=approved_at + timedelta(seconds=1))

        missing_receipt = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": "approval:intelligence-activation:not-recorded",
            },
        )
        assert missing_receipt.status_code == 403

        crossed_receipt = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": other_approved["approval"]["receipt_ref"],
            },
        )
        assert crossed_receipt.status_code == 403

        crossed_bound_plan = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": other_bound.model_dump(mode="json"),
                "approval_receipt_ref": approved["approval"]["receipt_ref"],
            },
        )
        assert crossed_bound_plan.status_code == 403


@pytest.mark.asyncio
async def test_session_associate_denies_foreign_actor_and_product_scope() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)

    app.dependency_overrides[get_current_user] = lambda: {**_owner(), "local_owner": False}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": approved["approval"]["receipt_ref"],
            },
        )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_session_associate_admits_no_later_stage_or_artifact() -> None:
    approved_at = datetime.now(UTC)
    bound = await _bound_plan(bound_at=approved_at)
    records = InMemoryImmutableRecordStore()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        approved = await _approve(client, bound=bound, approved_at=approved_at)
        associated = await client.post(
            "/v1/intelligence/builds/session/associate",
            json={
                "bound_plan": bound.model_dump(mode="json"),
                "approval_receipt_ref": approved["approval"]["receipt_ref"],
            },
        )

    session = associated.json()["session"]
    assert session["stage"] == OnboardingStage.GOAL_SELECTED.value
    assert session["sequence"] == 1
    assert session["artifacts"] == []
    assert session["approval_receipt_ref"] is None
    assert session["prior_revision_id"] is None
    assert session["block_reason"] is None
    assert session["resume_stage"] is None
