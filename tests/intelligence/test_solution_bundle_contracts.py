"""Solution Bundle manifest, resolution receipt, and activation revision contracts (PI10)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    AtriumModuleBindingV1,
    BundleActivationAction,
    BundleActivationRuntimeState,
    PolicyBindingV1,
    SolutionBundleActivationRevisionV1,
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)

pytestmark = pytest.mark.unit

PACK_DIGEST = "sha256:" + "a" * 64
BASE = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _pack_ref(*, pack_id: str = "demo_pack", pack_version: str = "1.0.0") -> CompiledPackRefV1:
    return CompiledPackRefV1(
        pack_id=pack_id,
        pack_version=pack_version,
        compiled_pack_id=f"pack_ir:{'a' * 32}",
        pack_digest=PACK_DIGEST,
    )


def _overlay(pack: CompiledPackRefV1) -> CompiledOverlayV1:
    return CompiledOverlayV1(
        overlay_id="demo_overlay",
        version="1.0.0",
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        pack_digest=pack.pack_digest,
        values=(),
    )


def _adapter(adapter_id: str = "markdown_adapter", version: str = "1.0.0") -> AdapterBindingV1:
    return AdapterBindingV1(adapter_id=adapter_id, adapter_version=version, artifact_digest="sha256:" + "b" * 64)


def _atrium_module(module_id: str = "inventory_panel", version: str = "1.0.0") -> AtriumModuleBindingV1:
    return AtriumModuleBindingV1(module_id=module_id, module_version=version, artifact_digest="sha256:" + "c" * 64)


def _policy(policy_id: str = "local_read_only", version: str = "1.0.0") -> PolicyBindingV1:
    return PolicyBindingV1(policy_id=policy_id, policy_version=version, policy_digest="sha256:" + "d" * 64)


def _manifest(
    *,
    bundle_id: str = "demo_bundle",
    product_id: str = "product:demo",
    adapters: tuple[AdapterBindingV1, ...] | None = None,
) -> SolutionBundleManifestV1:
    pack = _pack_ref()
    return SolutionBundleManifestV1(
        product_id=product_id,
        bundle_id=bundle_id,
        bundle_version="1.0.0",
        pack=pack,
        overlay=_overlay(pack),
        adapters=adapters if adapters is not None else (_adapter(),),
        atrium_modules=(_atrium_module(),),
        policy=_policy(),
    )


def _receipt(manifest: SolutionBundleManifestV1) -> SolutionBundleResolutionReceiptV1:
    return SolutionBundleResolutionReceiptV1(manifest=manifest)


def test_manifest_self_derives_stable_identity_from_exact_material() -> None:
    first = _manifest()
    second = _manifest()
    assert first.manifest_id is not None
    assert first.manifest_id == second.manifest_id
    assert first.manifest_hash == second.manifest_hash


def test_manifest_identity_changes_with_bundle_id() -> None:
    a = _manifest(bundle_id="bundle_a")
    b = _manifest(bundle_id="bundle_b")
    assert a.manifest_id != b.manifest_id


def test_manifest_rejects_overlay_targeting_a_different_pack() -> None:
    pack = _pack_ref()
    other_pack = _pack_ref(pack_id="other_pack")
    with pytest.raises(ValidationError, match="overlay must target the exact compiled pack"):
        SolutionBundleManifestV1(
            product_id="product:demo",
            bundle_id="demo_bundle",
            bundle_version="1.0.0",
            pack=pack,
            overlay=_overlay(other_pack),
            adapters=(_adapter(),),
            atrium_modules=(),
            policy=_policy(),
        )


def test_manifest_rejects_duplicate_adapter_ids() -> None:
    with pytest.raises(ValidationError, match="adapter bindings"):
        _manifest(adapters=(_adapter(), _adapter()))


def test_manifest_normalizes_adapter_order_regardless_of_input_order() -> None:
    forward = _manifest(adapters=(_adapter("a_adapter"), _adapter("b_adapter")))
    reversed_ = _manifest(adapters=(_adapter("b_adapter"), _adapter("a_adapter")))
    assert forward.manifest_id == reversed_.manifest_id
    assert [item.adapter_id for item in forward.adapters] == ["a_adapter", "b_adapter"]


def test_manifest_rejects_empty_adapter_set() -> None:
    with pytest.raises(ValidationError):
        _manifest(adapters=())


def test_resolution_receipt_binds_the_exact_manifest_and_derives_bundle_state_id() -> None:
    manifest = _manifest()
    receipt = _receipt(manifest)
    assert receipt.manifest == manifest
    assert receipt.bundle_state_id is not None
    assert receipt.bundle_state_id.startswith("solution_bundle:")
    assert receipt.resolution_id is not None
    assert receipt.resolution_hash is not None


def test_resolution_receipt_authority_stage_is_schema_pinned_non_authority() -> None:
    schema = SolutionBundleResolutionReceiptV1.model_json_schema()
    assert schema["properties"]["authority_stage"]["const"] == "resolved"


def test_resolution_receipt_bundle_state_id_is_stable_across_manifest_versions() -> None:
    """The activation scope key must survive a bundle_version upgrade."""

    pack = _pack_ref()
    manifest_v1 = SolutionBundleManifestV1(
        product_id="product:demo",
        bundle_id="demo_bundle",
        bundle_version="1.0.0",
        pack=pack,
        overlay=_overlay(pack),
        adapters=(_adapter(),),
        atrium_modules=(),
        policy=_policy(),
    )
    manifest_v2 = SolutionBundleManifestV1(
        product_id="product:demo",
        bundle_id="demo_bundle",
        bundle_version="1.1.0",
        pack=pack,
        overlay=_overlay(pack),
        adapters=(_adapter(version="1.1.0"),),
        atrium_modules=(),
        policy=_policy(),
    )
    assert manifest_v1.manifest_id != manifest_v2.manifest_id
    assert _receipt(manifest_v1).bundle_state_id == _receipt(manifest_v2).bundle_state_id


def _activation_revision(
    *,
    manifest: SolutionBundleManifestV1,
    action: BundleActivationAction = BundleActivationAction.ACTIVATE,
    state: BundleActivationRuntimeState = BundleActivationRuntimeState.ACTIVE,
    revision: int = 1,
    prior_revision_id: str | None = None,
    resolution_receipt: SolutionBundleResolutionReceiptV1 | None = None,
) -> SolutionBundleActivationRevisionV1:
    return SolutionBundleActivationRevisionV1(
        revision=revision,
        manifest=manifest,
        resolution_receipt=resolution_receipt if resolution_receipt is not None else _receipt(manifest),
        action=action,
        state=state,
        prior_revision_id=prior_revision_id,
        actor_ref="principal:tester",
        approval_receipt_ref="approval:1",
        occurred_at=BASE,
    )


def test_activation_revision_self_derives_activation_id_from_bundle_state_id() -> None:
    manifest = _manifest()
    revision = _activation_revision(manifest=manifest)
    assert revision.activation_id == _receipt(manifest).bundle_state_id


def test_activation_revision_rejects_mismatched_resolution_receipt() -> None:
    manifest = _manifest(bundle_id="bundle_a")
    other_manifest = _manifest(bundle_id="bundle_b")
    with pytest.raises(ValidationError, match="exact bound manifest"):
        _activation_revision(manifest=manifest, resolution_receipt=_receipt(other_manifest))


def test_activation_revision_first_revision_must_activate() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError, match="must activate"):
        _activation_revision(
            manifest=manifest,
            action=BundleActivationAction.DEACTIVATE,
            state=BundleActivationRuntimeState.RETIRED,
        )


def test_activation_revision_first_revision_cannot_have_a_prior_revision() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError, match="cannot have a prior revision"):
        _activation_revision(manifest=manifest, prior_revision_id="solution_bundle_activation_revision:" + "0" * 32)


def test_activation_revision_action_state_pairing_is_enforced() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError, match="activate action must produce the active state"):
        _activation_revision(
            manifest=manifest,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.RETIRED,
        )
