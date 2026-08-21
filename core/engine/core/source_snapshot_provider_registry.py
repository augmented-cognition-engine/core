"""Fail-closed discovery of installed source-snapshot capability providers."""

from __future__ import annotations

import os
from importlib import metadata
from typing import Iterable

from ace.application.source_snapshot_provider import (
    SOURCE_SNAPSHOT_CAPABILITY,
    SOURCE_SNAPSHOT_CONTRACT,
    SourceSnapshotProvider,
    validate_source_snapshot_provider_registration,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP = "ace.source_snapshot_providers"


class SourceSnapshotProviderRegistryError(RuntimeError):
    """Installed source-snapshot provider material is invalid or ambiguous."""


_providers: dict[str, SourceSnapshotProvider] = {}
_artifacts: dict[str, CapabilityArtifactIdentityV1Alpha1] = {}
_contract_claims: dict[tuple[str, str], str] = {}
_loaded = False
_load_error: SourceSnapshotProviderRegistryError | None = None


def register_source_snapshot_provider(provider: SourceSnapshotProvider) -> SourceSnapshotProvider:
    """Register one exact provider implementation, rejecting every ambiguity."""

    try:
        artifact = validate_source_snapshot_provider_registration(provider)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SourceSnapshotProviderRegistryError(str(exc)) from exc
    implementation_id = artifact.implementation_id
    if implementation_id in _providers:
        raise SourceSnapshotProviderRegistryError(
            f"multiple source snapshot providers claim implementation: {implementation_id}"
        )
    claim = (artifact.capability, artifact.contract)
    if claim in _contract_claims:
        raise SourceSnapshotProviderRegistryError(
            f"ambiguous source snapshot providers claim capability contract: {artifact.capability} {artifact.contract}"
        )
    _providers[implementation_id] = provider
    _artifacts[implementation_id] = artifact
    _contract_claims[claim] = implementation_id
    return provider


def load_installed_source_snapshot_providers(entry_points: Iterable | None = None) -> tuple[str, ...]:
    """Load the dedicated provider group once; the naked kernel loads nothing."""

    global _load_error, _loaded
    if _loaded:
        if _load_error is not None:
            raise _load_error
        return tuple(sorted(_providers))
    _loaded = True
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        return ()
    installed = (
        metadata.entry_points(group=SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP)
        if entry_points is None
        else entry_points
    )
    prior_providers = dict(_providers)
    prior_artifacts = dict(_artifacts)
    prior_claims = dict(_contract_claims)
    current_name = "(discovery)"
    try:
        for entry_point in sorted(installed, key=lambda item: item.name):
            current_name = entry_point.name
            loaded = entry_point.load()
            provider = loaded() if isinstance(loaded, type) else loaded
            register_source_snapshot_provider(provider)
    except SourceSnapshotProviderRegistryError as exc:
        _providers.clear()
        _providers.update(prior_providers)
        _artifacts.clear()
        _artifacts.update(prior_artifacts)
        _contract_claims.clear()
        _contract_claims.update(prior_claims)
        _load_error = exc
        raise
    except Exception as exc:
        _providers.clear()
        _providers.update(prior_providers)
        _artifacts.clear()
        _artifacts.update(prior_artifacts)
        _contract_claims.clear()
        _contract_claims.update(prior_claims)
        _load_error = SourceSnapshotProviderRegistryError(f"source snapshot provider failed to load: {current_name}")
        raise _load_error from exc
    return tuple(sorted(_providers))


def resolve_source_snapshot_provider() -> SourceSnapshotProvider | None:
    load_installed_source_snapshot_providers()
    implementation_id = _contract_claims.get((SOURCE_SNAPSHOT_CAPABILITY, SOURCE_SNAPSHOT_CONTRACT))
    if implementation_id is None:
        return None
    provider = _providers[implementation_id]
    try:
        artifact = validate_source_snapshot_provider_registration(provider)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SourceSnapshotProviderRegistryError(str(exc)) from exc
    if artifact != _artifacts[implementation_id] or artifact.implementation_id != implementation_id:
        raise SourceSnapshotProviderRegistryError(
            f"source snapshot provider identity drifted after registration: {implementation_id}"
        )
    return provider


def _reset_source_snapshot_provider_registry_for_tests() -> None:
    global _load_error, _loaded
    _providers.clear()
    _artifacts.clear()
    _contract_claims.clear()
    _loaded = False
    _load_error = None


__all__ = [
    "SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP",
    "SourceSnapshotProviderRegistryError",
    "load_installed_source_snapshot_providers",
    "register_source_snapshot_provider",
    "resolve_source_snapshot_provider",
]
