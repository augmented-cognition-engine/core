from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_build_execution import IntelligenceBuildStartV1Alpha2
from ace.application.intelligence_build_plan_binding import (
    BoundIntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanBindingError,
    IntelligenceBuildPlanBindingService,
    IntelligenceBuildPlanBindRequestV1Alpha1,
)
from ace.application.intelligence_build_planning import (
    INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT,
    INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
    IntelligenceBuildActivationProposalV1Alpha1,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
)
from ace.application.recorded_source_selection import RecordedSourceSelectionV1Alpha1
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.conformance import run_domain_pack_conformance
from ace.intelligence.contracts.activation import (
    AuthorityBindingV1,
    CapabilityBindingV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
)
from ace.intelligence.contracts.intelligence_builder_presentation import IntelligenceOnboardingProfileV1Alpha1
from ace.intelligence.contracts.pack import AuthorityRequestV1, CapabilityRequirementV1, CompiledDomainPackV1
from ace.intelligence.packs.compiler import compile_pack_document_with_report
from core.engine.api.intelligence_builds import router
from core.engine.core.auth import get_current_user
from core.engine.core.installed_intelligence_catalog import InstalledOnboardingProfile
from core.engine.core.intelligence_build import _request_identity
from core.engine.core.intelligence_build_plan import IntelligenceBuildPlanHttpRuntime, intelligence_build_plan_runtime
from tests.test_api_intelligence_catalog import _profile as base_profile
from tests.test_installed_pack_artifacts import _pack as pack_resources

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
PRODUCT = "product:personal-intelligence"
ACTOR = "principal:personal-analyst"


def _compiled_pack():
    resources = pack_resources()
    root = "domain_packs/neutral_measurement"
    manifest_document = resources[f"{root}/manifest.json"]
    manifest = json.loads(manifest_document)
    compiled = compile_pack_document_with_report(
        manifest_document,
        {item["path"]: resources[f"{root}/{item['path']}"] for item in manifest["resources"]},
    )
    receipt = run_domain_pack_conformance(
        manifest_document=manifest_document,
        resources={item["path"]: resources[f"{root}/{item['path']}"] for item in manifest["resources"]},
        fixture_document=resources[f"{root}/conformance/activation_golden_fixture.json"],
    )
    return SimpleNamespace(
        pack=compiled.pack,
        compilation=compiled.compilation,
        conformance_receipts=(receipt,),
    )


PACK_ARTIFACT = _compiled_pack()
PACK = PACK_ARTIFACT.pack
PACK_REFERENCE = CompiledPackRefV1(
    pack_id=PACK.metadata.pack_id,
    pack_version=PACK.metadata.version,
    compiled_pack_id=PACK.compiled_pack_id,
    pack_digest=PACK.pack_digest,
)
PLANNER_ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability=INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
    contract=INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT,
    implementation_id="fixture_planner",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "b" * 64,
)


def _profile() -> IntelligenceOnboardingProfileV1Alpha1:
    material = base_profile().model_dump(mode="json", exclude={"profile_digest"})
    material["source_groups"] = [
        {
            "source_group_id": "official_records",
            "label": "Official records",
            "description": "Reviewed source material already recorded by ACE.",
            "evidence_role": "primary_evidence",
            "source_ids": ["official_record"],
            "source_labels": ["Official record"],
            "access_label": "Recorded material",
            "default_selected": True,
        }
    ]
    return IntelligenceOnboardingProfileV1Alpha1.model_validate_json(json.dumps(material))


PROFILE = _profile()
INSTALLED_PROFILE = InstalledOnboardingProfile(
    distribution="ace-domain-fixture",
    distribution_version="1.0.0",
    resource_path="domain_packs/neutral_measurement/onboarding_profile.json",
    profile=PROFILE,
)


class _PackResolver:
    def __init__(self) -> None:
        self.calls = []

    async def resolve_exact(self, *, reference):
        self.calls.append(reference)
        return PACK_ARTIFACT if reference == PACK_REFERENCE else None


