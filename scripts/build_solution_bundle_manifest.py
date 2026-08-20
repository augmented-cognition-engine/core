"""Generate the public Personal Intelligence Solution Bundle manifest.

The bundle machinery is domain-neutral; this host-side generator constructs the
concrete Personal Intelligence bundle *value* from the repository's real
artifacts and writes ``solution_bundles/personal_intelligence/bundle.json``:

- the pack binding is the exact compiled identity of the shipped
  ``domain_packs/personal_intelligence`` pack (freshly compiled from bytes);
- the overlay is the default empty-values overlay over that exact pack;
- each adapter binding pins the adapter's declared distribution name, exact
  version, and a canonical source-tree digest (sorted relative path to
  sha256-of-bytes mapping, canonically hashed) so drift in any shipped adapter
  file changes the binding;
- the policy binding pins the shipped policy document's exact bytes.

Deterministic by construction: no clock, no environment, no network. Rerunning
against an unchanged repository emits byte-identical output, and the test suite
enforces exactly that.
"""

from __future__ import annotations

import json
import sys
import tomllib
from hashlib import sha256
from pathlib import Path

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    PolicyBindingV1,
    SolutionBundleManifestV1,
)
from ace.intelligence.packs.compiler import compile_pack_document_with_report

LOCAL_ADAPTER_DIRS = (
    "local_csv_source",
    "local_json_source",
    "local_markdown_source",
    "local_pdf_source",
    "local_source_normalizers",
)
_EXCLUDED_TREE_PARTS = {"__pycache__", ".venv", "dist", "build", ".pytest_cache"}


def adapter_source_tree_digest(adapter_dir: Path) -> str:
    """Canonical digest over every shipped file in one adapter's source tree."""

    mapping: dict[str, str] = {}
    for path in sorted(adapter_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(adapter_dir)
        if any(part in _EXCLUDED_TREE_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        mapping[relative.as_posix()] = sha256(path.read_bytes()).hexdigest()
    if not mapping:
        raise ValueError(f"adapter source tree is empty: {adapter_dir}")
    return f"sha256:{canonical_hash(mapping)}"


def _compiled_pack_reference(repo_root: Path) -> CompiledPackRefV1:
    pack_root = repo_root / "domain_packs" / "personal_intelligence"
    manifest_document = (pack_root / "manifest.json").read_bytes()
    pack_manifest = json.loads(manifest_document)
    resources = {item["path"]: (pack_root / item["path"]).read_bytes() for item in pack_manifest["resources"]}
    pack = compile_pack_document_with_report(manifest_document, resources).pack
    return CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )


def _adapter_bindings(repo_root: Path) -> tuple[AdapterBindingV1, ...]:
    bindings = []
    for directory in LOCAL_ADAPTER_DIRS:
        adapter_dir = repo_root / "adapters" / directory
        project = tomllib.loads((adapter_dir / "pyproject.toml").read_text())["project"]
        bindings.append(
            AdapterBindingV1(
                adapter_id=project["name"],
                adapter_version=project["version"],
                artifact_digest=adapter_source_tree_digest(adapter_dir),
            )
        )
    return tuple(bindings)


def _policy_binding(repo_root: Path) -> PolicyBindingV1:
    policy_path = repo_root / "solution_bundles" / "personal_intelligence" / "policy" / "local_read_only_sources.json"
    document = policy_path.read_bytes()
    policy = json.loads(document)
    return PolicyBindingV1(
        policy_id=policy["policy_id"],
        policy_version=policy["version"],
        policy_digest=f"sha256:{sha256(document).hexdigest()}",
    )


def build_personal_intelligence_bundle_manifest(repo_root: Path) -> SolutionBundleManifestV1:
    pack = _compiled_pack_reference(repo_root)
    return SolutionBundleManifestV1(
        product_id="product:personal-intelligence",
        bundle_id="personal_intelligence",
        bundle_version="1.2.0",
        pack=pack,
        overlay=CompiledOverlayV1(
            overlay_id="personal_defaults",
            version="1.0.0",
            pack_id=pack.pack_id,
            pack_version=pack.pack_version,
            pack_digest=pack.pack_digest,
            values=(),
        ),
        adapters=_adapter_bindings(repo_root),
        policy=_policy_binding(repo_root),
    )


def render_bundle_document(manifest: SolutionBundleManifestV1) -> bytes:
    material = manifest.model_dump(mode="json")
    return (json.dumps(material, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = build_personal_intelligence_bundle_manifest(repo_root)
    target = repo_root / "solution_bundles" / "personal_intelligence" / "bundle.json"
    target.write_bytes(render_bundle_document(manifest))
    print(f"wrote {target} ({manifest.manifest_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
