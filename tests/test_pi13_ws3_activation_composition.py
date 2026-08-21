"""PI13 WS3 composition proof: Builder progression routes -> existing activation path -> ACTIVE.

The frozen Builder-session progression addendum (PI13 addendum 9) requires the
same durable local-owner session that the seven ``/builder/...`` routes drive
from ``GOAL_SELECTED`` to ``FIRST_BRIEFING_READY`` to then reach ``ACTIVE``
through the *existing* ``/activation-plan/prepare|approve|activate`` routes,
with no new state-machine bypass. This module proves that composition over
in-memory durable stores using the production authority resolvers
(``RecordedIntelligenceActivationAuthority``,
``RecordedDomainActivationPlanAuthority``), the real installed Personal Pack
artifact, and the selected-provider strategy ports with a deterministic
provider double. It is focused candidate evidence only: the installed-artifact
WS0 run remains the J-step gate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.domain_activation import DomainActivationAdmissionService
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import DomainActivationPlanAdmissionService
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import (
    IntelligenceBuilderActivationPlanCoordinator,
    IntelligenceBuilderActivationService,
)
from ace.application.intelligence_builder_contracts import OnboardingStage
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    preview_local_source_connect,
)
from ace.core.contracts import canonical_json
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import intelligence_activation_approval_records, router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_activation_authority import RecordedIntelligenceActivationAuthority
from core.engine.core.intelligence_builder_activation_plan import (
    IntelligenceBuilderActivationPlanRuntime,
    RecordedDomainActivationPlanAuthority,
    intelligence_builder_activation_plan_runtime,
)
from core.engine.core.intelligence_builder_concept_progression import (
    IntelligenceBuilderConceptProgressionRuntime,
    intelligence_builder_concept_progression_runtime,
)
from core.engine.core.intelligence_builder_intelligence_progression import (
    IntelligenceBuilderIntelligenceProgressionRuntime,
    intelligence_builder_intelligence_progression_runtime,
)
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_PRODUCT_ID,
    bootstrap_local_owner_authority,
)
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    local_source_connect_scope_progression_runtime,
)
from tests.test_api_intelligence_builder_progression import (
    _acquired_markdown_file,
    _build_result,
    _preview_request,
    _SpyProvider,
)
from tests.test_intelligence_builder_strategies import (
    _brief_response,
    _concept_response,
    _intelligence_response,
)
from tests.test_local_first_run_bootstrap import _bound_plan, _installed_personal_pack, _owner
from tests.test_local_owner_authority import InMemoryGovernedStateStore

pytestmark = pytest.mark.unit

_ALPHA_PAYLOAD = canonical_json({"status": "ready", "value": 42})
_BETA_PAYLOAD = canonical_json({"status": "pending", "value": 7})
_PREFIX = "/v1/intelligence/builds"


class _GovernedStore(InMemoryGovernedStateStore):
    """The in-memory governed store plus the receipt-by-revision read the plan history walk uses."""

    async def load_receipt_for_revision(self, revision_id: str, *, product_id: str):
        matches = [
            receipt
            for (scope, _), receipt in self.receipts.items()
            if scope == product_id and receipt.revision_id == revision_id
        ]
        assert len(matches) <= 1
        return matches[0] if matches else None


class _InstalledArtifactResolver:
    """The resolve_exact/load_exact port over one real installed Personal Pack artifact."""

    def __init__(self, artifact) -> None:
        self.artifact = artifact

    async def resolve_exact(self, *, reference):
        pack = self.artifact.pack
        if (
            pack.metadata.pack_id == reference.pack_id
            and pack.metadata.version == reference.pack_version
            and pack.compiled_pack_id == reference.compiled_pack_id
            and pack.pack_digest == reference.pack_digest
        ):
            return self.artifact
        return None

    async def load_exact(self, *, reference):
        artifact = await self.resolve_exact(reference=reference)
        return None if artifact is None else artifact.pack


def _dispatching_response(parsed: dict[str, Any]) -> dict[str, Any]:
    stage = parsed["stage"]
    if stage == "concept_model_proposal":
        return _concept_response(parsed)
    if stage == "intelligence_model_proposal":
        return _intelligence_response(parsed)
    if stage == "first_briefing_preview":
        return _brief_response(parsed)
    raise AssertionError(f"unexpected stage {stage}")


def _json(model) -> dict:
    return json.loads(model.model_dump_json())


async def _composition(tmp_path, *, respond=None):
    """Production-shaped runtimes over in-memory durable stores; no fabricated authority."""

    base = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=20)
    records = InMemoryImmutableRecordStore()
    governed = _GovernedStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=base - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=base)
    artifact, _ = await _installed_personal_pack(tmp_path)
    packs = _InstalledArtifactResolver(artifact)

    sessions = IntelligenceBuilderSessionService(store=records)
    spec_authority = RecordedIntelligenceActivationAuthority(records=records, governed_state=governed)
    plan_authority = RecordedDomainActivationPlanAuthority(records=records, grants=spec_authority)
    plans = DomainActivationPlanAdmissionService(store=governed, authority=plan_authority)
    activation = IntelligenceBuilderActivationService(
        sessions=sessions,
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=spec_authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=spec_authority),
        packs=packs,
    )
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=sessions, plans=plans, packs=packs, activation=activation
    )
    repository = LocalSourceConnectRecordRepository(records)
    provider = _SpyProvider(_dispatching_response if respond is None else respond)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[intelligence_activation_approval_records] = lambda: records
    app.dependency_overrides[local_source_connect_scope_progression_runtime] = lambda: (
        LocalSourceConnectScopeProgressionRuntime(records=records, repository=repository, grants=spec_authority)
    )
    app.dependency_overrides[intelligence_builder_concept_progression_runtime] = lambda: (
        IntelligenceBuilderConceptProgressionRuntime(records=records, grants=spec_authority, provider=provider)
    )
    app.dependency_overrides[intelligence_builder_intelligence_progression_runtime] = lambda: (
        IntelligenceBuilderIntelligenceProgressionRuntime(
            records=records, grants=spec_authority, repository=repository, provider=provider
        )
    )
    app.dependency_overrides[intelligence_builder_activation_plan_runtime] = lambda: (
        IntelligenceBuilderActivationPlanRuntime(records=records, coordinator=coordinator)
    )

    # One authorized, durably recorded local Connect result over two exact Markdown captures.
    authorized_at = base - timedelta(minutes=5)
    preview = preview_local_source_connect(_preview_request())
    connect_request = LocalSourceConnectAuthorizationRequest(
        preview=preview, authorized=True, authorized_at=authorized_at
    )
    connect_result = await _build_result(
        connect_request,
        (
            _acquired_markdown_file("notes/alpha.md", _ALPHA_PAYLOAD),
            _acquired_markdown_file("notes/beta.md", _BETA_PAYLOAD),
        ),
    )
    await repository.persist(connect_request, connect_result, authorized_at)

    return {
        "base": base,
        "app": app,
        "records": records,
        "sessions": sessions,
        "bound": bound,
        "provider": provider,
        "connect_request": connect_request,
        "connect_result": connect_result,
    }


def at(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat()


async def _post(client: AsyncClient, path: str, body: dict) -> dict:
    response = await client.post(f"{_PREFIX}{path}", json=body)
    assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
    return response.json()


async def _progress_to_first_briefing_ready(
    client: AsyncClient, material: dict, *, stop_before_first_brief: bool = False
) -> dict:
    """Drive /approve -> /session/associate -> the seven builder routes; return the chain."""

    base: datetime = material["base"]
    bound = material["bound"]
    connect = {
        "connect_request": _json(material["connect_request"]),
        "connect_result": _json(material["connect_result"]),
    }
    at = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()  # noqa: E731

    approved = await _post(
        client, "/approve", {"decision": "approve", "bound_plan": _json(bound), "approved_at": at(1)}
    )
    receipt_ref = approved["approval"]["receipt_ref"]

    associated = await _post(
        client, "/session/associate", {"bound_plan": _json(bound), "approval_receipt_ref": receipt_ref}
    )
    session = associated["session"]
    assert session["stage"] == OnboardingStage.GOAL_SELECTED.value
    assert session["product_id"] == LOCAL_OWNER_PRODUCT_ID

    proposed = await _post(client, "/builder/source/propose", {**connect, "current": session, "occurred_at": at(2)})
    connected = await _post(
        client,
        "/builder/source/approve-connect",
        {
            **connect,
            "approval": {
                "decision": "approve",
                "current": proposed["session_revision"],
                "proposal": proposed["proposal"],
                "approved_at": at(3),
            },
        },
    )
    assert connected["blocked_reason"] is None
    concept_proposed = await _post(
        client,
        "/builder/concept/propose",
        {
            "current": connected["session_revision"],
            "source_profile": connected["profile"],
            "user_intent": "Understand the status and value of approved source-grounded records.",
            "organization_terminology": [],
            "proposed_at": at(4),
        },
    )
    concept_approved = await _post(
        client,
        "/builder/concept/approve",
        {
            "decision": "approve",
            "current": concept_proposed["session_revision"],
            "proposal": concept_proposed["proposal"],
            "approved_at": at(5),
        },
    )
    intelligence_proposed = await _post(
        client,
        "/builder/intelligence/propose",
        {
            **connect,
            "current": concept_approved["session_revision"],
            "source_profile": connected["profile"],
            "concept_model": concept_approved["proposal"],
            "concept_disposition": concept_approved["disposition"],
            "user_intent": "Watch material status and value changes for approved source-grounded records.",
            "audience_constraints": ["Review material changes without executing decisions."],
            "cadence_constraints": ["daily"],
            "proposed_at": at(6),
        },
    )
    intelligence_approved = await _post(
        client,
        "/builder/intelligence/approve",
        {
            "decision": "approve",
            "current": intelligence_proposed["session_revision"],
            "proposal": intelligence_proposed["proposal"],
            "approved_at": at(7),
        },
    )

    # The exact admitted observation set is durable Builder material, reopened
    # from the session rather than authored by the client.
    from ace.application.intelligence_agent_contracts import AuthorizedObservationSetV1
    from ace.application.intelligence_builder_contracts import (
        IntelligenceBuilderSessionRevisionV1,
        OnboardingArtifactKind,
    )

    sessions: IntelligenceBuilderSessionService = material["sessions"]
    current = IntelligenceBuilderSessionRevisionV1.model_validate(
        intelligence_approved["session_revision"], strict=False
    )
    observation_ref = next(
        item for item in current.artifacts if item.artifact_kind is OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET
    )
    observations = await sessions.load_artifact(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        reference=observation_ref,
        artifact_type=AuthorizedObservationSetV1,
        available_at=base + timedelta(seconds=8),
    )

    if stop_before_first_brief:
        return {
            "activation_approval_receipt_ref": receipt_ref,
            "intelligence_approved_session": intelligence_approved["session_revision"],
        }

    briefing = await _post(
        client,
        "/builder/first-brief/prepare",
        {
            "current": intelligence_approved["session_revision"],
            "concept_model": concept_approved["proposal"],
            "concept_disposition": concept_approved["disposition"],
            "intelligence_model": intelligence_approved["proposal"],
            "intelligence_disposition": intelligence_approved["disposition"],
            "observations": _json(observations),
            "generated_at": at(8),
        },
    )
    assert briefing["session_revision"]["stage"] == OnboardingStage.FIRST_BRIEFING_READY.value
    return {
        "activation_approval_receipt_ref": receipt_ref,
        "spec_approved_at": approved["approval"]["approved_at"],
        "intelligence_approved_session": intelligence_approved["session_revision"],
        "briefing_ready_session": briefing["session_revision"],
    }


async def _admit_activation_plan(client: AsyncClient, material: dict, chain: dict) -> dict:
    """Drive the existing /activation-plan/prepare and /approve over the briefing-ready session."""

    base: datetime = material["base"]
    bound_json = _json(material["bound"])
    at = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()  # noqa: E731

    plan = await _post(
        client,
        "/activation-plan/prepare",
        {"current": chain["briefing_ready_session"], "bound_plan": bound_json, "requested_at": at(9)},
    )
    assert plan["onboarding_handoff"]["session_id"] == chain["briefing_ready_session"]["session_id"]
    assert plan["onboarding_handoff"]["session_revision_id"] == chain["briefing_ready_session"]["revision_id"]

    commit = await _post(
        client,
        "/activation-plan/approve",
        {
            "decision": "approve",
            "current": chain["briefing_ready_session"],
            "bound_plan": bound_json,
            "approved_at": at(10),
        },
    )
    assert commit["activation_key"] == bound_json["activation_spec"]["activation_key"]
    return commit


@pytest.mark.asyncio
async def test_activation_plan_window_is_anchored_on_the_sessions_durable_start(tmp_path) -> None:
    """The v1alpha2 plan's ``created_at`` is the session's first durable revision
    instant -- the activation-spec approval's own ``approved_at`` that
    ``/session/associate`` started the session at -- so both the spec approval
    and the plan's later approval lie inside ``[created_at, occurred_at]`` by
    construction. No client value sets it and no approval is re-minted."""

    material = await _composition(tmp_path)
    base: datetime = material["base"]
    bound_json = _json(material["bound"])

    async with AsyncClient(transport=ASGITransport(app=material["app"]), base_url="http://test") as client:
        chain = await _progress_to_first_briefing_ready(client, material)
        plan = await _post(
            client,
            "/activation-plan/prepare",
            {"current": chain["briefing_ready_session"], "bound_plan": bound_json, "requested_at": at(base, 9)},
        )
        preview_again = await _post(
            client,
            "/activation-plan/prepare",
            {"current": chain["briefing_ready_session"], "bound_plan": bound_json, "requested_at": at(base, 30)},
        )

    sessions: IntelligenceBuilderSessionService = material["sessions"]
    first = await sessions.load_first(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session_id=chain["briefing_ready_session"]["session_id"],
        available_at=base + timedelta(seconds=31),
    )
    assert first is not None and first.sequence == 1
    spec_approved_at = datetime.fromisoformat(chain["spec_approved_at"])
    assert first.occurred_at == spec_approved_at
    assert datetime.fromisoformat(plan["created_at"]) == spec_approved_at
    # The preview is a pure function of durable material: a later request time
    # neither moves the window start nor changes the plan identity.
    assert preview_again["created_at"] == plan["created_at"]
    assert preview_again["plan_id"] == plan["plan_id"]
    assert preview_again["plan_digest"] == plan["plan_digest"]


@pytest.mark.asyncio
async def test_progressed_session_reaches_active_through_the_existing_activation_plan_routes(tmp_path) -> None:
    material = await _composition(tmp_path)
    base: datetime = material["base"]
    bound_json = _json(material["bound"])
    at = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()  # noqa: E731

    async with AsyncClient(transport=ASGITransport(app=material["app"]), base_url="http://test") as client:
        chain = await _progress_to_first_briefing_ready(client, material)
        await _admit_activation_plan(client, material, chain)

        activated = await _post(
            client,
            "/activation-plan/activate",
            {
                "bound_plan": bound_json,
                "activation_approval_receipt_ref": chain["activation_approval_receipt_ref"],
                "requested_at": at(11),
            },
        )
        assert activated["replayed"] is False
        assert activated["receipt"]["session_id"] == chain["briefing_ready_session"]["session_id"]

        replayed = await _post(
            client,
            "/activation-plan/activate",
            {
                "bound_plan": bound_json,
                "activation_approval_receipt_ref": chain["activation_approval_receipt_ref"],
                "requested_at": at(12),
            },
        )
        assert replayed["replayed"] is True
        assert replayed["receipt"] == activated["receipt"]

    sessions: IntelligenceBuilderSessionService = material["sessions"]
    current = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session_id=chain["briefing_ready_session"]["session_id"],
        available_at=base + timedelta(seconds=13),
    )
    assert current is not None
    assert current.stage is OnboardingStage.ACTIVE
    assert current.approval_receipt_ref == chain["activation_approval_receipt_ref"]
    assert material["provider"].calls == 3


@pytest.mark.asyncio
async def test_activation_plan_fails_closed_before_the_session_is_briefing_ready(tmp_path) -> None:
    """The existing state machine is not bypassed: while the durable session is
    only ``INTELLIGENCE_MODEL_APPROVED`` (no first Brief yet), the activation
    plan cannot be prepared or approved, and no provider call is spent."""

    material = await _composition(tmp_path)
    base: datetime = material["base"]
    bound_json = _json(material["bound"])

    async with AsyncClient(transport=ASGITransport(app=material["app"]), base_url="http://test") as client:
        chain = await _progress_to_first_briefing_ready(client, material, stop_before_first_brief=True)
        calls_before = material["provider"].calls
        prepared = await client.post(
            f"{_PREFIX}/activation-plan/prepare",
            json={
                "current": chain["intelligence_approved_session"],
                "bound_plan": bound_json,
                "requested_at": (base + timedelta(seconds=20)).isoformat(),
            },
        )
        approved = await client.post(
            f"{_PREFIX}/activation-plan/approve",
            json={
                "decision": "approve",
                "current": chain["intelligence_approved_session"],
                "bound_plan": bound_json,
                "approved_at": (base + timedelta(seconds=21)).isoformat(),
            },
        )

    assert prepared.status_code == 409, prepared.text
    assert "briefing-ready" in prepared.json()["detail"]
    assert approved.status_code == 409, approved.text
    assert material["provider"].calls == calls_before

    sessions: IntelligenceBuilderSessionService = material["sessions"]
    current = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session_id=chain["intelligence_approved_session"]["session_id"],
        available_at=base + timedelta(seconds=22),
    )
    assert current is not None
    assert current.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