class _Planner:
    profile_id = PROFILE.profile_id
    pack_reference = PACK_REFERENCE
    artifact_identity = PLANNER_ARTIFACT

    def __init__(self, *, invalid: bool = False, unavailable: bool = False) -> None:
        self.invalid = invalid
        self.unavailable = unavailable
        self.calls = []

    async def prepare(self, request, *, profile, pack):
        self.calls.append((request, profile, pack))
        if self.unavailable:
            raise RuntimeError("planner dependency unavailable")
        if self.invalid:
            return object()
        proposal = IntelligenceBuildActivationProposalV1Alpha1(
            product_id=request.product_id,
            activation_key="personal_intelligence",
            pack=self.pack_reference,
            overlay=CompiledOverlayV1(
                overlay_id="personal_policy",
                version="1.0.0",
                pack_id=self.pack_reference.pack_id,
                pack_version=self.pack_reference.pack_version,
                pack_digest=self.pack_reference.pack_digest,
            ),
            capability_requirement_ids=tuple(item.requirement_id for item in pack.capability_requirements),
            authority_request_ids=tuple(item.request_id for item in pack.authority_requests),
        )
        selection = RecordedSourceSelectionV1Alpha1(
            product_id=request.product_id,
            pack=self.pack_reference,
            source_group_id="official_records",
            mapping_id="official_record_snapshot",
            subject_binding_id="published_record",
            entity_type_id="measurement",
            entity_ref="entity:artificial-intelligence",
            source_definition_ref="source_definition:official-record",
            source_type_ref="source:official-record/v1",
            source_uri="https://example.invalid/official-record",
            captured_payload_digest="sha256:" + "d" * 64,
            observed_at=request.requested_at,
            locator="record:official",
        )
        return IntelligenceBuildPlanV1Alpha3(
            request=request,
            planner_artifact=self.artifact_identity,
            pack_reference=self.pack_reference,
            activation_proposal=proposal,
            recorded_source_selections=(selection,),
        )


class _PlannerResolution:
    def __init__(self, planner) -> None:
        self.planner = planner

    def resolve(self, profile_id):
        return self.planner if self.planner is not None and profile_id == self.planner.profile_id else None


