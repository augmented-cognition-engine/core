from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.domain_activation import DomainActivationAdmissionService
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import (
    DomainActivationPlanAdmissionService,
    prepare_activation_onboarding_handoff,
)
from ace.application.domain_activation_plan_contracts import ActivationPlanAction
from ace.application.intelligence_build_host import DurableIntelligenceBuildHostComposer
from ace.application.intelligence_build_plan_binding import (
    BoundIntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanBindRequestV1Alpha1,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildActivationProposalV1Alpha1,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import IntelligenceBuilderActivationService
from ace.application.intelligence_system_projection import DOMAIN_HEALTH_RESOURCE_KINDS
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.system_projection import IntelligenceSystemProjectionV1Alpha1, ProjectionMode
from ace.testing import InMemoryImmutableRecordStore
from ace.testing.watch_brief import exercise_watch_brief_restart
from core.engine.api.intelligence_builds import router
from core.engine.core.agent_composition_runtime import GovernedCompositionAuthorityError
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_activation_authority import (
    INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION,
    INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
    INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
    RecordedIntelligenceActivationAuthority,
    _artifact_for,
)
from core.engine.core.intelligence_build_plan import IntelligenceBuildPlanHttpRuntime
from core.engine.core.intelligence_build_resource_state import (
    IntelligenceBuildResourceStateRequestV1,
    IntelligenceBuildResourceStateRuntime,
    intelligence_build_resource_state_runtime,
    project_intelligence_build_resource_state,
)
from core.engine.core.intelligence_resource_plane import IntelligenceResourceHttpRuntime
from tests.intelligence.test_domain_activation_plan_admission import (
    _activation_material,
    _MemoryStore,
    _plan,
    _revision,
)
from tests.intelligence.test_domain_activation_plan_admission import (
    _Authority as _ActivationAuthority,
)
from tests.test_api_intelligence_build_plan import INSTALLED_PROFILE, PLANNER_ARTIFACT, PROFILE

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
ACTIVATION_KEY = "personal_intelligence"


class _ResourceAuthority:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        if self.deny:
            raise GovernedCompositionAuthorityError("inactive grant")
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="b" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=kwargs["context"].product_id,
                state_id=kwargs["grant_ref"],
                sequence=1,
                revision_id="authority_revision:resource-state",
                commit_receipt_id="authority_receipt:resource-state",
            ),
        )


class _NoRuntimeUse:
    async def resolve_authority_use(self, **_kwargs):
        raise AssertionError("resolve_active_binding must not spend a runtime authority use")


class _BuildPlanPackArtifact:
    def __init__(self, pack) -> None:
        self.pack = pack


class _BuildPlanPackResolver:
    """The InstalledCompiledPackArtifactResolver-shaped port `project_intelligence_build_plan` uses."""

    def __init__(self, pack) -> None:
        self.pack = pack
        self.reference = CompiledPackRefV1(
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            compiled_pack_id=pack.compiled_pack_id,
            pack_digest=pack.pack_digest,
        )

    async def resolve_exact(self, *, reference):
        return _BuildPlanPackArtifact(self.pack) if reference == self.reference else None


class _CanonicalPackResolver:
    """The ExactCompiledPackResolver-shaped port DurableIntelligenceBuildHostComposer uses."""

    def __init__(self, pack) -> None:
        self.pack = pack

    async def load_exact(self, *, reference):
        if (
            self.pack.metadata.pack_id == reference.pack_id
            and self.pack.metadata.version == reference.pack_version
            and self.pack.compiled_pack_id == reference.compiled_pack_id
            and self.pack.pack_digest == reference.pack_digest
        ):
            return self.pack
        return None


class _FixturePlanner:
    def __init__(self, *, profile_id: str, pack_reference: CompiledPackRefV1) -> None:
        self.profile_id = profile_id
        self.pack_reference = pack_reference
        self.artifact_identity = PLANNER_ARTIFACT


