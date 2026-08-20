"""1.2.1 journey-start fix (issue #252): the public artifacts must start J2→J3.

The 1.2.0 acceptance run proved no public artifact ships an onboarding profile
(F3) and no Intelligence build planner is registered anywhere (F4). These
tests pin the fix: the Personal profile ships in the pack distribution at the
scanned discovery path, and the first-party Personal planner registers from
the ``ace.intelligence_build_planners`` entry-point group declared by ace-core.
"""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ace.application.intelligence_build_planning import (
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
    validate_intelligence_build_planner_v1alpha3_registration,
)
from ace.intelligence.contracts.intelligence_builder_presentation import (
    IntelligenceOnboardingProfileV1Alpha1,
)
from ace.intelligence.packs.compiler import compile_pack_document_with_report
from core.engine.personal_intelligence.build_planner import (
    PERSONAL_PROFILE_ID,
    load_personal_intelligence_build_planner,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO / "domain_packs" / "personal_intelligence"


def _shipped_profile() -> IntelligenceOnboardingProfileV1Alpha1:
    return IntelligenceOnboardingProfileV1Alpha1.model_validate_json(
        (PACK_ROOT / "onboarding_profile.json").read_bytes()
    )


def _compiled_pack():
    manifest_document = (PACK_ROOT / "manifest.json").read_bytes()
    manifest = json.loads(manifest_document)
    resources = {item["path"]: (PACK_ROOT / item["path"]).read_bytes() for item in manifest["resources"]}
    return compile_pack_document_with_report(manifest_document, resources).pack


class TestShippedOnboardingProfile:
    def test_profile_validates_and_names_the_personal_journey(self):
        profile = _shipped_profile()
        assert profile.profile_id == PERSONAL_PROFILE_ID
        assert profile.source_groups, "the Choose flow needs at least one source group"
        group_ids = {item.source_group_id for item in profile.source_groups}
        assert "personal_local_sources" in group_ids

    def test_profile_ships_in_the_pack_distribution(self):
        project = tomllib.loads((PACK_ROOT / "pyproject.toml").read_text())
        force_include = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        assert force_include["onboarding_profile.json"] == "domain_packs/personal_intelligence/onboarding_profile.json"
        # `python -m build` builds the wheel FROM the sdist, so every
        # wheel-force-included file must also be in the sdist include list —
        # the v1.2.1 release build failed exactly here.
        sdist_include = project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        for source in force_include:
            assert source in sdist_include, f"{source} is wheel-included but missing from the sdist"

    def test_profile_source_groups_cover_the_four_local_kinds(self):
        profile = _shipped_profile()
        labels = " ".join(
            f"{group.label} {group.description} {' '.join(group.source_labels)}" for group in profile.source_groups
        ).lower()
        for kind in ("markdown", "pdf", "csv", "json"):
            assert kind in labels, f"profile does not present the {kind} local source kind"


class TestPersonalPlanner:
    def test_planner_loads_and_passes_registration_validation(self):
        planner = load_personal_intelligence_build_planner()
        pack_reference, artifact = validate_intelligence_build_planner_v1alpha3_registration(
            planner, profile_id=PERSONAL_PROFILE_ID
        )
        compiled = _compiled_pack()
        assert pack_reference.pack_digest == compiled.pack_digest
        assert pack_reference.compiled_pack_id == compiled.compiled_pack_id
        assert artifact.implementation_id

    def test_entry_point_is_declared_by_ace_core(self):
        project = tomllib.loads((REPO / "pyproject.toml").read_text())
        group = project["project"]["entry-points"]["ace.intelligence_build_planners"]
        assert group["personal_intelligence"] == (
            "core.engine.personal_intelligence.build_planner:load_personal_intelligence_build_planner"
        )

    @pytest.mark.asyncio
    async def test_prepare_produces_a_reviewable_activation_neutral_plan(self):
        planner = load_personal_intelligence_build_planner()
        profile = _shipped_profile()
        pack = _compiled_pack()
        request = IntelligenceBuildPlanRequestV1Alpha2(
            product_id="product:personal-acceptance",
            actor_ref="principal:owner",
            client_request_id="client:accept-1",
            profile_id=profile.profile_id,
            profile_digest=profile.profile_digest,
            subject="What currently matters in my personal notes",
            outcome_id=profile.outcomes[0].outcome_id,
            source_group_ids=tuple(item.source_group_id for item in profile.source_groups),
            cadence_id=profile.default_cadence_id,
            requested_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC),
        )
        plan = await planner.prepare(request, profile=profile, pack=pack)
        assert isinstance(plan, IntelligenceBuildPlanV1Alpha3)
        assert plan.request == request
        assert plan.pack_reference == planner.pack_reference
        proposal = plan.activation_proposal
        assert proposal.pack == planner.pack_reference
        assert set(proposal.capability_requirement_ids) == {
            item.requirement_id for item in pack.capability_requirements
        }
        assert set(proposal.authority_request_ids) == {item.request_id for item in pack.authority_requests}
        assert plan.plan_id is not None and plan.plan_digest is not None

    @pytest.mark.asyncio
    async def test_prepare_refuses_a_foreign_profile(self):
        planner = load_personal_intelligence_build_planner()
        profile = _shipped_profile()
        foreign = profile.model_copy(update={"profile_id": "intelligence_onboarding_profile:other"})
        request_material = dict(
            product_id="product:personal-acceptance",
            actor_ref="principal:owner",
            client_request_id="client:accept-2",
            profile_id="intelligence_onboarding_profile:other",
            profile_digest=profile.profile_digest,
            subject="What currently matters in my personal notes",
            outcome_id=profile.outcomes[0].outcome_id,
            source_group_ids=(),
            cadence_id=profile.default_cadence_id,
            requested_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC),
        )
        request = IntelligenceBuildPlanRequestV1Alpha2(**request_material)
        with pytest.raises(ValueError):
            await planner.prepare(request, profile=foreign, pack=_compiled_pack())
