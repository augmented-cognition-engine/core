"""Installable local ``source_snapshot`` capability provider for ACE.

Registers :class:`LocalSourceSnapshotProvider` under the
``ace.source_snapshot_providers`` entry-point group so a host registry can
discover it fail-closed. The provider is a thin seam: it revalidates each
snapshot request and delegates to ace-core's governed local acquisition port
with the ``source_units_for`` normalizer dispatch.
"""

from ace_local_source_snapshot.provider import (
    LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID,
    LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION,
    LocalSourceSnapshotProvider,
)

__all__ = [
    "LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID",
    "LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION",
    "LocalSourceSnapshotProvider",
]
