from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from core.engine.core.installed_intelligence_catalog import (
    InstalledIntelligenceCatalogError,
    discover_installed_onboarding_profiles,
)

pytestmark = pytest.mark.unit


def _profile(*, profile_id: str, topic_id: str, domain_label: str) -> dict:
    return {
        "contract": "ace.intelligence.onboarding-profile/v1alpha1",
        "profile_id": profile_id,
        "topic_id": topic_id,
        "domain_label": domain_label,
        "topic_label": topic_id.replace("_", " ").title(),
        "display_name": f"{domain_label} Command Center",
        "prompt": "What do you need to stay ahead of?",
        "description": "A validated inert starting point for one personal Intelligence picture.",
        "starter_prompts": ["Keep me ahead of material changes that affect my decisions."],
        "outcomes": [
            {
                "outcome_id": "decision_readiness",
                "label": "Stay decision-ready",
                "description": "Orient around meaningful change and the evidence behind it.",
                "icon_hint": "strategy",
                "recommended_watch_ids": [],
                "recommended_intelligence_ids": [],
                "recommended_topic_labels": [],
                "recommended_intelligence_labels": [],
            }
        ],
        "source_groups": [],
        "cadences": [{"cadence_id": "daily", "label": "Daily", "description": "A concise daily orientation."}],
        "default_cadence_id": "daily",
        "first_value": {
            "public_sources_first": True,
            "private_sources_optional": True,
            "completion_label": "Open my first Brief",
        },
        "guardrails": {
            "declarative_only": True,
            "authorizes_connections": False,
            "authorizes_monitors": False,
            "proposed_sources_are_not_connected": True,
            "feedback_may_reweight_relevance_not_authority": True,
        },
    }


@dataclass
class _Metadata:
    name: str

    def get(self, key: str):
        return self.name if key == "Name" else None


class _Distribution:
    def __init__(self, *, root: Path, name: str, version: str, resources: dict[str, dict | str]) -> None:
        self.root = root
        self.metadata = _Metadata(name)
        self.version = version
        self.files = tuple(PurePosixPath(path) for path in resources)
        for relative, document in resources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document) if isinstance(document, dict) else document)

    def locate_file(self, path) -> Path:
        return self.root / str(path)


def test_discovers_world_and_market_profiles_by_validated_shape_not_package_name(tmp_path: Path) -> None:
    market = _Distribution(
        root=tmp_path / "market",
        name="anything-market",
        version="1.0.0",
        resources={
            "domain_packs/market_intelligence/onboarding_profile.json": _profile(
                profile_id="intelligence_onboarding_profile:market",
                topic_id="market_intelligence",
                domain_label="Market Intelligence",
            )
        },
    )
    world = _Distribution(
        root=tmp_path / "world",
        name="anything-world",
        version="1.0.0",
        resources={
            "domain_packs/world_intelligence_ai/onboarding_profile.json": _profile(
                profile_id="intelligence_onboarding_profile:world",
                topic_id="artificial_intelligence",
                domain_label="World Intelligence",
            ),
            "domain_packs/world_intelligence_ai/manifest.json": {},
        },
    )

    found = discover_installed_onboarding_profiles([world, market])

    assert [item.profile.domain_label for item in found] == ["Market Intelligence", "World Intelligence"]
    assert [item.distribution for item in found] == ["anything-market", "anything-world"]
    assert all(item.profile.profile_digest.startswith("sha256:") for item in found)


def test_rejects_malformed_or_conflicting_installed_profiles(tmp_path: Path) -> None:
    malformed = _Distribution(
        root=tmp_path / "malformed",
        name="malformed-pack",
        version="1.0.0",
        resources={"domain_packs/broken/onboarding_profile.json": "not-json"},
    )
    with pytest.raises(InstalledIntelligenceCatalogError, match="failed exact validation"):
        discover_installed_onboarding_profiles([malformed])

    first = _profile(
        profile_id="intelligence_onboarding_profile:shared",
        topic_id="first_topic",
        domain_label="First Intelligence",
    )
    second = _profile(
        profile_id="intelligence_onboarding_profile:shared",
        topic_id="second_topic",
        domain_label="Second Intelligence",
    )
    one = _Distribution(
        root=tmp_path / "one",
        name="pack-one",
        version="1.0.0",
        resources={"domain_packs/one/onboarding_profile.json": first},
    )
    two = _Distribution(
        root=tmp_path / "two",
        name="pack-two",
        version="1.0.0",
        resources={"domain_packs/two/onboarding_profile.json": second},
    )
    with pytest.raises(InstalledIntelligenceCatalogError, match="identity conflicts"):
        discover_installed_onboarding_profiles([one, two])
