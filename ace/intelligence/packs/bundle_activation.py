"""Pure Solution Bundle manifest resolution.

Mirrors :mod:`ace.intelligence.packs.activation`: no I/O, no discovery, no
persistence, no authority. ``resolve_solution_bundle`` is a pure function of
its input manifest, so the same manifest always resolves to a
byte-identical receipt. Persistence and atomic admission remain an
Application/Core concern (see ``ace.application.solution_bundle_activation``).
"""

from __future__ import annotations

from ace.intelligence.contracts.solution_bundle import (
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)


def resolve_solution_bundle(manifest: SolutionBundleManifestV1) -> SolutionBundleResolutionReceiptV1:
    """Deterministically resolve one exact Solution Bundle manifest.

    Revalidates the manifest through an exact round trip (the same idiom
    used by :func:`~ace.intelligence.packs.activation.prepare_domain_activation`)
    before deriving the receipt, so a caller cannot smuggle an already-mutated
    or partially validated object into the resolved result.
    """

    exact_manifest = SolutionBundleManifestV1.model_validate(manifest.model_dump(mode="python"))
    return SolutionBundleResolutionReceiptV1(manifest=exact_manifest)


def preview_solution_bundle_activation(manifest: SolutionBundleManifestV1) -> SolutionBundleResolutionReceiptV1:
    """Preview exactly what activating ``manifest`` would resolve to.

    Read-only and side-effect free: identical to :func:`resolve_solution_bundle`.
    Kept as its own named entry point, with no store or authority parameter,
    so a caller can see at the call site — and the signature can prove —
    that activation has not occurred and grants no authority.
    """

    return resolve_solution_bundle(manifest)


__all__ = ["preview_solution_bundle_activation", "resolve_solution_bundle"]
