"""Discover installed Solution Bundle manifests without imports.

Mirrors the installed Domain Pack resolver: discovery reads only
distribution-declared package data at ``solution_bundles/<dir>/bundle.json``,
validates the exact bytes into ``SolutionBundleManifestV1``, and never imports
bundle code, loads an entry point, or treats a wheel version as the bundle
version. Listing a manifest grants no activation authority; activation remains
the governed admission path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Iterable, Protocol

from pydantic import ValidationError

from ace.intelligence.contracts.solution_bundle import SolutionBundleManifestV1

MAX_BUNDLE_MANIFEST_BYTES = 1_000_000


class InstalledBundleArtifactError(RuntimeError):
    """Installed bundle bytes or exact provenance failed closed."""


class InstalledDistribution(Protocol):
    @property
    def files(self): ...

    @property
    def metadata(self): ...

    @property
    def version(self) -> str: ...

    def locate_file(self, path) -> Path: ...


@dataclass(frozen=True, slots=True)
class InstalledSolutionBundleArtifact:
    """One validated installed bundle manifest that grants no activation authority."""

    distribution: str
    distribution_version: str
    manifest_resource_path: str
    manifest_digest: str
    manifest: SolutionBundleManifestV1


def _distribution_name(distribution: InstalledDistribution) -> str:
    value = distribution.metadata.get("Name")
    if not isinstance(value, str) or not value.strip():
        raise InstalledBundleArtifactError("installed distribution omitted its canonical name")
    return value.strip()


def _declared_paths(distribution: InstalledDistribution) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in distribution.files or ():
        normalized = str(value).replace("\\", "/")
        if normalized in result:
            raise InstalledBundleArtifactError("installed distribution declares one resource path more than once")
        result[normalized] = value
    return result


def _bundle_manifest_paths(declared: dict[str, object]) -> tuple[object, ...]:
    matches = []
    for normalized, original in declared.items():
        path = PurePosixPath(normalized)
        if len(path.parts) == 3 and path.parts[0] == "solution_bundles" and path.name == "bundle.json":
            matches.append(original)
    return tuple(sorted(matches, key=str))


def _safe_bytes(
    *,
    distribution: InstalledDistribution,
    declared: dict[str, object],
    resource_path: PurePosixPath,
) -> bytes:
    original = declared.get(resource_path.as_posix())
    if original is None:
        raise InstalledBundleArtifactError(f"installed bundle omitted declared manifest: {resource_path}")
    try:
        distribution_root = Path(distribution.locate_file(""))
        path = Path(distribution.locate_file(original))
        root = distribution_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise InstalledBundleArtifactError("installed bundle manifest escaped its distribution root")
        current = path
        while current != distribution_root and current != current.parent:
            if current.is_symlink():
                raise InstalledBundleArtifactError("installed bundle manifest uses a symbolic link")
            current = current.parent
        if not path.is_file():
            raise InstalledBundleArtifactError("installed bundle manifest is not a regular file")
        return path.read_bytes()
    except InstalledBundleArtifactError:
        raise
    except OSError as exc:
        raise InstalledBundleArtifactError("installed bundle manifest is unreadable") from exc


def _manifest(document: bytes) -> SolutionBundleManifestV1:
    if not document or len(document) > MAX_BUNDLE_MANIFEST_BYTES:
        raise InstalledBundleArtifactError("installed bundle manifest exceeded its bounded size")
    try:
        return SolutionBundleManifestV1.model_validate(json.loads(document))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise InstalledBundleArtifactError("installed bundle manifest failed exact validation") from exc


def discover_installed_solution_bundle_manifests(
    distributions: Iterable[InstalledDistribution] | None = None,
) -> tuple[InstalledSolutionBundleArtifact, ...]:
    """List exact installed bundle manifests without importing or activating anything."""

    if distributions is None:
        from importlib import metadata

        distributions = metadata.distributions()
    artifacts: list[InstalledSolutionBundleArtifact] = []
    seen_roots: set[tuple[str, str]] = set()
    seen_bundle_ids: set[str] = set()
    for distribution in sorted(distributions, key=lambda item: _distribution_name(item).lower()):
        name = _distribution_name(distribution)
        declared = _declared_paths(distribution)
        for manifest_path_value in _bundle_manifest_paths(declared):
            manifest_path = PurePosixPath(str(manifest_path_value).replace("\\", "/"))
            root_key = (name.lower(), manifest_path.parent.as_posix())
            if root_key in seen_roots:
                raise InstalledBundleArtifactError("installed bundle root is declared more than once")
            seen_roots.add(root_key)
            document = _safe_bytes(
                distribution=distribution,
                declared=declared,
                resource_path=manifest_path,
            )
            manifest = _manifest(document)
            if manifest.bundle_id in seen_bundle_ids:
                raise InstalledBundleArtifactError("installed bundle identifiers are ambiguous")
            seen_bundle_ids.add(manifest.bundle_id)
            artifacts.append(
                InstalledSolutionBundleArtifact(
                    distribution=name,
                    distribution_version=str(distribution.version),
                    manifest_resource_path=manifest_path.as_posix(),
                    manifest_digest=f"sha256:{sha256(document).hexdigest()}",
                    manifest=manifest,
                )
            )
    return tuple(sorted(artifacts, key=lambda item: item.manifest.bundle_id))


__all__ = [
    "MAX_BUNDLE_MANIFEST_BYTES",
    "InstalledBundleArtifactError",
    "InstalledSolutionBundleArtifact",
    "discover_installed_solution_bundle_manifests",
]
