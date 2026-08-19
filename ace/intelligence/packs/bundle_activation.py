"""Pure Solution Bundle manifest resolution.

Mirrors :mod:`ace.intelligence.packs.activation`: no I/O, no discovery, no
persistence, no authority. ``resolve_solution_bundle`` is a pure function of
its input manifest, so the same manifest always resolves to a
byte-identical receipt. Persistence and atomic admission remain an
Application/Core concern (see ``ace.application.solution_bundle_activation``).
"""

from __future__ import annotations

from ace.intelligence.contracts.solution_bundle import (
    InstalledSolutionComponentsV1,
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)


class SolutionBundleResolutionError(ValueError):
    """A manifest declared a component the workspace does not actually offer."""


def _require_installed(
    manifest: SolutionBundleManifestV1,
    installed: InstalledSolutionComponentsV1,
) -> None:
    """Fail closed unless every declared binding is present by full value equality."""

    if manifest.pack not in installed.packs:
        raise SolutionBundleResolutionError(
            f"declared pack is not installed on this workspace: {manifest.pack.pack_id}"
        )
    if manifest.overlay not in installed.overlays:
        raise SolutionBundleResolutionError(
            f"declared overlay is not installed on this workspace: {manifest.overlay.overlay_id}"
        )
    for adapter in manifest.adapters:
        if adapter not in installed.adapters:
            raise SolutionBundleResolutionError(
                f"declared adapter is not installed on this workspace: {adapter.adapter_id}"
            )
    for module in manifest.atrium_modules:
        if module not in installed.atrium_modules:
            raise SolutionBundleResolutionError(
                f"declared Atrium module is not installed on this workspace: {module.module_id}"
            )
    if manifest.policy not in installed.policies:
        raise SolutionBundleResolutionError(
            f"declared policy is not installed on this workspace: {manifest.policy.policy_id}"
        )


def resolve_solution_bundle(
    manifest: SolutionBundleManifestV1,
    *,
    installed: InstalledSolutionComponentsV1 | None = None,
) -> SolutionBundleResolutionReceiptV1:
    """Deterministically resolve one exact Solution Bundle manifest.

    Revalidates the manifest through an exact round trip (the same idiom
    used by :func:`~ace.intelligence.packs.activation.prepare_domain_activation`)
    before deriving the receipt, so a caller cannot smuggle an already-mutated
    or partially validated object into the resolved result.
    """

    exact_manifest = SolutionBundleManifestV1.model_validate(manifest.model_dump(mode="python"))
    if installed is not None:
        exact_installed = InstalledSolutionComponentsV1.model_validate(installed.model_dump(mode="python"))
        _require_installed(exact_manifest, exact_installed)
    return SolutionBundleResolutionReceiptV1(manifest=exact_manifest)


def preview_solution_bundle_activation(
    manifest: SolutionBundleManifestV1,
    *,
    installed: InstalledSolutionComponentsV1 | None = None,
) -> SolutionBundleResolutionReceiptV1:
    """Preview exactly what activating ``manifest`` would resolve to.

    Read-only and side-effect free: identical to :func:`resolve_solution_bundle`.
    Kept as its own named entry point, with no store or authority parameter,
    so a caller can see at the call site — and the signature can prove —
    that activation has not occurred and grants no authority.
    """

    return resolve_solution_bundle(manifest, installed=installed)


__all__ = [
    "SolutionBundleResolutionError",
    "preview_solution_bundle_activation",
    "resolve_solution_bundle",
]
