from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_build_execution import IntelligenceBuildStartV1
from ace.application.intelligence_build_planning import (
    INTELLIGENCE_BUILD_PLANNER_CONTRACT,
    INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
    IntelligenceBuildPlanV1Alpha1,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1, DomainActivationSpecV1
from ace.intelligence.contracts.intelligence_builder_presentation import IntelligenceOnboardingProfileV1Alpha1
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
    return compile_pack_document_with_report(
        manifest_document,
        {item["path"]: resources[f"{root}/{item['path']}"] for item in manifest["resources"]},
    ).pack


PACK = _compiled_pack()
PACK_REFERENCE = CompiledPackRefV1(
    pack_id=PACK.metadata.pack_id,
    pack_version=PACK.metadata.version,
    compiled_pack_id=PACK.compiled_pack_id,
    pack_digest=PACK.pack_digest,
)
PLANNER_ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability=INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
    contract=INTELLIGENCE_BUILD_PLANNER_CONTRACT,
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
        return SimpleNamespace(pack=PACK) if reference == PACK_REFERENCE else None


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
        spec = DomainActivationSpecV1(
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
            compilation_receipt_ref="pack_compilation:fixture",
            conformance_receipt_refs=("pack_conformance:fixture",),
        )
        return IntelligenceBuildPlanV1Alpha1(
            request=request,
            planner_artifact=self.artifact_identity,
            pack_reference=self.pack_reference,
            activation_spec=spec,
            recorded_source_refs=request.recorded_source_refs,
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
        "recorded_source_refs": [
            {
                "source_group_id": "official_records",
                "material_id": "recorded_source_material:directive",
                "material_digest": "sha256:" + "d" * 64,
            }
        ],
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
    plan = IntelligenceBuildPlanV1Alpha1.model_validate_json(response.content)
    assert plan.request.product_id == PRODUCT
    assert plan.request.actor_ref == ACTOR
    assert plan.pack_reference == PACK_REFERENCE
    assert plan.activation_spec.spec_id.startswith("activation_spec:")
    assert plan.recorded_source_refs[0].material_id == "recorded_source_material:directive"
    assert plan.plan_digest.startswith("sha256:")
    assert len(planner.calls) == 1
    assert planner.calls[0][1] == PROFILE
    assert planner.calls[0][2] == PACK
    assert packs.calls == [PACK_REFERENCE]


@pytest.mark.asyncio
async def test_planned_execution_identity_is_byte_for_byte_the_existing_start_identity() -> None:
    response, _ = await _request(planner=_Planner())
    plan = IntelligenceBuildPlanV1Alpha1.model_validate_json(response.content)
    start = IntelligenceBuildStartV1(
        authority_grant_ref="authority_grant:build",
        resource_authority_grant_ref="authority_grant:read",
        activation_approval_receipt_ref="approval:activation",
        activation_approval_subject_ref=plan.activation_spec.spec_id,
        client_request_id=plan.request.client_request_id,
        profile_id=plan.request.profile_id,
        subject=plan.request.subject,
        outcome_id=plan.request.outcome_id,
        source_group_ids=plan.request.source_group_ids,
        recorded_source_refs=plan.request.recorded_source_refs,
        cadence_id=plan.request.cadence_id,
        approved_effects=plan.request.proposed_effects,
        requested_at=plan.request.requested_at,
    )

    assert _request_identity(request=start, product_id=PRODUCT, actor_ref=ACTOR) == (
        plan.execution_request_id,
        plan.execution_request_digest,
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
    assert request_schema["$ref"].endswith("IntelligenceBuildPlanPrepareV1")
    assert response_schema["$ref"].endswith("IntelligenceBuildPlanV1Alpha1")
