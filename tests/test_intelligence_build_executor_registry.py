from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from core.engine.core.intelligence_build import _InstalledIntelligenceBuildExecutor
from core.engine.core.intelligence_build_executor_registry import (
    IntelligenceBuildExecutorRegistryError,
    _reset_intelligence_build_executor_registry_for_tests,
    load_installed_intelligence_build_executors,
    register_intelligence_build_executor,
    resolve_intelligence_build_executor,
)

pytestmark = pytest.mark.unit


class _Executor:
    profile_id = "intelligence_onboarding_profile:fixture"

    async def start(self, build, host_services):
        del host_services
        raise AssertionError("not executed by registry tests")


@dataclass(frozen=True)
class _EntryPoint:
    name: str
    value: object

    def load(self):
        return self.value


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    _reset_intelligence_build_executor_registry_for_tests()
    yield
    _reset_intelligence_build_executor_registry_for_tests()


def test_dedicated_entry_point_loads_and_resolves_exact_profile() -> None:
    assert load_installed_intelligence_build_executors((_EntryPoint("fixture", _Executor),)) == (_Executor.profile_id,)
    assert isinstance(resolve_intelligence_build_executor(_Executor.profile_id), _Executor)
    assert resolve_intelligence_build_executor("intelligence_onboarding_profile:unknown") is None


def test_duplicate_profile_claim_fails_closed() -> None:
    register_intelligence_build_executor(profile_id=_Executor.profile_id, executor=_Executor())
    with pytest.raises(IntelligenceBuildExecutorRegistryError, match="multiple"):
        register_intelligence_build_executor(profile_id=_Executor.profile_id, executor=_Executor())


def test_duplicate_installed_claim_remains_failed_closed() -> None:
    entries = (_EntryPoint("one", _Executor), _EntryPoint("two", _Executor))
    with pytest.raises(IntelligenceBuildExecutorRegistryError, match="multiple"):
        load_installed_intelligence_build_executors(entries)
    with pytest.raises(IntelligenceBuildExecutorRegistryError, match="multiple"):
        resolve_intelligence_build_executor(_Executor.profile_id)


@pytest.mark.parametrize("profile_id", ["", "has spaces", "../escape", "x" * 241])
def test_invalid_profile_identity_is_rejected(profile_id: str) -> None:
    with pytest.raises(IntelligenceBuildExecutorRegistryError, match="invalid"):
        register_intelligence_build_executor(profile_id=profile_id, executor=_Executor())


def test_naked_kernel_does_not_load_installed_executors(monkeypatch) -> None:
    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    assert load_installed_intelligence_build_executors((_EntryPoint("fixture", _Executor),)) == ()
    assert resolve_intelligence_build_executor(_Executor.profile_id) is None


def test_sync_executor_is_rejected() -> None:
    class _SyncExecutor:
        def start(self, build):
            return build

    with pytest.raises(IntelligenceBuildExecutorRegistryError, match="async start"):
        register_intelligence_build_executor(profile_id=_Executor.profile_id, executor=_SyncExecutor())


@pytest.mark.anyio
async def test_installed_dispatcher_selects_only_the_authorized_profile(monkeypatch) -> None:
    marker = object()

    class _ReturningExecutor:
        async def start(self, build, host_services):
            assert build.request.profile_id == _Executor.profile_id
            assert host_services is marker
            return marker

    monkeypatch.setattr(
        "core.engine.core.intelligence_build.resolve_intelligence_build_executor",
        lambda profile_id: _ReturningExecutor() if profile_id == _Executor.profile_id else None,
    )
    build = SimpleNamespace(request=SimpleNamespace(profile_id=_Executor.profile_id))
    assert await _InstalledIntelligenceBuildExecutor().start(build, marker) is marker
