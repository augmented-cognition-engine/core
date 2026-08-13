from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.intelligence import IntelligenceOnboardingProfileV1Alpha1
from core.engine.api import intelligence_catalog
from core.engine.core.auth import get_current_user
from core.engine.core.installed_intelligence_catalog import InstalledOnboardingProfile

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
