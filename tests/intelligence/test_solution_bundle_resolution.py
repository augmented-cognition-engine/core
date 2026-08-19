"""Pure, deterministic Solution Bundle resolution and preview (PI10)."""

from __future__ import annotations

import pytest

from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    AtriumModuleBindingV1,
    PolicyBindingV1,
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)
from ace.intelligence.packs.bundle_activation import (
    preview_solution_bundle_activation,
    resolve_solution_bundle,
)

pytestmark = pytest.mark.unit

PACK_DIGEST = "sha256:" + "a" * 64


def _pack_ref() -> CompiledPackRefV1:
    return CompiledPackRefV1(
        pack_id="demo_pack",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{'a' * 32}",
        pack_digest=PACK_DIGEST,
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


def test_resolve_returns_a_resolution_receipt() -> None:
    receipt = resolve_solution_bundle(_manifest())
    assert isinstance(receipt, SolutionBundleResolutionReceiptV1)
    assert receipt.authority_stage == "resolved"


def test_resolve_is_deterministic_across_independent_calls() -> None:
    """The same manifest resolves to a byte-identical receipt every time."""

    manifest_one = _manifest()
    manifest_two = _manifest()
    receipt_one = resolve_solution_bundle(manifest_one)
    receipt_two = resolve_solution_bundle(manifest_two)
    assert receipt_one == receipt_two
    assert receipt_one.resolution_id == receipt_two.resolution_id
    assert receipt_one.resolution_hash == receipt_two.resolution_hash

    # Pin: resolving a third, independently constructed time still agrees.
    receipt_three = resolve_solution_bundle(_manifest())
    assert receipt_three == receipt_one


def test_resolve_differs_for_a_materially_different_manifest() -> None:
    manifest = _manifest()
    upgraded = manifest.model_copy(update={"bundle_version": "2.0.0", "manifest_id": None, "manifest_hash": None})
    upgraded = SolutionBundleManifestV1.model_validate(upgraded.model_dump(mode="python"))
    assert resolve_solution_bundle(manifest).resolution_id != resolve_solution_bundle(upgraded).resolution_id


def test_resolve_does_not_mutate_the_input_manifest() -> None:
    manifest = _manifest()
    before = manifest.model_dump(mode="json")
    resolve_solution_bundle(manifest)
    assert manifest.model_dump(mode="json") == before


def test_preview_is_read_only_and_matches_resolve() -> None:
    manifest = _manifest()
    assert preview_solution_bundle_activation(manifest) == resolve_solution_bundle(manifest)


def test_preview_signature_accepts_no_store_or_authority() -> None:
    """Preview cannot have a store side effect: no store/authority can even be passed in.

    The optional ``installed`` inventory (review graft) is discovery evidence — a
    pure value compared against the manifest — not a store or an authority, so the
    invariant this pin protects is unchanged.
    """

    import inspect

    parameters = inspect.signature(preview_solution_bundle_activation).parameters
    assert set(parameters) == {"manifest", "installed"}
