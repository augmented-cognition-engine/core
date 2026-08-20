"""PI11: checkout-free discovery of installed Solution Bundle manifests.

J1 installs the public bundle from distributions alone. Discovery reads only
distribution-declared package data at ``solution_bundles/<dir>/bundle.json``,
validates the exact bytes, and never imports bundle code or entry points.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

import pytest

from ace.application.installed_bundle_artifacts import (
    InstalledBundleArtifactError,
    discover_installed_solution_bundle_manifests,
)
from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    PolicyBindingV1,
    SolutionBundleManifestV1,
)

pytestmark = pytest.mark.unit


def _manifest_document(*, bundle_id: str = "demo_bundle") -> bytes:
    pack = CompiledPackRefV1(
        pack_id="demo_pack",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{'a' * 32}",
        pack_digest="sha256:" + "a" * 64,
    )
    manifest = SolutionBundleManifestV1(
        product_id="product:demo",
        bundle_id=bundle_id,
        bundle_version="1.0.0",
        pack=pack,
        overlay=CompiledOverlayV1(
            overlay_id="demo_overlay",
            version="1.0.0",
            pack_id=pack.pack_id,
            pack_version=pack.pack_version,
            pack_digest=pack.pack_digest,
            values=(),
        ),
        adapters=(
            AdapterBindingV1(adapter_id="demo-adapter", adapter_version="0.1.0", artifact_digest="sha256:" + "b" * 64),
        ),
        policy=PolicyBindingV1(policy_id="demo_policy", policy_version="1.0.0", policy_digest="sha256:" + "c" * 64),
    )
    return json.dumps(manifest.model_dump(mode="json")).encode("utf-8")


@dataclass
class _Metadata:
    name: str

    def get(self, key: str):
        return self.name if key == "Name" else None


class _Distribution:
    def __init__(self, root: Path, name: str, resources: dict[str, bytes], *, version: str = "0.1.0") -> None:
        self.root = root
        self.metadata = _Metadata(name)
        self.version = version
        self.files = tuple(PurePosixPath(path) for path in resources)
        for relative, payload in resources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def locate_file(self, path) -> Path:
        return self.root / str(path)

    @property
    def entry_points(self):
        raise AssertionError("installed bundle discovery must never inspect or execute entry points")


def test_discovers_declared_bundle_manifest_by_shape(tmp_path: Path) -> None:
    document = _manifest_document()
    distribution = _Distribution(
        tmp_path / "one",
        "any-distribution-name",
        {
            "solution_bundles/demo_bundle/bundle.json": document,
            "solution_bundles/demo_bundle/__init__.py": b"raise RuntimeError('must never import')",
        },
        version="1.2.0",
    )
    artifacts = discover_installed_solution_bundle_manifests([distribution])
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.distribution == "any-distribution-name"
    assert artifact.distribution_version == "1.2.0"
    assert artifact.manifest_resource_path == "solution_bundles/demo_bundle/bundle.json"
    assert artifact.manifest_digest == f"sha256:{sha256(document).hexdigest()}"
    assert artifact.manifest.bundle_id == "demo_bundle"
    assert artifact.manifest.manifest_id is not None


def test_ignores_paths_that_are_not_bundle_roots(tmp_path: Path) -> None:
    distribution = _Distribution(
        tmp_path / "shape",
        "shape",
        {
            "solution_bundles/demo_bundle/releases/v2/bundle.json": b"not a bundle root",
            "solution_bundles/bundle.json": b"not a bundle root",
            "other_tree/demo_bundle/bundle.json": b"not a bundle root",
        },
    )
    assert discover_installed_solution_bundle_manifests([distribution]) == ()


def test_duplicate_bundle_identifier_fails_closed(tmp_path: Path) -> None:
    document = _manifest_document()
    first = _Distribution(tmp_path / "first", "first", {"solution_bundles/demo_bundle/bundle.json": document})
    second = _Distribution(tmp_path / "second", "second", {"solution_bundles/other_dir/bundle.json": document})
    with pytest.raises(InstalledBundleArtifactError, match="ambiguous"):
        discover_installed_solution_bundle_manifests([first, second])


def test_invalid_manifest_bytes_fail_closed(tmp_path: Path) -> None:
    distribution = _Distribution(
        tmp_path / "invalid",
        "invalid",
        {"solution_bundles/demo_bundle/bundle.json": b'{"contract": "wrong"}'},
    )
    with pytest.raises(InstalledBundleArtifactError, match="validation"):
        discover_installed_solution_bundle_manifests([distribution])


def test_tampered_manifest_identity_fails_closed(tmp_path: Path) -> None:
    material = json.loads(_manifest_document())
    material["manifest_id"] = "solution_bundle_manifest:" + "0" * 32
    distribution = _Distribution(
        tmp_path / "tampered",
        "tampered",
        {"solution_bundles/demo_bundle/bundle.json": json.dumps(material).encode("utf-8")},
    )
    with pytest.raises(InstalledBundleArtifactError, match="validation"):
        discover_installed_solution_bundle_manifests([distribution])


def test_oversized_manifest_fails_closed(tmp_path: Path) -> None:
    padded = json.loads(_manifest_document())
    distribution = _Distribution(
        tmp_path / "oversized",
        "oversized",
        {"solution_bundles/demo_bundle/bundle.json": json.dumps(padded).encode("utf-8") + b" " * 1_000_001},
    )
    with pytest.raises(InstalledBundleArtifactError, match="size"):
        discover_installed_solution_bundle_manifests([distribution])


def test_symlinked_manifest_fails_closed(tmp_path: Path) -> None:
    document = _manifest_document()
    distribution = _Distribution(
        tmp_path / "sym",
        "sym",
        {"solution_bundles/demo_bundle/real.json": document},
    )
    target = tmp_path / "sym" / "solution_bundles" / "demo_bundle" / "bundle.json"
    target.symlink_to(tmp_path / "sym" / "solution_bundles" / "demo_bundle" / "real.json")
    distribution.files = distribution.files + (PurePosixPath("solution_bundles/demo_bundle/bundle.json"),)
    with pytest.raises(InstalledBundleArtifactError, match="symbolic"):
        discover_installed_solution_bundle_manifests([distribution])


def test_undeclared_manifest_path_fails_closed(tmp_path: Path) -> None:
    distribution = _Distribution(
        tmp_path / "undeclared", "undeclared", {"solution_bundles/demo_bundle/other.txt": b"x"}
    )
    distribution.files = distribution.files + (PurePosixPath("solution_bundles/demo_bundle/bundle.json"),)
    with pytest.raises(InstalledBundleArtifactError, match="unreadable|omitted"):
        discover_installed_solution_bundle_manifests([distribution])


def test_results_are_sorted_and_never_import(tmp_path: Path) -> None:
    beta = _Distribution(
        tmp_path / "beta",
        "beta",
        {"solution_bundles/beta_bundle/bundle.json": _manifest_document(bundle_id="beta_bundle")},
    )
    alpha = _Distribution(
        tmp_path / "alpha",
        "alpha",
        {"solution_bundles/alpha_bundle/bundle.json": _manifest_document(bundle_id="alpha_bundle")},
    )
    artifacts = discover_installed_solution_bundle_manifests([beta, alpha])
    assert [item.manifest.bundle_id for item in artifacts] == ["alpha_bundle", "beta_bundle"]
