"""Discover inert Intelligence onboarding profiles from installed distributions.

The host recognizes a validated resource shape, never a domain or package name.
Domain distributions remain JSON-only and do not gain executable entry points.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Iterable, Protocol

from pydantic import ValidationError

from ace.application import IntelligenceOnboardingProfileV1Alpha1

MAX_ONBOARDING_PROFILE_BYTES = 1_000_000
ONBOARDING_PROFILE_FILENAME = "onboarding_profile.json"


class InstalledIntelligenceCatalogError(RuntimeError):
    """Installed catalog material was unreadable, invalid, or conflicting."""


class InstalledDistribution(Protocol):
    @property
    def files(self): ...

    @property
    def metadata(self): ...

    @property
    def version(self) -> str: ...

    def locate_file(self, path) -> Path: ...


@dataclass(frozen=True, slots=True)
class InstalledOnboardingProfile:
    distribution: str
    distribution_version: str
    resource_path: str
    profile: IntelligenceOnboardingProfileV1Alpha1


def _distribution_name(distribution: InstalledDistribution) -> str:
    value = distribution.metadata.get("Name")
    if not isinstance(value, str) or not value.strip():
        raise InstalledIntelligenceCatalogError("installed distribution omitted its canonical name")
    return value.strip()


def _profile_paths(distribution: InstalledDistribution) -> tuple:
    paths = []
    for candidate in distribution.files or ():
        normalized = PurePosixPath(str(candidate).replace("\\", "/"))
        if (
            normalized.name == ONBOARDING_PROFILE_FILENAME
            and "domain_packs" in normalized.parts
            and ".dist-info" not in normalized.as_posix()
        ):
            paths.append(candidate)
    return tuple(sorted(paths, key=str))


def _load_profile(*, distribution: InstalledDistribution, candidate, name: str) -> InstalledOnboardingProfile:
    resource_path = str(candidate).replace("\\", "/")
    try:
        path = Path(distribution.locate_file(candidate))
        payload = path.read_bytes()
    except OSError as exc:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile is unreadable: {name}:{resource_path}"
        ) from exc
    if not payload or len(payload) > MAX_ONBOARDING_PROFILE_BYTES:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile exceeded its bounded size: {name}:{resource_path}"
        )
    try:
        json.loads(payload)
        profile = IntelligenceOnboardingProfileV1Alpha1.model_validate_json(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile failed exact validation: {name}:{resource_path}"
        ) from exc
    return InstalledOnboardingProfile(
        distribution=name,
        distribution_version=str(distribution.version),
        resource_path=resource_path,
        profile=profile,
    )


def discover_installed_onboarding_profiles(
    distributions: Iterable[InstalledDistribution] | None = None,
) -> tuple[InstalledOnboardingProfile, ...]:
    """Return validated inert profiles with deterministic provenance and ordering."""

    installed = metadata.distributions() if distributions is None else distributions
    discovered: list[InstalledOnboardingProfile] = []
    for distribution in sorted(installed, key=lambda item: _distribution_name(item).lower()):
        name = _distribution_name(distribution)
        for candidate in _profile_paths(distribution):
            discovered.append(_load_profile(distribution=distribution, candidate=candidate, name=name))

    by_id: dict[str, InstalledOnboardingProfile] = {}
    for item in discovered:
        incumbent = by_id.get(item.profile.profile_id)
        if incumbent is None:
            by_id[item.profile.profile_id] = item
            continue
        if incumbent.profile.profile_digest != item.profile.profile_digest:
            raise InstalledIntelligenceCatalogError(
                f"installed onboarding profile identity conflicts across distributions: {item.profile.profile_id}"
            )
    return tuple(sorted(by_id.values(), key=lambda item: (item.profile.domain_label or "", item.profile.profile_id)))


__all__ = [
    "InstalledIntelligenceCatalogError",
    "InstalledOnboardingProfile",
    "IntelligenceOnboardingProfileV1Alpha1",
    "discover_installed_onboarding_profiles",
]