class _PlannerResolution:
    def __init__(self, planner) -> None:
        self.planner = planner

    def resolve(self, profile_id):
        return self.planner if profile_id == self.planner.profile_id else None


def _claims(*, product_id: str, actor_ref: str) -> dict:
    return {
        "sub": actor_ref,
        "product": product_id,
        "authorities": ["observe_read"],
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _bound_plan(*, product_id: str, actor_ref: str, spec) -> BoundIntelligenceBuildPlanV1Alpha1:
    pack_reference = CompiledPackRefV1(
        pack_id=spec.pack.pack_id,
        pack_version=spec.pack.pack_version,
        compiled_pack_id=spec.pack.compiled_pack_id,
        pack_digest=spec.pack.pack_digest,
    )
    request = IntelligenceBuildPlanRequestV1Alpha2(
        product_id=product_id,
        actor_ref=actor_ref,
        client_request_id="atrium-request:resource-state",
        profile_id=PROFILE.profile_id,
        profile_digest=PROFILE.profile_digest,
        subject="Keep me ahead of meaningful changes in artificial intelligence.",
        outcome_id="decision_readiness",
        source_group_ids=(),
        cadence_id="daily",
        proposed_effects=(
            "connect_sources",
            "map_concepts",
            "activate_watch",
            "create_first_brief",
        ),
        requested_at=NOW,
    )
    plan = IntelligenceBuildPlanV1Alpha3(
        request=request,
        planner_artifact=PLANNER_ARTIFACT,
        pack_reference=pack_reference,
        activation_proposal=IntelligenceBuildActivationProposalV1Alpha1(
            product_id=product_id,
            activation_key=spec.activation_key,
            pack=pack_reference,
            overlay=spec.overlay,
            capability_requirement_ids=tuple(item.requirement_id for item in spec.capability_bindings),
            authority_request_ids=tuple(item.request_id for item in spec.authority_bindings),
        ),
        recorded_source_selections=(),
    )
    return BoundIntelligenceBuildPlanV1Alpha1(
        binding_request=IntelligenceBuildPlanBindRequestV1Alpha1(
            plan=plan,
            capability_bindings=spec.capability_bindings,
            authority_bindings=spec.authority_bindings,
            bound_at=NOW,
        ),
        activation_spec=spec,
    )


async def _persist_approval(
    *,
    records: InMemoryImmutableRecordStore,
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1,
    product_id: str,
    actor_ref: str,
    approved_at: datetime,
) -> str:
    """Durably record the approval `RecordedIntelligenceActivationAuthority` reads.

    Reuses the exact production artifact/receipt derivation
    (``_artifact_for``) and the exact production persistence shape
    (``approve_intelligence_activation``'s own ``records.append`` call) —
    just without going through that endpoint's local-owner-only caller gate,
    which is an unrelated authorization concern from the association this
    test proves.
    """

    artifact = _artifact_for(
        bound=bound_plan,
        actor_ref=actor_ref,
        product_id=product_id,
        approved_at=approved_at,
    )
    approval = artifact.approval
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
        record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
        record_key=approval.receipt_ref,
        payload_contract=artifact.contract,
        payload=artifact.model_dump(mode="python"),
        as_of=approval.approved_at,
        available_at=approval.approved_at,
        processing_order=0,
    )
    await records.append(
        AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
            transaction_key=approval.receipt_ref,
            records=(record,),
            submitted_at=approval.approved_at,
        )
    )
    assert artifact.contract == INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION
    return str(approval.receipt_ref)


