"""HTTP boundary and host-composition proof for the FIRST_BRIEFING_READY-to-canonical-activation seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.domain_activation import CommittedActivationBinding
from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    AuthorizedIntelligenceBuild,
    IntelligenceBuildStartV1,
    ProductScopedImmutableRecordStore,
)
from ace.application.intelligence_build_host import (
    DurableIntelligenceBuildHostComposer,
    IntelligenceBuildHostCompositionError,
)
from ace.application.intelligence_builder_activation import (
    DomainActivationPlanNotAdmittedError,
    IntelligenceBuilderActivationError,
)
from ace.application.intelligence_builder_contracts import IntelligenceBuilderSessionRevisionV1
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_builder_activation_plan import (
    IntelligenceBuilderActivationPlanRuntime,
    intelligence_builder_activation_plan_runtime,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_GRANTS, LOCAL_OWNER_PRODUCT_ID
from tests.intelligence.test_domain_activation_plan_admission import _activation_material
from tests.intelligence.test_intelligence_builder_activation_plan_coordinator import (
    ACTOR_REF,
    _ConformancePackResolver,
    _stack,
)
from tests.test_api_intelligence_build_resource_state import _bound_plan
from tests.test_intelligence_build_host_composition import _Resources, _RuntimeUse

pytestmark = pytest.mark.unit


def _owner_claims() -> dict:
    return {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["cognition-review", *(spec.authority_class.value for spec in LOCAL_OWNER_GRANTS)],
        "local_owner": True,
    }


def _owned_session(session: IntelligenceBuilderSessionRevisionV1) -> IntelligenceBuilderSessionRevisionV1:
    """Same exact material, re-scoped to the fixed local-owner product for gating tests.

    The underlying durable store still partitions by the fixture's own
    product, so this is only valid against a *fake* coordinator double --
    the real coordinator's own product/session-consistency behavior is
    already proven in ``test_intelligence_builder_activation_plan_coordinator``.
    """

    data = session.model_dump(mode="python")
    data.update(product_id=LOCAL_OWNER_PRODUCT_ID, revision_id=None, revision_digest=None)
    return IntelligenceBuilderSessionRevisionV1.model_validate(data)


_FAKE_SESSION_STARTED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class _FakeSessions:
    """The durable session port the host consults for the plan window start."""

    def __init__(self, first_revision) -> None:
        self.first_revision = first_revision
        self.load_first_calls: list[dict] = []

    async def load_first(self, **kwargs):
        self.load_first_calls.append(kwargs)
        return self.first_revision


class _FakeCoordinator:
    def __init__(self, *, first_revision=...) -> None:
        if first_revision is ...:
            # The host reads only the first durable revision's ``occurred_at``.
            first_revision = SimpleNamespace(sequence=1, occurred_at=_FAKE_SESSION_STARTED_AT)
        self.sessions = _FakeSessions(first_revision)
        self.prepare_calls: list[dict] = []
        self.admit_calls: list[dict] = []
        self.activate_calls: list[dict] = []
        self.prepare_result = None
        self.admit_result = None
        self.activate_result = None
        self.prepare_error: Exception | None = None
        self.admit_error: Exception | None = None
        self.activate_error: Exception | None = None

    async def prepare(self, **kwargs):
        self.prepare_calls.append(kwargs)
        if self.prepare_error is not None:
            raise self.prepare_error
        return self.prepare_result

    async def admit(self, **kwargs):
        self.admit_calls.append(kwargs)
        if self.admit_error is not None:
            raise self.admit_error
        return self.admit_result

    async def activate(self, **kwargs):
        self.activate_calls.append(kwargs)
        if self.activate_error is not None:
            raise self.activate_error
        return self.activate_result


def _app(*, coordinator, claims: dict, records=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_builder_activation_plan_runtime] = lambda: (
        IntelligenceBuilderActivationPlanRuntime(
            records=records or InMemoryImmutableRecordStore(),
            coordinator=coordinator,
        )
    )
    return app


async def _owned_material():
    material = await _stack()
    session = _owned_session(material["session"])
    owned_spec = _activation_material(product_id=LOCAL_OWNER_PRODUCT_ID)[2]
    bound_plan = _bound_plan(product_id=LOCAL_OWNER_PRODUCT_ID, actor_ref=LOCAL_OWNER_ACTOR_REF, spec=owned_spec)
    return material, session, bound_plan


@pytest.mark.asyncio
async def test_activation_plan_routes_deny_a_non_local_owner() -> None:
    material, session, bound_plan = await _owned_material()
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, claims={**_owner_claims(), "local_owner": False})
    requested_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        prepared = await client.post(
            "/v1/intelligence/builds/activation-plan/prepare",
            json={
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "requested_at": requested_at.isoformat(),
            },
        )
        approved = await client.post(
            "/v1/intelligence/builds/activation-plan/approve",
            json={
                "decision": "approve",
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "approved_at": requested_at.isoformat(),
            },
        )
        activated = await client.post(
            "/v1/intelligence/builds/activation-plan/activate",
            json={
                "bound_plan": bound_plan.model_dump(mode="json"),
                "activation_approval_receipt_ref": "approval:canonical-spec",
                "requested_at": requested_at.isoformat(),
            },
        )

    assert prepared.status_code == approved.status_code == activated.status_code == 403
    assert coordinator.prepare_calls == coordinator.admit_calls == coordinator.activate_calls == []


@pytest.mark.asyncio
async def test_activation_plan_routes_deny_bound_material_crossing_the_fixed_owner_scope() -> None:
    material = await _stack()  # fixture-scoped, not the fixed local-owner product/actor
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, claims=_owner_claims())
    requested_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        prepared = await client.post(
            "/v1/intelligence/builds/activation-plan/prepare",
            json={
                "current": material["session"].model_dump(mode="json"),
                "bound_plan": material["bound_plan"].model_dump(mode="json"),
                "requested_at": requested_at.isoformat(),
            },
        )
        activated = await client.post(
            "/v1/intelligence/builds/activation-plan/activate",
            json={
                "bound_plan": material["bound_plan"].model_dump(mode="json"),
                "activation_approval_receipt_ref": "approval:canonical-spec",
                "requested_at": requested_at.isoformat(),
            },
        )

    assert prepared.status_code == 403
    assert activated.status_code == 403
    assert coordinator.prepare_calls == coordinator.activate_calls == []


@pytest.mark.asyncio
async def test_prepare_returns_the_coordinators_exact_plan_for_the_verified_owner() -> None:
    material, session, bound_plan = await _owned_material()
    plan = await material["coordinator"].prepare(
        product_id=material["session"].product_id,
        session_id=material["session"].session_id,
        bound=material["bound_plan"],
        created_at=material["session"].occurred_at + timedelta(seconds=1),
    )
    coordinator = _FakeCoordinator()
    coordinator.prepare_result = plan
    app = _app(coordinator=coordinator, claims=_owner_claims())
    requested_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/activation-plan/prepare",
            json={
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "requested_at": requested_at.isoformat(),
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["plan_id"] == plan.plan_id
    assert len(coordinator.prepare_calls) == 1
    assert coordinator.prepare_calls[0]["session_id"] == session.session_id
    # The plan window starts at the session's durable first revision, never at
    # a client-supplied time; the request time is only the durable read instant.
    assert coordinator.prepare_calls[0]["created_at"] == _FAKE_SESSION_STARTED_AT
    assert coordinator.prepare_calls[0]["evaluated_at"] == requested_at
    assert coordinator.sessions.load_first_calls[0]["session_id"] == session.session_id


@pytest.mark.asyncio
async def test_prepare_and_approve_map_a_missing_durable_session_to_404() -> None:
    material, session, bound_plan = await _owned_material()
    coordinator = _FakeCoordinator(first_revision=None)
    app = _app(coordinator=coordinator, claims=_owner_claims())
    now = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        prepared = await client.post(
            "/v1/intelligence/builds/activation-plan/prepare",
            json={
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "requested_at": now.isoformat(),
            },
        )
        approved = await client.post(
            "/v1/intelligence/builds/activation-plan/approve",
            json={
                "decision": "approve",
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "approved_at": now.isoformat(),
            },
        )

    assert prepared.status_code == 404, prepared.text
    assert approved.status_code == 404, approved.text
    assert coordinator.prepare_calls == []
    assert coordinator.admit_calls == []


@pytest.mark.asyncio
async def test_approve_maps_a_stale_plan_conflict_to_409() -> None:
    material, session, bound_plan = await _owned_material()
    plan = await material["coordinator"].prepare(
        product_id=material["session"].product_id,
        session_id=material["session"].session_id,
        bound=material["bound_plan"],
        created_at=material["session"].occurred_at + timedelta(seconds=1),
    )
    coordinator = _FakeCoordinator()
    coordinator.prepare_result = plan
    coordinator.admit_error = IntelligenceBuilderActivationError(
        "activation plan is already admitted with different exact material"
    )
    app = _app(coordinator=coordinator, claims=_owner_claims())
    approved_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/activation-plan/approve",
            json={
                "decision": "approve",
                "current": session.model_dump(mode="json"),
                "bound_plan": bound_plan.model_dump(mode="json"),
                "approved_at": approved_at.isoformat(),
            },
        )

    assert response.status_code == 409, response.text
    assert len(coordinator.admit_calls) == 1


@pytest.mark.asyncio
async def test_activate_maps_not_yet_admitted_to_404() -> None:
    _, _, bound_plan = await _owned_material()
    coordinator = _FakeCoordinator()
    coordinator.activate_error = DomainActivationPlanNotAdmittedError(
        "the v1alpha2 activation plan has not yet been separately approved and admitted"
    )
    app = _app(coordinator=coordinator, claims=_owner_claims())
    requested_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/activation-plan/activate",
            json={
                "bound_plan": bound_plan.model_dump(mode="json"),
                "activation_approval_receipt_ref": "approval:canonical-spec",
                "requested_at": requested_at.isoformat(),
            },
        )

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_activate_returns_the_exact_receipt_and_replay_flag() -> None:
    material, session, bound_plan = await _owned_material()
    created_at = material["session"].occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    await material["coordinator"].admit(
        product_id=material["session"].product_id,
        session_id=material["session"].session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )
    outcome = await material["coordinator"].activate(
        product_id=material["session"].product_id,
        bound=material["bound_plan"],
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=committed_at + timedelta(seconds=1),
    )
    coordinator = _FakeCoordinator()
    coordinator.activate_result = outcome
    app = _app(coordinator=coordinator, claims=_owner_claims())
    requested_at = datetime.now(UTC)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/builds/activation-plan/activate",
            json={
                "bound_plan": bound_plan.model_dump(mode="json"),
                "activation_approval_receipt_ref": "approval:canonical-spec",
                "requested_at": requested_at.isoformat(),
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replayed"] is False
    assert body["receipt"]["session_id"] == outcome.receipt_artifact.session_id
    assert body["receipt"]["canonical_commit_receipt_id"] == outcome.receipt_artifact.canonical_commit_receipt_id


def test_activation_plan_routes_expose_stable_public_contracts() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    for path in (
        "/v1/intelligence/builds/activation-plan/prepare",
        "/v1/intelligence/builds/activation-plan/approve",
        "/v1/intelligence/builds/activation-plan/activate",
    ):
        assert "post" in paths[path]


def _build(active) -> AuthorizedIntelligenceBuild:
    evaluated_at = active.receipt_artifact.activated_at + timedelta(minutes=1)
    product_id = active.binding.prepared_binding.reference.product_id
    actor_ref = active.binding.commit_receipt.actor_ref
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        authentication_receipt_ref="authentication_receipt:activation-plan-coordinator",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=evaluated_at - timedelta(minutes=2),
        expires_at=evaluated_at + timedelta(hours=1),
    )
    request = IntelligenceBuildStartV1(
        authority_grant_ref="authority_grant:activation-plan-coordinator",
        resource_authority_grant_ref="authority_grant:activation-plan-coordinator-read",
        activation_approval_receipt_ref=str(active.binding.commit_receipt.approval.receipt_ref),
        activation_approval_subject_ref=str(active.binding.prepared_binding.revision.spec.spec_id),
        client_request_id="atrium_request:activation-plan-coordinator",
        profile_id="intelligence_onboarding_profile:activation-plan-coordinator",
        subject="Track this exact activated subject for meaningful material changes.",
        outcome_id="decision_readiness",
        source_group_ids=(),
        recorded_source_refs=(),
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=evaluated_at - timedelta(seconds=1),
    )
    build_id = "intelligence_build:activation-plan-coordinator"
    request_digest = "sha256:" + "2" * 64
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        authenticated_context=context,
        use_subject_ref=build_id,
        use_subject_digest=request_digest,
        operation="start_intelligence_build",
        authority="intelligence_build",
        grant_ref=request.authority_grant_ref,
        grant_hash="3" * 64,
        evaluated_at=evaluated_at,
        expires_at=evaluated_at + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=product_id,
            state_id=request.authority_grant_ref,
            sequence=1,
            revision_id="authority_grant_revision:activation-plan-coordinator",
            commit_receipt_id="governed_state_commit:activation-plan-coordinator",
        ),
    )
    return AuthorizedIntelligenceBuild(
        build_id=build_id,
        request_digest=request_digest,
        product_id=product_id,
        actor_ref=actor_ref,
        request=request,
        authority_use=authority_use,
        activation_approval=active.binding.commit_receipt.approval,
    )


@pytest.mark.asyncio
async def test_slash_start_host_composition_consumes_the_coordinators_durable_chain_and_rejects_a_different_bound_execution() -> (
    None
):
    material = await _stack()
    coordinator = material["coordinator"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )
    active = await coordinator.activate(
        product_id=session.product_id,
        bound=material["bound_plan"],
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=committed_at + timedelta(seconds=1),
    )
    assert isinstance(active.binding, CommittedActivationBinding)

    build = _build(active)
    composer = DurableIntelligenceBuildHostComposer(
        governed_state=material["governed"],
        runtime_use=_RuntimeUse(),
        packs=_ConformancePackResolver(pack=material["pack"], conformance=material["conformance"]),
    )
    scoped = ProductScopedImmutableRecordStore(product_id=build.product_id, store=material["records"])

    services = await composer.compose(
        build=build,
        records=scoped,
        resources=_Resources(),
        activation_authority=material["activation"].plans.authority,
    )
    assert services.recorded_sources is not None
    assert services.recorded_sources.binding == active.binding

    forged_build = AuthorizedIntelligenceBuild(
        build_id=build.build_id,
        request_digest=build.request_digest,
        product_id=build.product_id,
        actor_ref=build.actor_ref,
        request=build.request,
        authority_use=build.authority_use,
        activation_approval=build.activation_approval.model_copy(
            update={"receipt_ref": "approval:a-different-execution"}
        ),
    )
    with pytest.raises(IntelligenceBuildHostCompositionError):
        await composer.compose(
            build=forged_build,
            records=scoped,
            resources=_Resources(),
            activation_authority=material["activation"].plans.authority,
        )
