"""Discover and verify installed inert Domain Pack artifacts without imports.

The resolver reads only distribution-declared package data. It never imports a
Domain Pack, loads an entry point, executes pack code, or treats a wheel version
as the Pack version. Every result is recompiled and re-conformed from bytes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Iterable, Protocol

from pydantic import ValidationError

from ace.intelligence.conformance import run_domain_pack_conformance
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.conformance import DomainPackConformanceReceiptV1
from ace.intelligence.contracts.pack import CompiledDomainPackV1, DomainPackManifestV1
from ace.intelligence.packs.compiler import (
    CompiledPackResultV1,
    PackCompilationError,
    compile_pack_document_with_report,
    validate_compiled_pack_set,
)
from ace.intelligence.packs.diagnostics import StablePackCompilationResultV1

ACTIVATION_GOLDEN_FIXTURE_PATH = PurePosixPath("conformance/activation_golden_fixture.json")
MAX_MANIFEST_BYTES = 1_000_000


class InstalledPackArtifactError(RuntimeError):
    """Installed Pack bytes or exact provenance failed closed."""


class InstalledDistribution(Protocol):
    @property
    def files(self): ...

    @property
    def metadata(self): ...

    @property
    def version(self) -> str: ...

    def locate_file(self, path) -> Path: ...


@dataclass(frozen=True, slots=True)
class InstalledCompiledPackArtifact:
    """One recompiled, passing, immutable installed Pack artifact."""

    distribution: str
    distribution_version: str
    manifest_resource_path: str
    pack: CompiledDomainPackV1
    compilation: StablePackCompilationResultV1
    conformance_receipts: tuple[DomainPackConformanceReceiptV1, ...]


@dataclass(frozen=True, slots=True)
class InstalledDomainPackPreview:
    """Validated installed manifest material that grants no activation authority."""

    distribution: str
    distribution_version: str
    manifest_resource_path: str
    manifest_digest: str
    manifest: DomainPackManifestV1


@dataclass(frozen=True, slots=True)
class _InstalledPackRoot:
    """Validated manifest identity whose activation material remains unloaded."""

    distribution: InstalledDistribution
    distribution_name: str
    distribution_version: str
    declared: dict[str, object]
    manifest_path: PurePosixPath
    manifest_document: bytes
    manifest: DomainPackManifestV1


def _distribution_name(distribution: InstalledDistribution) -> str:
    value = distribution.metadata.get("Name")
    if not isinstance(value, str) or not value.strip():
        raise InstalledPackArtifactError("installed distribution omitted its canonical name")
    return value.strip()


def _declared_paths(distribution: InstalledDistribution) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in distribution.files or ():
        normalized = str(value).replace("\\", "/")
        if normalized in result:
            raise InstalledPackArtifactError("installed distribution declares one resource path more than once")
        result[normalized] = value
    return result


def _manifest_paths(declared: dict[str, object]) -> tuple[object, ...]:
    matches = []
    for normalized, original in declared.items():
        path = PurePosixPath(normalized)
        if len(path.parts) == 3 and path.parts[0] == "domain_packs" and path.name == "manifest.json":
            matches.append(original)
    return tuple(sorted(matches, key=str))


def _safe_bytes(
    *,
    distribution: InstalledDistribution,
    declared: dict[str, object],
    resource_path: PurePosixPath,
    label: str,
) -> bytes:
    original = declared.get(resource_path.as_posix())
    if original is None:
        raise InstalledPackArtifactError(f"installed Pack omitted declared {label}: {resource_path}")
    try:
        distribution_root = Path(distribution.locate_file(""))
        path = Path(distribution.locate_file(original))
        root = distribution_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise InstalledPackArtifactError(f"installed Pack {label} escaped its distribution root")
        current = path
        while current != distribution_root and current != current.parent:
            if current.is_symlink():
                raise InstalledPackArtifactError(f"installed Pack {label} uses a symbolic link")
            current = current.parent
        if not path.is_file():
            raise InstalledPackArtifactError(f"installed Pack {label} is not a regular file")
        return path.read_bytes()
    except InstalledPackArtifactError:
        raise
    except OSError as exc:
        raise InstalledPackArtifactError(f"installed Pack {label} is unreadable") from exc


def _manifest(bytes_value: bytes) -> DomainPackManifestV1:
    if not bytes_value or len(bytes_value) > MAX_MANIFEST_BYTES:
        raise InstalledPackArtifactError("installed Pack manifest exceeded its bounded size")
    try:
        return DomainPackManifestV1.model_validate(json.loads(bytes_value))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise InstalledPackArtifactError("installed Pack manifest failed exact validation") from exc


def _validate_provenance(
    *,
    compiled: CompiledPackResultV1,
    receipt: DomainPackConformanceReceiptV1,
) -> None:
    pack = compiled.pack
    exact = DomainPackConformanceReceiptV1.model_validate(receipt.model_dump(mode="python"))
    if not exact.passed:
        raise InstalledPackArtifactError("installed Pack activation conformance did not pass")
    if (
        exact.pack_id != pack.metadata.pack_id
        or exact.pack_version != pack.metadata.version
        or exact.compiled_pack_id != pack.compiled_pack_id
        or exact.pack_digest != pack.pack_digest
        or exact.manifest_contract != pack.manifest_contract
        or exact.compiler_contract != pack.compiler_contract
        or exact.intelligence_contract != pack.intelligence_contract
        or exact.compatibility_status != compiled.compatibility.status
        or exact.compilation_result_id != compiled.compilation.result_id
        or exact.compilation_result_digest != compiled.compilation.result_digest
    ):
        raise InstalledPackArtifactError("installed Pack conformance provenance crossed exact compilation material")


def _load_artifact(
    *,
    root: _InstalledPackRoot,
) -> InstalledCompiledPackArtifact:
    pack_root = root.manifest_path.parent
    resources = {
        item.path: _safe_bytes(
            distribution=root.distribution,
            declared=root.declared,
            resource_path=pack_root / item.path,
            label=f"resource {item.resource_id}",
        )
        for item in root.manifest.resources
    }
    fixture_document = _safe_bytes(
        distribution=root.distribution,
        declared=root.declared,
        resource_path=pack_root / ACTIVATION_GOLDEN_FIXTURE_PATH,
        label="activation golden fixture",
    )
    try:
        compiled = compile_pack_document_with_report(root.manifest_document, resources)
        receipt = run_domain_pack_conformance(
            manifest_document=root.manifest_document,
            resources=resources,
            fixture_document=fixture_document,
        )
        _validate_provenance(compiled=compiled, receipt=receipt)
    except InstalledPackArtifactError:
        raise
    except (PackCompilationError, ValidationError, TypeError, ValueError) as exc:
        raise InstalledPackArtifactError("installed Pack compilation or activation conformance failed") from exc
    return InstalledCompiledPackArtifact(
        distribution=root.distribution_name,
        distribution_version=root.distribution_version,
        manifest_resource_path=root.manifest_path.as_posix(),
        pack=compiled.pack,
        compilation=compiled.compilation,
        conformance_receipts=(receipt,),
    )


def _exact_distributions(installed: Iterable[InstalledDistribution]) -> tuple[InstalledDistribution, ...]:
    """Collapse one dist-info enumerated more than once into one installed distribution.

    A duplicated ``sys.path`` entry (a re-prepended site-packages directory)
    makes ``importlib.metadata.distributions()`` yield the same dist-info path
    twice. That is one installed Pack, not an ambiguous pair, so entries whose
    canonical distribution name *and* resolved dist-info path are identical
    are kept once. Entries sharing a name across genuinely different paths,
    or lacking a name or path, are retained so downstream ambiguity still
    fails closed.
    """

    keyed: dict[tuple[str, str], InstalledDistribution] = {}
    unkeyed: list[InstalledDistribution] = []
    for distribution in installed:
        try:
            name = _distribution_name(distribution)
        except Exception:  # noqa: BLE001 - an unnamed entry is retained for the strict path below
            unkeyed.append(distribution)
            continue
        dist_info = getattr(distribution, "_path", None)
        if not name or dist_info is None:
            unkeyed.append(distribution)
            continue
        try:
            resolved = str(Path(str(dist_info)).resolve())
        except OSError:
            unkeyed.append(distribution)
            continue
        keyed.setdefault((re.sub(r"[-_.]+", "-", name).lower(), resolved), distribution)
    return tuple(keyed.values()) + tuple(unkeyed)


def _index_installed_pack_roots(
    distributions: Iterable[InstalledDistribution] | None = None,
) -> tuple[_InstalledPackRoot, ...]:
    """Index manifest identities without activating unrelated installed Packs."""

    installed = metadata.distributions() if distributions is None else distributions
    roots: list[_InstalledPackRoot] = []
    seen_roots: set[tuple[str, str]] = set()
    seen_pack_ids: set[str] = set()
    for distribution in sorted(_exact_distributions(installed), key=lambda item: _distribution_name(item).lower()):
        name = _distribution_name(distribution)
        declared = _declared_paths(distribution)
        for manifest_path_value in _manifest_paths(declared):
            manifest_path = PurePosixPath(str(manifest_path_value).replace("\\", "/"))
            root_key = (name.lower(), manifest_path.parent.as_posix())
            if root_key in seen_roots:
                raise InstalledPackArtifactError("installed Pack root is declared more than once")
            seen_roots.add(root_key)
            manifest_document = _safe_bytes(
                distribution=distribution,
                declared=declared,
                resource_path=manifest_path,
                label="manifest",
            )
            manifest = _manifest(manifest_document)
            if manifest.metadata.pack_id in seen_pack_ids:
                raise InstalledPackArtifactError("installed Pack identifiers are ambiguous")
            seen_pack_ids.add(manifest.metadata.pack_id)
            roots.append(
                _InstalledPackRoot(
                    distribution=distribution,
                    distribution_name=name,
                    distribution_version=str(distribution.version),
                    declared=declared,
                    manifest_path=manifest_path,
                    manifest_document=manifest_document,
                    manifest=manifest,
                )
            )
    return tuple(sorted(roots, key=lambda item: item.manifest.metadata.pack_id))


def discover_installed_domain_pack_previews(
    distributions: Iterable[InstalledDistribution] | None = None,
) -> tuple[InstalledDomainPackPreview, ...]:
    """List exact installed manifests without compiling, conforming, or activating Packs."""

    return tuple(
        InstalledDomainPackPreview(
            distribution=item.distribution_name,
            distribution_version=item.distribution_version,
            manifest_resource_path=item.manifest_path.as_posix(),
            manifest_digest=f"sha256:{sha256(item.manifest_document).hexdigest()}",
            manifest=DomainPackManifestV1.model_validate(item.manifest.model_dump(mode="python")),
        )
        for item in _index_installed_pack_roots(distributions)
    )


class InstalledCompiledPackArtifactResolver:
    """Exact immutable resolver over one freshly discovered installed set."""

    def __init__(
        self,
        artifacts: Iterable[InstalledCompiledPackArtifact] = (),
        *,
        roots: Iterable[_InstalledPackRoot] = (),
    ) -> None:
        exact = tuple(artifacts)
        indexed = tuple(roots)
        try:
            validate_compiled_pack_set([item.pack for item in exact])
            for artifact in exact:
                pack = CompiledDomainPackV1.model_validate(artifact.pack.model_dump(mode="python"))
                compilation = StablePackCompilationResultV1.model_validate(
                    artifact.compilation.model_dump(mode="python")
                )
                if (
                    compilation.compiled_pack_id != pack.compiled_pack_id
                    or compilation.pack_digest != pack.pack_digest
                    or compilation.manifest_contract != pack.manifest_contract
                    or compilation.compiler_contract != pack.compiler_contract
                    or compilation.intelligence_contract != pack.intelligence_contract
                    or len(artifact.conformance_receipts) != 1
                ):
                    raise InstalledPackArtifactError("installed Pack resolver artifact crossed exact compilation")
                receipt = DomainPackConformanceReceiptV1.model_validate(
                    artifact.conformance_receipts[0].model_dump(mode="python")
                )
                if (
                    not receipt.passed
                    or receipt.pack_id != pack.metadata.pack_id
                    or receipt.pack_version != pack.metadata.version
                    or receipt.compiled_pack_id != pack.compiled_pack_id
                    or receipt.pack_digest != pack.pack_digest
                    or receipt.compilation_result_id != compilation.result_id
                    or receipt.compilation_result_digest != compilation.result_digest
                ):
                    raise InstalledPackArtifactError("installed Pack resolver artifact crossed exact conformance")
        except InstalledPackArtifactError:
            raise
        except (PackCompilationError, ValidationError, AttributeError, TypeError, ValueError) as exc:
            raise InstalledPackArtifactError("installed Pack resolver artifacts failed exact validation") from exc
        root_ids = [item.manifest.metadata.pack_id for item in indexed]
        if len(root_ids) != len(set(root_ids)) or set(root_ids).intersection(
            item.pack.metadata.pack_id for item in exact
        ):
            raise InstalledPackArtifactError("installed Pack identifiers are ambiguous")
        self._artifacts = {item.pack.metadata.pack_id: item for item in exact}
        self._roots = {item.manifest.metadata.pack_id: item for item in indexed}

    @classmethod
    def discover(
        cls,
        distributions: Iterable[InstalledDistribution] | None = None,
    ) -> "InstalledCompiledPackArtifactResolver":
        return cls(roots=_index_installed_pack_roots(distributions))

    async def resolve_exact(self, *, reference: CompiledPackRefV1) -> InstalledCompiledPackArtifact | None:
        artifact = self._artifacts.get(reference.pack_id)
        if artifact is None:
            root = self._roots.get(reference.pack_id)
            if root is None or root.manifest.metadata.version != reference.pack_version:
                return None
            artifact = _load_artifact(root=root)
        pack = artifact.pack
        if (
            pack.metadata.version != reference.pack_version
            or pack.compiled_pack_id != reference.compiled_pack_id
            or pack.pack_digest != reference.pack_digest
        ):
            return None
        return InstalledCompiledPackArtifact(
            distribution=artifact.distribution,
            distribution_version=artifact.distribution_version,
            manifest_resource_path=artifact.manifest_resource_path,
            pack=CompiledDomainPackV1.model_validate(pack.model_dump(mode="python")),
            compilation=StablePackCompilationResultV1.model_validate(artifact.compilation.model_dump(mode="python")),
            conformance_receipts=tuple(
                DomainPackConformanceReceiptV1.model_validate(item.model_dump(mode="python"))
                for item in artifact.conformance_receipts
            ),
        )

    async def load_exact(self, *, reference: CompiledPackRefV1) -> CompiledDomainPackV1 | None:
        artifact = await self.resolve_exact(reference=reference)
        return None if artifact is None else artifact.pack


__all__ = [
    "ACTIVATION_GOLDEN_FIXTURE_PATH",
    "InstalledCompiledPackArtifact",
    "InstalledCompiledPackArtifactResolver",
    "InstalledDomainPackPreview",
    "InstalledPackArtifactError",
    "discover_installed_domain_pack_previews",
]
