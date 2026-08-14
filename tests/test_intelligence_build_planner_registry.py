from __future__ import annotations

from dataclasses import dataclass

import pytest

from ace.application.intelligence_build_planning import (
    INTELLIGENCE_BUILD_PLANNER_CONTRACT,
    INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from core.engine.core.intelligence_build_planner_registry import (
    IntelligenceBuildPlannerRegistryError,
    _reset_intelligence_build_planner_registry_for_tests,
    load_installed_intelligence_build_planners,
    register_intelligence_build_planner,
    resolve_intelligence_build_planner,
)

pytestmark = pytest.mark.unit


class _Planner:
    profile_id = "intelligence_onboarding_profile:fixture"
    pack_reference = CompiledPackRefV1(
        pack_id="neutral_measurement",
        pack_version="1.0.0",
        compiled_pack_id="pack_ir:" + "a" * 32,
        pack_digest="sha256:" + "a" * 64,
    )
    artifact_identity = CapabilityArtifactIdentityV1Alpha1(
        capability=INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
        contract=INTELLIGENCE_BUILD_PLANNER_CONTRACT,
        implementation_id="fixture_planner",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "b" * 64,
    )

    async def prepare(self, request, *, profile, pack):
        del request, profile, pack
        raise AssertionError("registry tests never invoke planning")


@dataclass(frozen=True)
class _EntryPoint:
    name: str
    value: object

    def load(self):
        return self.value


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    _reset_intelligence_build_planner_registry_for_tests()
    yield
    _reset_intelligence_build_planner_registry_for_tests()


def test_dedicated_entry_point_loads_and_resolves_exact_profile() -> None:
    assert load_installed_intelligence_build_planners((_EntryPoint("fixture", _Planner),)) == (_Planner.profile_id,)
    assert isinstance(resolve_intelligence_build_planner(_Planner.profile_id), _Planner)
    assert resolve_intelligence_build_planner("intelligence_onboarding_profile:unknown") is None


def test_duplicate_profile_registration_and_installed_claim_fail_closed() -> None:
    register_intelligence_build_planner(profile_id=_Planner.profile_id, planner=_Planner())
    with pytest.raises(IntelligenceBuildPlannerRegistryError, match="multiple"):
        register_intelligence_build_planner(profile_id=_Planner.profile_id, planner=_Planner())

    _reset_intelligence_build_planner_registry_for_tests()
    with pytest.raises(IntelligenceBuildPlannerRegistryError, match="multiple"):
        load_installed_intelligence_build_planners((_EntryPoint("one", _Planner), _EntryPoint("two", _Planner)))
    with pytest.raises(IntelligenceBuildPlannerRegistryError, match="multiple"):
        resolve_intelligence_build_planner(_Planner.profile_id)


def test_naked_kernel_loads_no_planner(monkeypatch) -> None:
    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    assert load_installed_intelligence_build_planners((_EntryPoint("fixture", _Planner),)) == ()
    assert resolve_intelligence_build_planner(_Planner.profile_id) is None


def test_invalid_or_sync_planner_fails_closed() -> None:
    class _SyncPlanner(_Planner):
        def prepare(self, request, *, profile, pack):
            return request, profile, pack

    with pytest.raises(IntelligenceBuildPlannerRegistryError, match="async prepare"):
        register_intelligence_build_planner(profile_id=_Planner.profile_id, planner=_SyncPlanner())

    class _WrongArtifactPlanner(_Planner):
        artifact_identity = _Planner.artifact_identity.model_copy(update={"capability": "other_capability"})

    with pytest.raises(IntelligenceBuildPlannerRegistryError, match="wrong capability"):
        register_intelligence_build_planner(profile_id=_Planner.profile_id, planner=_WrongArtifactPlanner())