def _runtime(
    *,
    records: InMemoryImmutableRecordStore,
    governed_store,
    pack,
    resource_authority: _ResourceAuthority | None = None,
    activation_authority=None,
) -> IntelligenceBuildResourceStateRuntime:
    return IntelligenceBuildResourceStateRuntime(
        records=records,
        governed_state=governed_store,
        activation_authority=activation_authority
        or RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_store),
        build_plan=IntelligenceBuildPlanHttpRuntime(
            profiles=(INSTALLED_PROFILE,),
            packs=_BuildPlanPackResolver(pack),
            planners=_PlannerResolution(
                _FixturePlanner(profile_id=PROFILE.profile_id, pack_reference=_BuildPlanPackResolver(pack).reference)
            ),
        ),
        resources=IntelligenceResourceHttpRuntime(
            records=records, authority=resource_authority or _ResourceAuthority()
        ),
        composer=DurableIntelligenceBuildHostComposer(
            governed_state=governed_store,
            runtime_use=_NoRuntimeUse(),
            packs=_CanonicalPackResolver(pack),
        ),
    )


def _selector(*, cursor=None) -> dict:
    return {
        "authority_grant_ref": "authority_grant:resource-state-read",
        "resource_kinds": [item.value for item in DOMAIN_HEALTH_RESOURCE_KINDS],
        "subject_refs": [],
        "as_of": NOW.isoformat(),
        "available_at": NOW.isoformat(),
        "page_size": 50,
        "cursor": cursor,
    }


