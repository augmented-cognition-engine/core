from __future__ import annotations

import pytest

import core.engine.core.source_snapshot_provider_registry as registry
from ace.application.source_snapshot_provider import (
    SOURCE_SNAPSHOT_CAPABILITY,
    SOURCE_SNAPSHOT_CONTRACT,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from core.engine.core.source_snapshot_provider_registry import (
    SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP,
    SourceSnapshotProviderRegistryError,
    load_installed_source_snapshot_providers,
    register_source_snapshot_provider,
    resolve_source_snapshot_provider,
)

pytestmark = pytest.mark.unit


def _identity(implementation_id: str = "fixture_provider_one", **overrides) -> CapabilityArtifactIdentityV1Alpha1:
    material = {
        "capability": SOURCE_SNAPSHOT_CAPABILITY,
        "contract": SOURCE_SNAPSHOT_CONTRACT,
        "implementation_id": implementation_id,
        "implementation_version": "1.0.0",
        "artifact_digest": "sha256:" + "a" * 64,
    }
    material.update(overrides)
    return CapabilityArtifactIdentityV1Alpha1(**material)


class _FixtureProvider:
    def __init__(self, identity: CapabilityArtifactIdentityV1Alpha1) -> None:
        self.artifact_identity = identity

    async def snapshot(self, request):
        del request
        raise AssertionError("registry tests never take a snapshot")


class _FakeEntryPoint:
    def __init__(self, name: str, loaded: object) -> None:
        self.name = name
        self.load_count = 0
        self._loaded = loaded

    def load(self) -> object:
        self.load_count += 1
        if isinstance(self._loaded, BaseException):
            raise self._loaded
        return self._loaded


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    registry._reset_source_snapshot_provider_registry_for_tests()
    yield
    registry._reset_source_snapshot_provider_registry_for_tests()


def test_direct_registration_resolves_the_registered_provider() -> None:
    provider = _FixtureProvider(_identity())

    assert register_source_snapshot_provider(provider) is provider
    assert load_installed_source_snapshot_providers(entry_points=()) == ("fixture_provider_one",)
    assert resolve_source_snapshot_provider() is provider


def test_resolution_returns_none_when_nothing_claims_the_contract() -> None:
    assert load_installed_source_snapshot_providers(entry_points=()) == ()
    assert resolve_source_snapshot_provider() is None


def test_registration_rejects_the_wrong_capability_or_contract() -> None:
    wrong_contract = _FixtureProvider(_identity(contract="ace.source.other/v1alpha1"))
    wrong_capability = _FixtureProvider(_identity(capability="other_capability"))

    with pytest.raises(SourceSnapshotProviderRegistryError, match="wrong capability contract"):
        register_source_snapshot_provider(wrong_contract)
    with pytest.raises(SourceSnapshotProviderRegistryError, match="wrong capability contract"):
        register_source_snapshot_provider(wrong_capability)
    assert load_installed_source_snapshot_providers(entry_points=()) == ()


def test_registration_rejects_missing_identity_and_sync_snapshot() -> None:
    class _NoIdentity:
        async def snapshot(self, request):
            del request

    class _SyncSnapshot:
        artifact_identity = _identity("fixture_sync_provider")

        def snapshot(self, request):
            del request

    with pytest.raises(SourceSnapshotProviderRegistryError, match="artifact identity"):
        register_source_snapshot_provider(_NoIdentity())
    with pytest.raises(SourceSnapshotProviderRegistryError, match="async snapshot"):
        register_source_snapshot_provider(_SyncSnapshot())


def test_duplicate_implementation_id_is_rejected() -> None:
    register_source_snapshot_provider(_FixtureProvider(_identity()))

    with pytest.raises(SourceSnapshotProviderRegistryError, match="multiple source snapshot providers"):
        register_source_snapshot_provider(_FixtureProvider(_identity()))


def test_ambiguous_claim_on_the_same_capability_contract_is_rejected() -> None:
    first = _FixtureProvider(_identity("fixture_provider_one"))
    register_source_snapshot_provider(first)

    with pytest.raises(SourceSnapshotProviderRegistryError, match="ambiguous source snapshot providers"):
        register_source_snapshot_provider(_FixtureProvider(_identity("fixture_provider_two")))

    assert load_installed_source_snapshot_providers(entry_points=()) == ("fixture_provider_one",)
    assert resolve_source_snapshot_provider() is first


def test_installed_discovery_reads_the_dedicated_entry_point_group(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ClassProvider:
        artifact_identity = _identity("installed_class_provider")

        async def snapshot(self, request):
            del request
            raise AssertionError("registry tests never take a snapshot")

    requested_groups: list[str] = []

    def fake_entry_points(*, group: str):
        requested_groups.append(group)
        return (_FakeEntryPoint("installed_class_provider", _ClassProvider),)

    monkeypatch.setattr(registry.metadata, "entry_points", fake_entry_points)

    assert load_installed_source_snapshot_providers() == ("installed_class_provider",)
    assert requested_groups == [SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP]
    resolved = resolve_source_snapshot_provider()
    assert isinstance(resolved, _ClassProvider)


def test_loaded_ids_are_deterministic_and_the_load_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    entry_point = _FakeEntryPoint("installed_provider", _FixtureProvider(_identity("installed_provider")))

    first = load_installed_source_snapshot_providers(entry_points=(entry_point,))

    monkeypatch.setattr(
        registry.metadata,
        "entry_points",
        lambda **kwargs: pytest.fail("a completed load must never rescan installed entry points"),
    )
    assert first == ("installed_provider",)
    assert load_installed_source_snapshot_providers() == first
    assert entry_point.load_count == 1


def test_entry_points_load_in_name_order_and_registry_errors_roll_back() -> None:
    bad = _FakeEntryPoint("a_bad", _FixtureProvider(_identity("a_bad", contract="ace.source.other/v1alpha1")))
    good = _FakeEntryPoint("z_good", _FixtureProvider(_identity("z_good")))

    with pytest.raises(SourceSnapshotProviderRegistryError, match="wrong capability contract"):
        load_installed_source_snapshot_providers(entry_points=(good, bad))

    assert bad.load_count == 1
    assert good.load_count == 0
    assert registry._providers == {}
    assert registry._contract_claims == {}


def test_naked_kernel_loads_nothing_when_extensions_are_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    poison = _FakeEntryPoint("never_loaded", RuntimeError("the naked kernel must not load extensions"))

    assert load_installed_source_snapshot_providers(entry_points=(poison,)) == ()
    assert poison.load_count == 0
    assert resolve_source_snapshot_provider() is None


def test_load_exception_rolls_back_partial_state_and_re_raises_the_cached_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _FixtureProvider(_identity("prior_provider", contract=SOURCE_SNAPSHOT_CONTRACT))
    register_source_snapshot_provider(prior)
    boom = _FakeEntryPoint("b_boom", RuntimeError("broken distribution"))

    with pytest.raises(SourceSnapshotProviderRegistryError, match="failed to load: b_boom") as first:
        load_installed_source_snapshot_providers(entry_points=(boom,))

    assert registry._providers == {"prior_provider": prior}
    assert registry._contract_claims == {(SOURCE_SNAPSHOT_CAPABILITY, SOURCE_SNAPSHOT_CONTRACT): "prior_provider"}

    monkeypatch.setattr(
        registry.metadata,
        "entry_points",
        lambda **kwargs: pytest.fail("a failed load must stay failed without rescanning"),
    )
    with pytest.raises(SourceSnapshotProviderRegistryError) as second:
        load_installed_source_snapshot_providers()
    assert second.value is first.value
    with pytest.raises(SourceSnapshotProviderRegistryError) as via_resolve:
        resolve_source_snapshot_provider()
    assert via_resolve.value is first.value
    assert boom.load_count == 1


def test_reset_restores_a_clean_registry() -> None:
    provider = _FixtureProvider(_identity())
    register_source_snapshot_provider(provider)
    assert load_installed_source_snapshot_providers(entry_points=()) == ("fixture_provider_one",)
    assert resolve_source_snapshot_provider() is provider

    registry._reset_source_snapshot_provider_registry_for_tests()

    assert load_installed_source_snapshot_providers(entry_points=()) == ()
    assert resolve_source_snapshot_provider() is None
    assert register_source_snapshot_provider(_FixtureProvider(_identity())) is not provider


def test_resolution_fails_closed_when_identity_is_tampered_after_registration() -> None:
    # Registration accepted one exact artifact identity; a provider whose
    # declared identity later changes is no longer the registered artifact,
    # so resolution must refuse it rather than serve mismatched material.
    provider = _FixtureProvider(_identity())
    register_source_snapshot_provider(provider)
    assert load_installed_source_snapshot_providers(entry_points=()) == ("fixture_provider_one",)

    provider.artifact_identity = _identity(
        "tampered_provider",
        artifact_digest="sha256:" + "f" * 64,
    )

    with pytest.raises(SourceSnapshotProviderRegistryError):
        resolve_source_snapshot_provider()
