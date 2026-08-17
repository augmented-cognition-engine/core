"""Validation for returns from a bounded, provider-neutral coding-agent handoff."""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.code_intelligence.contracts import (
    BoundedCodeHandoffV1Alpha1,
    CodingAgentReturnReceiptV1Alpha1,
    CodingAgentReturnV1Alpha1,
)


def validate_coding_agent_return(
    handoff: BoundedCodeHandoffV1Alpha1,
    returned: CodingAgentReturnV1Alpha1,
) -> CodingAgentReturnReceiptV1Alpha1:
    """Validate identity closure and the context/change bounds of one agent return."""

    expected = handoff.receipt
    identity_pairs = (
        ("receiver", returned.receiver_ref, expected.receiver_ref),
        ("handoff", returned.handoff_id, expected.handoff_id),
        ("index", returned.index_id, expected.index_id),
        ("lens", returned.lens_id, expected.lens_id),
        ("manifest", returned.manifest_id, expected.manifest_id),
    )
    for label, actual, wanted in identity_pairs:
        if actual != wanted:
            raise ValueError(f"coding-agent return {label} identity does not match handoff")

    manifest_blocks = {item.block_id for item in handoff.manifest.blocks}
    consumed = set(returned.consumed_block_ids)
    unknown_blocks = consumed - manifest_blocks
    if unknown_blocks:
        raise ValueError(f"coding-agent return names unknown context blocks: {sorted(unknown_blocks)}")

    included_paths = set(expected.included_paths)
    outside_paths = set(returned.changed_paths) - included_paths
    if outside_paths:
        raise ValueError(f"coding-agent return changes paths outside the bounded handoff: {sorted(outside_paths)}")

    warnings = list(returned.uncertainties)
    unconsumed = manifest_blocks - consumed
    if unconsumed:
        warnings.append(f"Agent did not report consuming {len(unconsumed)} manifest block(s).")
    if not returned.verification_refs:
        warnings.append("Agent supplied no independent verification reference.")

    return CodingAgentReturnReceiptV1Alpha1(
        return_id=returned.return_id,
        receiver_ref=returned.receiver_ref,
        handoff_id=returned.handoff_id,
        index_id=returned.index_id,
        lens_id=returned.lens_id,
        manifest_id=returned.manifest_id,
        disposition=returned.disposition,
        consumed_block_ids=returned.consumed_block_ids,
        changed_paths=returned.changed_paths,
        verification_refs=returned.verification_refs,
        warnings=tuple(warnings),
        validated_at=datetime.now(timezone.utc),
    )
