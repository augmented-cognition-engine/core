from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.installed_pack_artifacts import InstalledDomainPackPreview
from ace.intelligence import IntelligenceOnboardingProfileV1Alpha1
from ace.intelligence.contracts.activation import (
    DOMAIN_ACTIVATION_REVISION_VERSION,
    ORGANIZATION_OVERLAY_VERSION,
)
from ace.intelligence.contracts.pack import DomainPackManifestV1
from ace.intelligence.contracts.resource_plane import (
    RESOURCE_PLANE_PAGE_VERSION,
    RESOURCE_PLANE_QUERY_VERSION,
    RESOURCE_PLANE_RECORD_VERSION,
)
from ace.intelligence.contracts.subscriptions import SUBSCRIPTION_VERSION
from core.engine.api import intelligence_catalog
from core.engine.core.auth import get_current_user
from core.engine.core.installed_intelligence_catalog import InstalledOnboardingProfile, domain_pack_activation_store
from tests.test_installed_pack_artifacts import _pack

pytestmark = pytest.mark.unit


def _profile() -> IntelligenceOnboardingProfileV1Alpha1:
    return IntelligenceOnboardingProfileV1Alpha1.model_validate_json(
        """{
          "contract": "ace.intelligence.onboarding-profile/v1alpha1",
          "profile_id": "intelligence_onboarding_profile:world-ai",
          "topic_id": "artificial_intelligence",
          "domain_label": "World Intelligence",
          "topic_label": "Artificial intelligence",
          "display_name": "AI Command Center",
          "prompt": "What do you need to stay ahead of?",
          "description": "A cited view of material AI change for one person.",
          "starter_prompts": ["Keep me ahead of meaningful changes in AI."],
          "outcomes": [{
            "outcome_id": "decision_readiness",
            "label": "Stay decision-ready",
            "description": "Orient around material change and evidence.",
            "icon_hint": "strategy",
            "recommended_watch_ids": [],
            "recommended_intelligence_ids": [],
            "recommended_topic_labels": [],
            "recommended_intelligence_labels": []
          }],
          "source_groups": [],
          "cadences": [{"cadence_id": "daily", "label": "Daily", "description": "A daily orientation."}],
          "default_cadence_id": "daily",
          "first_value": {"public_sources_first": true, "private_sources_optional": true, "completion_label": "Open Brief"},
          "guardrails": {
            "declarative_only": true,
            "authorizes_connections": false,
            "authorizes_monitors": false,
            "proposed_sources_are_not_connected": true,
            "feedback_may_reweight_relevance_not_authority": true
          }
        }"""
    )


@pytest.mark.asyncio
async def test_installed_catalog_exposes_validated_inert_profiles_with_provenance(monkeypatch) -> None:
    monkeypatch.setattr(
        intelligence_catalog,
        "discover_installed_onboarding_profiles",
        lambda: (
            InstalledOnboardingProfile(
                distribution="ace-domain-world-intelligence",
                distribution_version="1.0.0",
                resource_path="domain_packs/world_intelligence_ai/onboarding_profile.json",
                profile=_profile(),
            ),
        ),
    )
    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "principal:personal-analyst",
        "product": "product:personal-intelligence",
        "authorities": ["administer_lifecycle"],
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/intelligence/catalog/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "ace.http.installed-intelligence-catalog/v1alpha1"
    assert body["profiles"][0]["distribution"] == "ace-domain-world-intelligence"
    assert body["profiles"][0]["profile"]["domain_label"] == "World Intelligence"
    assert body["profiles"][0]["profile"]["profile_digest"].startswith("sha256:")


