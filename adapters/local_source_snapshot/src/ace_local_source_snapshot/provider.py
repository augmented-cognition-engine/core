"""Local ``source_snapshot`` capability provider.

Zero-argument implementation of the public
:class:`~ace.application.source_snapshot_provider.SourceSnapshotProvider` port.
It owns no traversal, scope enforcement, digesting, or format logic: a snapshot
revalidates the request from its exact model dump and then only calls the
governed acquisition port in ace-core, dispatching each file through the
``source_units_for`` normalizer composition shaped into explicit
JSON-serializable dictionaries.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ace_local_source_normalizers import source_units_for

from ace.application.local_source_acquisition import AcquiredLocalFile, acquire_local_folder
from ace.application.source_snapshot_provider import (
    SOURCE_SNAPSHOT_CAPABILITY,
    SOURCE_SNAPSHOT_CONTRACT,
    SourceSnapshotRequestV1Alpha1,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID = "local_source_snapshot"
LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION = "0.1.0"


def _artifact_digest() -> str:
    """Digest of this module's exact source bytes, so identity drifts with the code."""
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _dispatch_source_units(extension: str, content: bytes) -> list[dict[str, str]] | None:
    """Dispatch to ``source_units_for``, shaping each unit into an explicit dictionary.

    Unsupported formats pass through unchanged as ``None`` — the unsupported-inventory
    signal the acquisition port expects.
    """
    units = source_units_for(extension, content)
    if units is None:
        return None
    return [{"anchor_kind": unit.anchor_kind, "anchor_value": unit.anchor_value, "text": unit.text} for unit in units]


class LocalSourceSnapshotProvider:
    """Installed ``source_snapshot`` implementation over the governed local port."""

    artifact_identity = CapabilityArtifactIdentityV1Alpha1(
        capability=SOURCE_SNAPSHOT_CAPABILITY,
        contract=SOURCE_SNAPSHOT_CONTRACT,
        implementation_id=LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID,
        implementation_version=LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION,
        artifact_digest=_artifact_digest(),
    )

    async def snapshot(self, request: SourceSnapshotRequestV1Alpha1) -> tuple[AcquiredLocalFile, ...]:
        validated = SourceSnapshotRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        return acquire_local_folder(
            validated.authorized_root,
            dispatch=_dispatch_source_units,
            include=validated.include,
            exclude=validated.exclude,
        )


__all__ = [
    "LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID",
    "LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION",
    "LocalSourceSnapshotProvider",
]
