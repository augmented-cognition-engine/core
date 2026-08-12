"""Lossless Core-owned bridges into Agent Memory source provenance.

Bridges copy only existing Core authority and exact source coordinates. Captured
payload remains inert and never supplies scope, authority, time, or a locator.
"""

from __future__ import annotations

from ace.core.agent_memory import SourceProvenanceV1Alpha1, SourceSpanV1Alpha1
from ace.core.source import CanonicalSourceSnapshotV1Alpha1


def provenance_from_canonical_source_snapshot(
    snapshot: CanonicalSourceSnapshotV1Alpha1,
    *,
    span: SourceSpanV1Alpha1,
    capture_method_ref: str,
) -> SourceProvenanceV1Alpha1:
    """Map one immutable Core source snapshot without copying its payload.

    The caller must supply an exact locator already bound to the snapshot, or an
    explicit unavailable locator. This bridge never parses the legacy free-form
    locator and never treats captured content as authority.
    """

    snapshot_ref = str(snapshot.source_snapshot_ref)
    if span.source_version_id != snapshot_ref:
        raise ValueError("source span must bind the exact canonical source snapshot")
    return SourceProvenanceV1Alpha1(
        source_id=snapshot.source_definition_ref,
        source_version_id=snapshot_ref,
        content_digest=snapshot.captured_payload_digest,
        span=span,
        acquisition_receipt_ref=snapshot.acquisition_receipt_ref,
        capture_method_ref=capture_method_ref,
        derived_from=(snapshot_ref,),
    )


__all__ = ["provenance_from_canonical_source_snapshot"]