def test_installed_catalog_openapi_exposes_stable_response_contract() -> None:
    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    operation = app.openapi()["paths"]["/v1/intelligence/catalog/profiles"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("InstalledIntelligenceCatalogV1")


@pytest.mark.asyncio
async def test_pack_catalog_exposes_manifest_version_and_install_provenance_without_activation(monkeypatch) -> None:
    resources = _pack()
    manifest_path = "domain_packs/neutral_measurement/manifest.json"
    manifest = DomainPackManifestV1.model_validate(json.loads(resources[manifest_path]))
    monkeypatch.setattr(
        intelligence_catalog,
        "discover_installed_domain_pack_previews",
        lambda: (
            InstalledDomainPackPreview(
                distribution="ace-domain-neutral-measurement",
                distribution_version="2.5.0",
                manifest_resource_path=manifest_path,
                manifest_digest="sha256:" + "1" * 64,
                manifest=manifest,
            ),
        ),
    )
    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "principal:personal-analyst",
        "product": "product:personal-intelligence",
        "authorities": ["administer_lifecycle"],
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/intelligence/catalog/packs")

    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "ace.http.installed-domain-pack-catalog/v1alpha1"
    assert body["packs"][0]["manifest"]["metadata"] == {
        "pack_id": "neutral_measurement",
        "version": "1.0.0",
        "display_name": "Neutral Measurement",
        "description": None,
    }
    assert body["packs"][0]["distribution_version"] == "2.5.0"
    assert "activation" not in body["packs"][0]
    lifecycle = {item["capability_id"]: item for item in body["packs"][0]["lifecycle"]}
    assert lifecycle["installed_material"]["availability"] == "available"
    assert lifecycle["reviewed_customization"]["availability"] == "contract_only"
    assert lifecycle["reviewed_customization"]["contract_refs"] == [ORGANIZATION_OVERLAY_VERSION]
    assert lifecycle["upgrade_discovery"]["availability"] == "not_exposed"
    assert lifecycle["activation_history"]["availability"] == "available"
    assert lifecycle["activation_history"]["endpoint"].endswith("/{activation_key}")
    assert lifecycle["activation_history"]["contract_refs"] == ["ace.intelligence.domain-activation-revision/v1alpha2"]
    assert lifecycle["rollback"]["availability"] == "contract_only"


@pytest.mark.asyncio
async def test_consumer_catalog_separates_available_contracts_from_unexposed_delivery() -> None:
    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "principal:personal-analyst",
        "product": "product:personal-intelligence",
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/intelligence/catalog/consumers")

    assert response.status_code == 200
    body = response.json()
    interfaces = {item["interface_id"]: item for item in body["interfaces"]}
    assert interfaces["intelligence_resource_http"]["availability"] == "available"
    assert interfaces["intelligence_resource_http"]["endpoint"] == "POST /v1/intelligence/resources/query"
    assert interfaces["intelligence_resource_http"]["contract_refs"] == [
        RESOURCE_PLANE_QUERY_VERSION,
        RESOURCE_PLANE_RECORD_VERSION,
        RESOURCE_PLANE_PAGE_VERSION,
    ]
    assert len(interfaces["ace_thin_mcp_client"]["operations"]) == 11
    assert interfaces["ace_python_contracts"]["contract_refs"][-3:] == [
        ORGANIZATION_OVERLAY_VERSION,
        DOMAIN_ACTIVATION_REVISION_VERSION,
        SUBSCRIPTION_VERSION,
    ]
    assert interfaces["intelligence_subscription"]["availability"] == "contract_only"
    assert interfaces["intelligence_subscription"]["endpoint"] == ("POST /v1/intelligence/subscriptions/lifecycle")
    assert interfaces["intelligence_subscription"]["operations"] == [
        "record-only create",
        "record-only pause",
        "record-only resume",
        "record-only revoke",
    ]
    assert "No list/current projection" in interfaces["intelligence_subscription"]["delivery_boundary"]
    assert interfaces["intelligence_stream"]["availability"] == "not_exposed"
    assert interfaces["intelligence_stream"]["endpoint"] is None
    assert interfaces["intelligence_stream"]["operations"] == []
    assert "LIVE operator-state SSE" in interfaces["intelligence_stream"]["delivery_boundary"]
    assert interfaces["intelligence_webhook"]["availability"] == "not_exposed"
    assert interfaces["intelligence_webhook"]["endpoint"] is None
    assert interfaces["intelligence_webhook"]["operations"] == []
    assert "global notification webhook" in interfaces["intelligence_webhook"]["delivery_boundary"]
    assert interfaces["investigation_board"]["availability"] == "navigation_only"
    assert any("provenance" in item.lower() for item in body["unresolved_dependencies"])


def test_installed_catalog_openapi_exposes_pack_and_consumer_response_contracts() -> None:
    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    paths = app.openapi()["paths"]
    pack_schema = paths["/v1/intelligence/catalog/packs"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    consumer_schema = paths["/v1/intelligence/catalog/consumers"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert pack_schema["$ref"].endswith("InstalledDomainPackCatalogV1")
    assert consumer_schema["$ref"].endswith("IntelligenceConsumerCatalogV1")
    history_schema = paths["/v1/intelligence/catalog/packs/activations/{activation_key}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert history_schema["$ref"].endswith("DomainPackActivationHistoryProjectionV1")
    assert not any(
        path.startswith("/v1/intelligence/streams") or path.startswith("/v1/intelligence/webhooks") for path in paths
    )


@pytest.mark.asyncio
async def test_pack_activation_history_requires_exact_product_scope_and_activation_key() -> None:
    class _EmptyStore:
        async def load_head(self, **kwargs):
            return None

    app = FastAPI()
    app.include_router(intelligence_catalog.router)
    app.dependency_overrides[domain_pack_activation_store] = _EmptyStore
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "principal:personal-analyst",
        "product": "product:personal-intelligence",
        "authorities": ["administer_lifecycle"],
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/v1/intelligence/catalog/packs/activations/world_intelligence")
    assert missing.status_code == 404
    assert "exact activation key" in missing.json()["detail"]

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "principal:personal-analyst",
        "product": "product:personal-intelligence",
        "authorities": [],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/v1/intelligence/catalog/packs/activations/world_intelligence")
    assert denied.status_code == 403

    app.dependency_overrides[get_current_user] = lambda: {"sub": "principal:personal-analyst"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/v1/intelligence/catalog/packs/activations/world_intelligence")
    assert unauthenticated.status_code == 401
