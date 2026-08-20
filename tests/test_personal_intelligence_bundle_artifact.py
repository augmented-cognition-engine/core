"""PI11: the shipped public Personal Intelligence bundle artifact is exact and regenerable.

The bundle machinery is domain-neutral (Decision 1); the concrete Personal
Intelligence bundle exists only as this distribution-shipped manifest value.
Every binding must be exact against the repository's real artifacts, and the
document must regenerate byte-identically from the generator script.
"""

from __future__ import annotations

import json
import tomllib
from hashlib import sha256
from pathlib import Path

import pytest

from ace.intelligence.contracts.solution_bundle import SolutionBundleManifestV1
from ace.intelligence.packs.bundle_activation import resolve_solution_bundle
from ace.intelligence.packs.compiler import compile_pack_document_with_report
from scripts.build_solution_bundle_manifest import (
    adapter_source_tree_digest,
    build_personal_intelligence_bundle_manifest,
    render_bundle_document,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
BUNDLE_DIR = REPO / "solution_bundles" / "personal_intelligence"
LOCAL_ADAPTER_DIRS = (
    "local_csv_source",
    "local_json_source",
    "local_markdown_source",
    "local_pdf_source",
    "local_source_normalizers",
)


def _shipped_manifest() -> SolutionBundleManifestV1:
    return SolutionBundleManifestV1.model_validate(json.loads((BUNDLE_DIR / "bundle.json").read_bytes()))


def test_shipped_bundle_document_validates_and_resolves() -> None:
    manifest = _shipped_manifest()
    receipt = resolve_solution_bundle(manifest)
    assert receipt.authority_stage == "resolved"
    assert manifest.bundle_id == "personal_intelligence"


def test_pack_binding_matches_a_fresh_compile_of_the_shipped_pack() -> None:
    pack_root = REPO / "domain_packs" / "personal_intelligence"
    manifest_document = (pack_root / "manifest.json").read_bytes()
    pack_manifest = json.loads(manifest_document)
    resources = {item["path"]: (pack_root / item["path"]).read_bytes() for item in pack_manifest["resources"]}
    compiled = compile_pack_document_with_report(manifest_document, resources).pack
    bound = _shipped_manifest().pack
    assert bound.pack_id == compiled.metadata.pack_id
    assert bound.pack_version == compiled.metadata.version
    assert bound.compiled_pack_id == compiled.compiled_pack_id
    assert bound.pack_digest == compiled.pack_digest


def test_adapter_bindings_pin_the_exact_local_adapter_family() -> None:
    manifest = _shipped_manifest()
    bound = {item.adapter_id: item for item in manifest.adapters}
    expected_ids = set()
    for directory in LOCAL_ADAPTER_DIRS:
        adapter_dir = REPO / "adapters" / directory
        project = tomllib.loads((adapter_dir / "pyproject.toml").read_text())["project"]
        expected_ids.add(project["name"])
        binding = bound[project["name"]]
        assert binding.adapter_version == project["version"]
        assert binding.artifact_digest == adapter_source_tree_digest(adapter_dir)
    assert set(bound) == expected_ids


def test_policy_binding_pins_the_shipped_policy_document() -> None:
    manifest = _shipped_manifest()
    policy_document = (BUNDLE_DIR / "policy" / "local_read_only_sources.json").read_bytes()
    policy = json.loads(policy_document)
    assert manifest.policy.policy_id == policy["policy_id"]
    assert manifest.policy.policy_version == policy["version"]
    assert manifest.policy.policy_digest == f"sha256:{sha256(policy_document).hexdigest()}"


def test_overlay_is_the_default_empty_overlay_over_the_exact_pack() -> None:
    manifest = _shipped_manifest()
    assert manifest.overlay.values == ()
    assert manifest.overlay.pack_digest == manifest.pack.pack_digest


def test_document_regenerates_byte_identically_from_the_generator() -> None:
    regenerated = render_bundle_document(build_personal_intelligence_bundle_manifest(REPO))
    assert regenerated == (BUNDLE_DIR / "bundle.json").read_bytes()


def test_distribution_ships_the_manifest_at_the_discovery_path() -> None:
    project = tomllib.loads((BUNDLE_DIR / "pyproject.toml").read_text())
    assert project["project"]["name"] == "ace-personal-intelligence-bundle"
    force_include = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force_include["bundle.json"] == "solution_bundles/personal_intelligence/bundle.json"
    assert force_include["policy"] == "solution_bundles/personal_intelligence/policy"