async def _post(
    *,
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1,
    approval_receipt_ref: str,
    runtime: IntelligenceBuildResourceStateRuntime,
    claims: dict,
    selector: dict | None = None,
):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_build_resource_state_runtime] = lambda: runtime
    body = {
        "bound_plan": bound_plan.model_dump(mode="json"),
        "activation_approval_receipt_ref": approval_receipt_ref,
        "selector": selector or _selector(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/intelligence/builds/projection/resource-state", json=body)


async def _live_material():
    """Build the actual accepted current path end to end: prepare -> bind ->
    approve -> the same durable Builder activation bootstrap
    `DurableIntelligenceBuildHostComposer`/`test_intelligence_build_host_composition`
    exercise for the real `/start` path, except the durable approval receipt
    this test persists (and the real `/approve` HTTP boundary would persist,
    were it not gated to the fixed local-owner identity) is computed and
    recorded *before* `.activate()` is called, so the durably ACTIVE Builder
    session's own `approval_receipt_ref` matches it exactly — proving the
    endpoint's independent re-resolution against the real artifact chain.
    """

    records = InMemoryImmutableRecordStore()
    watch = await exercise_watch_brief_restart(store=records)
    session = watch.briefing.session.revision
    handoff = prepare_activation_onboarding_handoff(
        session=session,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    pack, conformance, spec = _activation_material(product_id=session.product_id, activation_key=ACTIVATION_KEY)
    created = session.occurred_at + timedelta(seconds=1)
    activation_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
        handoff=handoff,
    )
    activation_revision = _revision(plan=activation_plan, revision=1, occurred_at=created + timedelta(seconds=2))
    governed_authority = _ActivationAuthority(approved_at=created + timedelta(seconds=1))
    governed = _MemoryStore()
    plans = DomainActivationPlanAdmissionService(store=governed, authority=governed_authority)
    committed_plan = await plans.admit(
        activation_revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=activation_revision.occurred_at + timedelta(seconds=1),
        session=session,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    activation = IntelligenceBuilderActivationService(
        sessions=IntelligenceBuilderSessionService(store=records),
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=governed_authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=governed_authority),
        packs=_CanonicalPackResolver(pack),
    )
    recorded = await activation.record_current_plan(
        product_id=session.product_id,
        session_id=session.session_id,
        committed=committed_plan,
        pack=spec.pack,
        recorded_at=activation_revision.occurred_at + timedelta(seconds=2),
    )

    product_id = session.product_id
    actor_ref = activation_revision.actor_ref
    bound_plan = _bound_plan(product_id=product_id, actor_ref=actor_ref, spec=spec)
    approval_receipt_ref = await _persist_approval(
        records=records,
        bound_plan=bound_plan,
        product_id=product_id,
        actor_ref=actor_ref,
        approved_at=activation_revision.occurred_at + timedelta(seconds=3),
    )
    active = await activation.activate(
        product_id=session.product_id,
        session_id=recorded.session.revision.session_id,
        activation_approval_receipt_ref=approval_receipt_ref,
        evaluated_at=activation_revision.occurred_at + timedelta(seconds=4),
    )
    assert active.binding.commit_receipt.actor_ref == actor_ref

    claims = _claims(product_id=product_id, actor_ref=actor_ref)
    # Real durable-not-found approval reads (RecordedIntelligenceActivationAuthority)
    # for tests that never need to reach a genuine live match.
    runtime = _runtime(records=records, governed_store=governed, pack=pack)
    # The exact same resolver instance that committed the canonical activation's
    # own approval, reused for the endpoint's independent re-resolution call, so
    # `committed.commit_receipt.approval == activation_approval` holds by the same
    # deterministic construction `test_intelligence_build_host_composition` relies
    # on — proving the real Builder-artifact/canonical-activation bootstrap chain
    # end to end without standing up a second durable authority-grant store.
    live_runtime = _runtime(
        records=records,
        governed_store=governed,
        pack=pack,
        activation_authority=governed_authority,
    )
    return {
        "records": records,
        "governed": governed,
        "pack": pack,
        "active": active,
        "bound_plan": bound_plan,
        "approval_receipt_ref": approval_receipt_ref,
        "product_id": product_id,
        "actor_ref": actor_ref,
        "claims": claims,
        "runtime": runtime,
        "live_runtime": live_runtime,
        "activation_authority": governed_authority,
    }


@pytest.mark.asyncio
async def test_resource_state_returns_live_mode_matching_the_canonical_activation() -> None:
    material = await _live_material()

    response = await _post(
        bound_plan=material["bound_plan"],
        approval_receipt_ref=material["approval_receipt_ref"],
        runtime=material["live_runtime"],
        claims=material["claims"],
    )

    assert response.status_code == 200, response.text
    projection = IntelligenceSystemProjectionV1Alpha1.model_validate_json(response.content)
    assert projection.mode is ProjectionMode.LIVE
    live_reference = material["active"].binding.prepared_binding.reference
    assert projection.activation_revision == live_reference


@pytest.mark.asyncio
async def test_resource_state_rejects_crossed_product_or_actor() -> None:
    material = await _live_material()
    foreign_claims = _claims(product_id=material["product_id"], actor_ref="principal:someone-else")

    response = await _post(
        bound_plan=material["bound_plan"],
        approval_receipt_ref=material["approval_receipt_ref"],
        runtime=material["runtime"],
        claims=foreign_claims,
    )

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_resource_state_stays_proposed_for_an_unapproved_bound_plan() -> None:
    material = await _live_material()

    response = await _post(
        bound_plan=material["bound_plan"],
        approval_receipt_ref="approval:intelligence-activation:" + "0" * 32,
        runtime=material["runtime"],
        claims=material["claims"],
    )

    assert response.status_code == 200, response.text
    projection = IntelligenceSystemProjectionV1Alpha1.model_validate_json(response.content)
    assert projection.mode is ProjectionMode.PROPOSED
    assert projection.activation_revision is None


@pytest.mark.asyncio
async def test_resource_state_rejects_a_forged_unpersisted_approval_subject() -> None:
    material = await _live_material()
    spec = material["active"].binding.prepared_binding.revision.spec
    forged_overlay = spec.overlay.model_copy(
        update={"version": "9.9.9", "compiled_overlay_id": None, "overlay_digest": None}
    )
    forged_overlay = type(spec.overlay).model_validate(forged_overlay.model_dump(mode="python"))
    forged_spec = spec.model_copy(update={"overlay": forged_overlay, "spec_id": None, "spec_hash": None})
    forged_spec = type(spec).model_validate(forged_spec.model_dump(mode="python"))
    assert forged_spec.spec_id != spec.spec_id
    assert forged_spec.activation_key == spec.activation_key
    forged_bound_plan = _bound_plan(
        product_id=material["product_id"],
        actor_ref=material["actor_ref"],
        spec=forged_spec,
    )
    # A different valid plan can still get a durable approval receipt of its
    # own — approval alone proves an owner decision, not durable activation.
    forged_approval_ref = await _persist_approval(
        records=material["records"],
        bound_plan=forged_bound_plan,
        product_id=material["product_id"],
        actor_ref=material["actor_ref"],
        approved_at=material["active"].receipt_artifact.activated_at + timedelta(seconds=2),
    )

    response = await _post(
        bound_plan=forged_bound_plan,
        approval_receipt_ref=forged_approval_ref,
        runtime=material["runtime"],
        claims=material["claims"],
    )

    assert response.status_code == 200, response.text
    projection = IntelligenceSystemProjectionV1Alpha1.model_validate_json(response.content)
    assert projection.mode is ProjectionMode.PROPOSED
    assert projection.activation_revision is None


@pytest.mark.asyncio
async def test_resource_state_denies_current_resource_grant() -> None:
    material = await _live_material()
    denying_runtime = _runtime(
        records=material["records"],
        governed_store=material["governed"],
        pack=material["pack"],
        resource_authority=_ResourceAuthority(deny=True),
        activation_authority=material["activation_authority"],
    )

    response = await _post(
        bound_plan=material["bound_plan"],
        approval_receipt_ref=material["approval_receipt_ref"],
        runtime=denying_runtime,
        claims=material["claims"],
    )

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_resource_state_fails_closed_for_a_continuation_cursor() -> None:
    # Exercised at the service layer: the shared strict resource-plane cursor
    # contract cannot round-trip through one JSON HTTP body next to the
    # non-strict selector transport model; that pre-existing constraint is
    # identical for the existing `/v1/intelligence/resources/query` endpoint
    # and is not specific to this composition.
    from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
    from ace.intelligence.contracts.resource_plane import (
        IntelligenceResourceCursorV1Alpha1,
        IntelligenceResourceKind,
        IntelligenceResourceQueryV1Alpha1,
    )
    from core.engine.core.intelligence_resource_plane import IntelligenceResourceHttpQueryV1

    material = await _live_material()
    product_id = material["product_id"]
    actor_ref = material["actor_ref"]
    unfiltered_query_id = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=product_id,
            actor_ref=actor_ref,
            authentication_receipt_ref="task_authentication_receipt:fixture-continuation",
            authentication_receipt_digest="sha256:" + "a" * 64,
            authenticated_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        ),
        product_id=product_id,
        authority_grant_ref="authority_grant:resource-state-read",
        resource_kinds=tuple(DOMAIN_HEALTH_RESOURCE_KINDS),
        as_of=NOW,
        available_at=NOW,
        page_size=50,
    ).query_id
    selector = IntelligenceResourceHttpQueryV1(
        authority_grant_ref="authority_grant:resource-state-read",
        resource_kinds=tuple(DOMAIN_HEALTH_RESOURCE_KINDS),
        subject_refs=(),
        as_of=NOW,
        available_at=NOW,
        page_size=50,
        cursor=IntelligenceResourceCursorV1Alpha1(
            query_id=unfiltered_query_id,
            after_available_at=NOW,
            after_resource_kind=IntelligenceResourceKind.OBSERVATION,
            after_resource_id="observation:" + "0" * 32,
            after_revision=1,
        ),
    )
    request = IntelligenceBuildResourceStateRequestV1(
        bound_plan=material["bound_plan"].model_dump(mode="json"),
        activation_approval_receipt_ref=material["approval_receipt_ref"],
        selector=selector,
    )

    projection = await project_intelligence_build_resource_state(
        request=request,
        user=material["claims"],
        runtime=material["live_runtime"],
    )

    assert projection.mode is ProjectionMode.PROPOSED
    assert projection.activation_revision is None
    assert any("did not fully close" in gap for gap in projection.gaps)


def test_resource_state_openapi_exposes_the_public_projection_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/v1/intelligence/builds/projection/resource-state"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("IntelligenceSystemProjectionV1Alpha1")
