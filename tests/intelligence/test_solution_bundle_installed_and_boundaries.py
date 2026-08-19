"""Review grafts onto the PI10 Solution Bundle machinery.

Three gaps the PI12 three-arm review identified, closed here:
- fail-closed installed-component verification (arm A's design): a manifest
  declaring a pack/overlay/adapter/module/policy the workspace does not
  actually offer must not resolve, preview, or activate;
- a golden-digest regression pin (arm A's design): the strongest form of
  "deterministic, test-pinned" — canonicalization drift changes this literal;
- an executable Decision-1 boundary check (arm B's design): the bundle
  machinery's identifiers and non-docstring literals never name a specific
  bundle — which product a bundle serves is manifest data, never a noun.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    AtriumModuleBindingV1,
    InstalledSolutionComponentsV1,
    PolicyBindingV1,
    SolutionBundleManifestV1,
)
from ace.intelligence.packs.bundle_activation import (
    SolutionBundleResolutionError,
    preview_solution_bundle_activation,
    resolve_solution_bundle,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]


def _pack_ref() -> CompiledPackRefV1:
    return CompiledPackRefV1(
        pack_id="demo_pack",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{'a' * 32}",
        pack_digest="sha256:" + "a" * 64,
    )


def _manifest() -> SolutionBundleManifestV1:
    pack = _pack_ref()
    return SolutionBundleManifestV1(
        product_id="product:demo",
        bundle_id="demo_bundle",
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
            AdapterBindingV1(
                adapter_id="markdown_adapter", adapter_version="1.0.0", artifact_digest="sha256:" + "b" * 64
            ),
        ),
        atrium_modules=(
            AtriumModuleBindingV1(
                module_id="inventory_panel", module_version="1.0.0", artifact_digest="sha256:" + "c" * 64
            ),
        ),
        policy=PolicyBindingV1(policy_id="local_read_only", policy_version="1.0.0", policy_digest="sha256:" + "d" * 64),
    )


def _installed_everything(manifest: SolutionBundleManifestV1) -> InstalledSolutionComponentsV1:
    return InstalledSolutionComponentsV1(
        packs=(manifest.pack,),
        overlays=(manifest.overlay,),
        adapters=manifest.adapters,
        atrium_modules=manifest.atrium_modules,
        policies=(manifest.policy,),
    )


# --- installed-component fail-closed verification ---------------------------


def test_resolution_succeeds_when_every_declared_component_is_installed() -> None:
    manifest = _manifest()
    receipt = resolve_solution_bundle(manifest, installed=_installed_everything(manifest))
    assert receipt.manifest == manifest


def test_resolution_without_an_inventory_is_unchanged_legacy_behavior() -> None:
    manifest = _manifest()
    assert resolve_solution_bundle(manifest) == resolve_solution_bundle(manifest, installed=None)


@pytest.mark.parametrize(
    ("missing", "message_fragment"),
    [
        ("packs", "declared pack is not installed"),
        ("overlays", "declared overlay is not installed"),
        ("adapters", "declared adapter is not installed"),
        ("atrium_modules", "declared Atrium module is not installed"),
        ("policies", "declared policy is not installed"),
    ],
)
def test_resolution_fails_closed_when_a_declared_component_is_not_installed(
    missing: str, message_fragment: str
) -> None:
    manifest = _manifest()
    full = _installed_everything(manifest)
    hollowed = InstalledSolutionComponentsV1.model_validate({**full.model_dump(mode="python"), missing: ()})
    with pytest.raises(SolutionBundleResolutionError, match=message_fragment):
        resolve_solution_bundle(manifest, installed=hollowed)
    with pytest.raises(SolutionBundleResolutionError, match=message_fragment):
        preview_solution_bundle_activation(manifest, installed=hollowed)


def test_version_or_digest_drift_fails_closed_by_full_value_equality() -> None:
    manifest = _manifest()
    drifted_pack = manifest.pack.model_copy(update={"pack_version": "1.0.1"})
    inventory = InstalledSolutionComponentsV1.model_validate(
        {
            **_installed_everything(manifest).model_dump(mode="python"),
            "packs": (drifted_pack.model_dump(mode="python"),),
        }
    )
    with pytest.raises(SolutionBundleResolutionError, match="declared pack is not installed"):
        resolve_solution_bundle(manifest, installed=inventory)


# --- golden-digest determinism pin -------------------------------------------


def test_resolution_receipt_digest_is_pinned_to_a_golden_literal() -> None:
    """Canonicalization drift must fail loudly, not silently re-derive.

    The literal below is the exact receipt digest of the fixture manifest at
    the time this machinery merged. Any change to field ordering, canonical
    JSON, hashing, or contract shape that alters derived identities will break
    this pin and demand a conscious decision.
    """

    receipt = resolve_solution_bundle(_manifest())
    assert receipt.resolution_hash == "sha256:61c27971a5078e5e4be9e03e3a4be00cf862e2e8e88c68419644ff88156d400b"


# --- executable Decision-1 boundary ------------------------------------------

_BUNDLE_NOUNS = ("personal", "code_intelligence", "code intelligence")
_BUNDLE_MACHINERY = (
    "ace/intelligence/contracts/solution_bundle.py",
    "ace/intelligence/packs/bundle_activation.py",
    "ace/application/solution_bundle_activation.py",
)


def _identifiers_and_literals(path: Path) -> list[str]:
    """Every identifier and non-docstring string literal in a module."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            found.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append(node.name)
        elif isinstance(node, ast.arg):
            found.append(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append(node.value)
    return found


def test_bundle_machinery_names_no_specific_bundle() -> None:
    """Decision 1: which product a bundle serves is manifest data, never a noun.

    Docstrings may explain the rule in prose; identifiers and functional string
    literals may never encode it.
    """

    for relative in _BUNDLE_MACHINERY:
        for token in _identifiers_and_literals(REPO / relative):
            lowered = token.lower()
            for noun in _BUNDLE_NOUNS:
                assert noun not in lowered, f"{relative} names a specific bundle: {token!r}"