def _claims() -> dict:
    return {
        "sub": ACTOR,
        "product": PRODUCT,
        "authorities": [],
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _body() -> dict:
    return {
        "client_request_id": "atrium-request:first-picture",
        "profile_id": PROFILE.profile_id,
        "profile_digest": PROFILE.profile_digest,
        "subject": "Keep me ahead of meaningful changes in artificial intelligence.",
        "outcome_id": "decision_readiness",
        "source_group_ids": ["official_records"],
        "cadence_id": "daily",
        "proposed_effects": [
            "connect_sources",
            "map_concepts",
            "activate_watch",
            "create_first_brief",
        ],
        "requested_at": NOW.isoformat(),
    }


async def _request(*, planner, body: dict | None = None, claims: dict | None = None):
    app = FastAPI()
    app.include_router(router)
    packs = _PackResolver()
    app.dependency_overrides[get_current_user] = lambda: _claims() if claims is None else claims
    app.dependency_overrides[intelligence_build_plan_runtime] = lambda: IntelligenceBuildPlanHttpRuntime(
        profiles=(INSTALLED_PROFILE,),
        packs=packs,
        planners=_PlannerResolution(planner),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/intelligence/builds/prepare", json=body or _body())
    return response, packs


@pytest.mark.asyncio
async def test_prepare_returns_exact_review_material_without_authority_or_execution() -> None:
    planner = _Planner()
    response, packs = await _request(planner=planner)

    assert response.status_code == 200
    plan = IntelligenceBuildPlanV1Alpha3.model_validate_json(response.content)
    assert plan.request.product_id == PRODUCT
    assert plan.request.actor_ref == ACTOR
    assert plan.pack_reference == PACK_REFERENCE
    assert plan.activation_proposal.proposal_id.startswith("intelligence_build_activation_proposal:")
    assert not hasattr(plan, "execution_request_id")
    assert plan.recorded_source_selection_refs[0].selection_id.startswith("recorded_source_selection:")
    assert plan.plan_digest.startswith("sha256:")
    assert len(planner.calls) == 1
    assert planner.calls[0][1] == PROFILE
    assert planner.calls[0][2] == PACK
    assert packs.calls == [PACK_REFERENCE]


@pytest.mark.asyncio
async def test_bound_execution_identity_is_byte_for_byte_the_existing_start_identity() -> None:
    response, _ = await _request(planner=_Planner())
    plan = IntelligenceBuildPlanV1Alpha3.model_validate_json(response.content)
    bind_body = IntelligenceBuildPlanBindRequestV1Alpha1(
        plan=plan,
        bound_at=NOW,
    ).model_dump(mode="json")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _claims
    app.dependency_overrides[intelligence_build_plan_runtime] = lambda: IntelligenceBuildPlanHttpRuntime(
        profiles=(INSTALLED_PROFILE,),
        packs=_PackResolver(),
        planners=_PlannerResolution(_Planner()),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bind_response = await client.post("/v1/intelligence/builds/bind", json=bind_body)
    assert bind_response.status_code == 200, bind_response.text
    bound = BoundIntelligenceBuildPlanV1Alpha1.model_validate_json(bind_response.content)
    start = IntelligenceBuildStartV1Alpha2(
        authority_grant_ref="authority_grant:build",
        resource_authority_grant_ref="authority_grant:read",
        activation_approval_receipt_ref="approval:activation",
        activation_approval_subject_ref=bound.activation_spec.spec_id,
        client_request_id=plan.request.client_request_id,
        profile_id=plan.request.profile_id,
        subject=plan.request.subject,
        outcome_id=plan.request.outcome_id,
        source_group_ids=plan.request.source_group_ids,
        recorded_source_selection_refs=plan.recorded_source_selection_refs,
        cadence_id=plan.request.cadence_id,
        approved_effects=plan.request.proposed_effects,
        requested_at=plan.request.requested_at,
    )

    assert _request_identity(request=start, product_id=PRODUCT, actor_ref=ACTOR) == (
        bound.execution_request_id,
        bound.execution_request_digest,
    )


@pytest.mark.asyncio
async def test_prepare_fails_closed_for_unknown_or_changed_installed_material() -> None:
    missing, _ = await _request(planner=None)
    assert missing.status_code == 503
    assert "no Intelligence build planner" in missing.json()["detail"]

    stale_body = _body()
    stale_body["profile_digest"] = "sha256:" + "0" * 64
    stale, _ = await _request(planner=_Planner(), body=stale_body)
    assert stale.status_code == 409

    unknown_body = _body()
    unknown_body["profile_id"] = "intelligence_onboarding_profile:unknown"
    unknown, _ = await _request(planner=_Planner(), body=unknown_body)
    assert unknown.status_code == 404

    invalid, _ = await _request(planner=_Planner(invalid=True))
    assert invalid.status_code == 409


@pytest.mark.asyncio
async def test_prepare_rejects_legacy_activation_bound_material_references() -> None:
    body = _body()
    body["recorded_source_refs"] = [
        {
            "source_group_id": "official_records",
            "material_id": "recorded_source_material:legacy",
            "material_digest": "sha256:" + "a" * 64,
        }
    ]

    response, _ = await _request(planner=_Planner(), body=body)

    assert response.status_code == 422

    unavailable, _ = await _request(planner=_Planner(unavailable=True))
    assert unavailable.status_code == 503


@pytest.mark.asyncio
async def test_prepare_requires_only_verified_product_identity_not_build_authority() -> None:
    accepted, _ = await _request(planner=_Planner(), claims=_claims())
    assert accepted.status_code == 200

    unauthenticated, _ = await _request(planner=_Planner(), claims={"sub": ACTOR})
    assert unauthenticated.status_code == 401


def test_prepare_openapi_exposes_stable_request_and_plan_contracts() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/v1/intelligence/builds/prepare"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].removesuffix("-Input").endswith("IntelligenceBuildPlanPrepareV1Alpha2")
    assert response_schema["$ref"].removesuffix("-Output").endswith("IntelligenceBuildPlanV1Alpha3")
    bind_operation = app.openapi()["paths"]["/v1/intelligence/builds/bind"]["post"]
    bind_request = bind_operation["requestBody"]["content"]["application/json"]["schema"]
    bind_response = bind_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert bind_request["$ref"].removesuffix("-Input").endswith("IntelligenceBuildPlanBindRequestV1Alpha1")
    assert bind_response["$ref"].removesuffix("-Output").endswith("BoundIntelligenceBuildPlanV1Alpha1")


def _pack_with_reviewed_requirements() -> CompiledDomainPackV1:
    material = PACK.model_dump(
        mode="python",
        exclude={"compiled_pack_id", "pack_digest", "declared_compatibility"},
    )
    material.update(
        contract="ace.intelligence.compiled-domain-pack/v1alpha1",
        compiler_contract="ace.intelligence.pack-compiler/v1alpha1",
        intelligence_contract="ace.intelligence.runtime/v1alpha1",
        manifest_contract="ace.intelligence.domain-pack-manifest/v1alpha1",
        capability_requirements=(
            CapabilityRequirementV1(
                requirement_id="official_snapshot",
                capability="source_snapshot",
                contract="ace.source.snapshot/v1alpha1",
            ),
        ),
        authority_requests=(AuthorityRequestV1(request_id="read_official_record", authority="source_read"),),
    )
    return CompiledDomainPackV1.model_validate(material)


REVIEWED_PACK = _pack_with_reviewed_requirements()
REVIEWED_PACK_REFERENCE = CompiledPackRefV1(
    pack_id=REVIEWED_PACK.metadata.pack_id,
    pack_version=REVIEWED_PACK.metadata.version,
    compiled_pack_id=REVIEWED_PACK.compiled_pack_id,
    pack_digest=REVIEWED_PACK.pack_digest,
)


class _ReviewedPackResolver:
    async def resolve_exact(self, *, reference):
        if reference != REVIEWED_PACK_REFERENCE:
            return None
        return SimpleNamespace(
            pack=REVIEWED_PACK,
            compilation=PACK_ARTIFACT.compilation,
            conformance_receipts=PACK_ARTIFACT.conformance_receipts,
        )


def _reviewed_plan(
    *, proposal_requirement_ids=("official_snapshot",), proposal_authority_ids=("read_official_record",)
):
    request = IntelligenceBuildPlanRequestV1Alpha2(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        client_request_id="atrium-request:reviewed-bindings",
        profile_id=PROFILE.profile_id,
        profile_digest=PROFILE.profile_digest,
        subject="Track the exact reviewed official record progression.",
        outcome_id="decision_readiness",
        source_group_ids=("official_records",),
        cadence_id="daily",
        requested_at=NOW,
    )
    artifact = PLANNER_ARTIFACT.model_copy(update={"contract": INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT})
    proposal = IntelligenceBuildActivationProposalV1Alpha1(
        product_id=PRODUCT,
        activation_key="personal_intelligence",
        pack=REVIEWED_PACK_REFERENCE,
        overlay=CompiledOverlayV1(
            overlay_id="personal_policy",
            version="1.0.0",
            pack_id=REVIEWED_PACK_REFERENCE.pack_id,
            pack_version=REVIEWED_PACK_REFERENCE.pack_version,
            pack_digest=REVIEWED_PACK_REFERENCE.pack_digest,
        ),
        capability_requirement_ids=proposal_requirement_ids,
        authority_request_ids=proposal_authority_ids,
    )
    return IntelligenceBuildPlanV1Alpha3(
        request=request,
        planner_artifact=artifact,
        pack_reference=REVIEWED_PACK_REFERENCE,
        activation_proposal=proposal,
    )


def _capability(*, capability="source_snapshot", requirement_id="official_snapshot") -> CapabilityBindingV1:
    return CapabilityBindingV1(
        requirement_id=requirement_id,
        capability=capability,
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="recorded_snapshot_adapter",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "4" * 64,
    )


def _authority(*, authority="source_read", grant_ref="authority_grant:official-record") -> AuthorityBindingV1:
    return AuthorityBindingV1(
        request_id="read_official_record",
        authority=authority,
        grant_ref=grant_ref,
    )


@pytest.mark.asyncio
async def test_bind_requires_complete_exact_reviewed_requirement_sets_and_pack_proposal() -> None:
    service = IntelligenceBuildPlanBindingService(packs=_ReviewedPackResolver())
    plan = _reviewed_plan()

    for capabilities, authorities in (
        ((), (_authority(),)),
        ((_capability(),), ()),
        ((_capability(capability="other_capability"),), (_authority(),)),
        ((_capability(),), (_authority(authority="other_authority"),)),
        ((_capability(), _capability(requirement_id="extra_requirement")), (_authority(),)),
    ):
        with pytest.raises(IntelligenceBuildPlanBindingError):
            await service.bind(
                IntelligenceBuildPlanBindRequestV1Alpha1(
                    plan=plan,
                    capability_bindings=capabilities,
                    authority_bindings=authorities,
                    bound_at=NOW,
                )
            )

    stale = _reviewed_plan(proposal_requirement_ids=("changed_requirement",))
    with pytest.raises(IntelligenceBuildPlanBindingError, match="requirements"):
        await service.bind(
            IntelligenceBuildPlanBindRequestV1Alpha1(
                plan=stale,
                capability_bindings=(_capability(),),
                authority_bindings=(_authority(),),
                bound_at=NOW,
            )
        )


@pytest.mark.asyncio
async def test_bind_is_deterministic_and_binding_changes_rekey_spec_and_execution() -> None:
    service = IntelligenceBuildPlanBindingService(packs=_ReviewedPackResolver())
    plan = _reviewed_plan()

    def request(grant_ref: str):
        return IntelligenceBuildPlanBindRequestV1Alpha1(
            plan=plan,
            capability_bindings=(_capability(),),
            authority_bindings=(_authority(grant_ref=grant_ref),),
            bound_at=NOW,
        )

    first = await service.bind(request("authority_grant:official-record"))
    replay = await service.bind(request("authority_grant:official-record"))
    changed = await service.bind(request("authority_grant:official-record-updated"))

    assert first == replay
    assert first.activation_spec.spec_id != changed.activation_spec.spec_id
    assert first.execution_request_id != changed.execution_request_id
    assert first.execution_request_digest != changed.execution_request_digest


@pytest.mark.asyncio
async def test_bind_rejects_stale_profile_planner_and_pack_without_authority_resolution() -> None:
    response, _ = await _request(planner=_Planner())
    plan = IntelligenceBuildPlanV1Alpha3.model_validate_json(response.content)

    async def post(candidate: IntelligenceBuildPlanV1Alpha3):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = _claims
        app.dependency_overrides[intelligence_build_plan_runtime] = lambda: IntelligenceBuildPlanHttpRuntime(
            profiles=(INSTALLED_PROFILE,),
            packs=_PackResolver(),
            planners=_PlannerResolution(_Planner()),
        )
        body = IntelligenceBuildPlanBindRequestV1Alpha1(plan=candidate, bound_at=NOW).model_dump(mode="json")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/v1/intelligence/builds/bind", json=body)

    stale_request_material = plan.request.model_dump(mode="python", exclude={"request_id", "request_digest"})
    stale_request_material["profile_digest"] = "sha256:" + "0" * 64
    stale_profile = IntelligenceBuildPlanV1Alpha3(
        request=IntelligenceBuildPlanRequestV1Alpha2(**stale_request_material),
        planner_artifact=plan.planner_artifact,
        pack_reference=plan.pack_reference,
        activation_proposal=plan.activation_proposal,
        recorded_source_selections=plan.recorded_source_selections,
    )
    assert (await post(stale_profile)).status_code == 409

    stale_planner = IntelligenceBuildPlanV1Alpha3(
        request=plan.request,
        planner_artifact=plan.planner_artifact.model_copy(update={"artifact_digest": "sha256:" + "9" * 64}),
        pack_reference=plan.pack_reference,
        activation_proposal=plan.activation_proposal,
        recorded_source_selections=plan.recorded_source_selections,
    )
    assert (await post(stale_planner)).status_code == 409

    class _MissingPackResolver:
        async def resolve_exact(self, *, reference):
            del reference
            return None

    with pytest.raises(IntelligenceBuildPlanBindingError, match="not installed"):
        await IntelligenceBuildPlanBindingService(packs=_MissingPackResolver()).bind(
            IntelligenceBuildPlanBindRequestV1Alpha1(plan=plan, bound_at=NOW)
        )
