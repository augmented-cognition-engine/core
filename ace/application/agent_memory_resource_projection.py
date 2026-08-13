"""Public Context Manifest, Memory Use, and memory-lineage projections."""

from __future__ import annotations

from collections.abc import Iterable

from ace.application.agent_memory_recall import (
    AM3_RECORD_SPACE,
    CONTEXT_MANIFEST_RECORD_KIND,
    CONTEXT_USE_RECORD_KIND,
    MEMORY_CONTEXT_LINEAGE_RECORD_KIND,
)
from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
from ace.intelligence.contracts.agent_memory import MemoryContextLineageV1Alpha1
from ace.intelligence.contracts.agent_memory_recall import (
    CanonicalContextManifestV1,
    ContextUseReceiptV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1

AGENT_MEMORY_RESOURCE_KINDS = frozenset(
    {
        IntelligenceResourceKind.CONTEXT_MANIFEST,
        IntelligenceResourceKind.MEMORY_USE,
        IntelligenceResourceKind.EVIDENCE_LINEAGE,
    }
)


def _is_am3_record(record: ImmutableRecordV1) -> bool:
    return record.record_space.startswith(f"{AM3_RECORD_SPACE}:")


def _manifest_reference(
    *,
    product_id: str,
    manifest: CanonicalContextManifestV1,
    record: ImmutableRecordV1,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=IntelligenceResourceKind.CONTEXT_MANIFEST,
        resource_id=str(manifest.artifact_id),
        resource_digest=str(manifest.artifact_digest),
        resource_contract=manifest.contract,
        revision=1,
        as_of=record.as_of,
        available_at=record.available_at,
    )


def _decode_manifest(record: ImmutableRecordV1) -> CanonicalContextManifestV1:
    value = CanonicalContextManifestV1.model_validate(record.payload, strict=False)
    if (
        not _is_am3_record(record)
        or record.record_kind != CONTEXT_MANIFEST_RECORD_KIND
        or record.record_key != value.artifact_id
        or record.payload_contract != value.contract
        or record.product_id != value.receiver.product_id
        or record.as_of != value.generated_at
        or record.available_at != value.generated_at
    ):
        raise ValueError("Context Manifest envelope mismatch")
    return value


def _decode_use(record: ImmutableRecordV1) -> ContextUseReceiptV1Alpha1:
    value = ContextUseReceiptV1Alpha1.model_validate(record.payload, strict=False)
    if (
        not _is_am3_record(record)
        or record.record_kind != CONTEXT_USE_RECORD_KIND
        or record.record_key != value.artifact_id
        or record.payload_contract != value.contract
        or record.as_of != value.recorded_at
        or record.available_at != value.recorded_at
    ):
        raise ValueError("Memory Use envelope mismatch")
    return value


def _decode_lineage(record: ImmutableRecordV1) -> MemoryContextLineageV1Alpha1:
    value = MemoryContextLineageV1Alpha1.model_validate(record.payload, strict=False)
    if (
        not _is_am3_record(record)
        or record.record_kind != MEMORY_CONTEXT_LINEAGE_RECORD_KIND
        or record.record_key != value.lineage_id
        or record.payload_contract != value.contract
        or record.product_id != value.scope.product_id
        or record.as_of != value.recorded_at
        or record.available_at != value.recorded_at
    ):
        raise ValueError("memory lineage envelope mismatch")
    return value


def _manifest_record(
    record: ImmutableRecordV1,
    value: CanonicalContextManifestV1,
) -> IntelligenceResourceRecordV1Alpha1:
    reasons = tuple(f"degraded_reason:context-manifest:{item}" for item in value.degraded_reasons)
    availability = IntelligenceResourceAvailability.DEGRADED if reasons else IntelligenceResourceAvailability.AVAILABLE
    return IntelligenceResourceRecordV1Alpha1(
        reference=_manifest_reference(product_id=record.product_id, manifest=value, record=record),
        availability=availability,
        title=f"Context Manifest: {value.receiver.task_ref}",
        summary=(
            f"Selected {len(value.selected_candidate_refs)} memory candidates into {value.total_tokens} bounded tokens."
        ),
        subject_refs=tuple(
            sorted(
                {
                    value.receiver.participant_ref,
                    value.receiver.stage_ref,
                    value.receiver.task_ref,
                    *value.selected_candidate_refs,
                }
            )
        ),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(value.model_dump(mode="json"))),
        degraded_reason_refs=reasons,
    )


def _use_record(
    record: ImmutableRecordV1,
    value: ContextUseReceiptV1Alpha1,
    manifest_reference: IntelligenceResourceReferenceV1Alpha1,
) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=record.product_id,
            resource_kind=IntelligenceResourceKind.MEMORY_USE,
            resource_id=str(value.artifact_id),
            resource_digest=str(value.artifact_digest),
            resource_contract=value.contract,
            revision=1,
            as_of=record.as_of,
            available_at=record.available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"Memory Use: {value.receiver_ref}",
        summary=(
            f"Selected {len(value.selected_candidate_refs)}, injected {len(value.injected_candidate_refs)}, "
            f"and materially used {len(value.decision_material_candidate_refs)} candidates; benefit is unknown."
        ),
        subject_refs=tuple(sorted({value.receiver_ref, *value.selected_candidate_refs})),
        provenance=(manifest_reference,),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(value.model_dump(mode="json"))),
    )


def _lineage_record(
    record: ImmutableRecordV1,
    value: MemoryContextLineageV1Alpha1,
    manifest_reference: IntelligenceResourceReferenceV1Alpha1,
) -> IntelligenceResourceRecordV1Alpha1:
    payload = value.model_dump(mode="json")
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=record.product_id,
            resource_kind=IntelligenceResourceKind.EVIDENCE_LINEAGE,
            resource_id=str(value.lineage_id),
            resource_digest=f"sha256:{canonical_hash(payload)}",
            resource_contract=value.contract,
            revision=1,
            as_of=record.as_of,
            available_at=record.available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"Memory evidence: {value.assertion_ref}",
        summary="Exact assertion-to-context lineage; no authority or benefit is implied.",
        subject_refs=tuple(
            sorted(
                item
                for item in {
                    value.scope.actor_id,
                    value.scope.session_id,
                    value.scope.source_id,
                    value.assertion_ref,
                }
                if item is not None
            )
        ),
        provenance=(manifest_reference,),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(payload)),
    )


def _after_cursor(
    records: Iterable[IntelligenceResourceRecordV1Alpha1],
    cursor: IntelligenceResourceCursorV1Alpha1 | None,
) -> list[IntelligenceResourceRecordV1Alpha1]:
    ordered = sorted(
        records,
        key=lambda item: (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        ),
    )
    if cursor is None:
        return ordered
    after = (
        cursor.after_available_at,
        cursor.after_resource_kind.value,
        cursor.after_resource_id,
        cursor.after_revision,
    )
    return [
        item
        for item in ordered
        if (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        )
        > after
    ]


class AgentMemoryResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project authorized memory selection and actual-use evidence across product-fenced scopes."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return AGENT_MEMORY_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & AGENT_MEMORY_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - AGENT_MEMORY_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if not relevant:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            product_records = await self.store.scan_product_records(product_id=query.product_id)
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:scan-agent-memory",),
            )
        eligible = tuple(
            record
            for record in product_records
            if _is_am3_record(record) and record.available_at <= query.available_at and record.as_of <= query.as_of
        )
        manifests: dict[str, tuple[ImmutableRecordV1, CanonicalContextManifestV1]] = {}
        for record in eligible:
            if record.record_kind != CONTEXT_MANIFEST_RECORD_KIND:
                continue
            try:
                value = _decode_manifest(record)
                if str(value.artifact_id) in manifests:
                    raise ValueError("duplicate Context Manifest identity")
                manifests[str(value.artifact_id)] = (record, value)
            except Exception:
                degraded.add("degraded_reason:invalid-context-manifest")

        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        if IntelligenceResourceKind.CONTEXT_MANIFEST in relevant:
            projected.extend(_manifest_record(record, value) for record, value in manifests.values())
        for record in eligible:
            try:
                if record.record_kind == CONTEXT_USE_RECORD_KIND and IntelligenceResourceKind.MEMORY_USE in relevant:
                    value = _decode_use(record)
                    manifest = manifests.get(value.manifest_ref)
                    if manifest is None or manifest[0].record_space != record.record_space:
                        raise ValueError("Memory Use lacks exact Context Manifest")
                    projected.append(
                        _use_record(
                            record,
                            value,
                            _manifest_reference(product_id=query.product_id, manifest=manifest[1], record=manifest[0]),
                        )
                    )
                elif (
                    record.record_kind == MEMORY_CONTEXT_LINEAGE_RECORD_KIND
                    and IntelligenceResourceKind.EVIDENCE_LINEAGE in relevant
                ):
                    value = _decode_lineage(record)
                    manifest = manifests.get(value.context_manifest_id)
                    if manifest is None or manifest[0].record_space != record.record_space:
                        raise ValueError("memory lineage lacks exact Context Manifest")
                    projected.append(
                        _lineage_record(
                            record,
                            value,
                            _manifest_reference(product_id=query.product_id, manifest=manifest[1], record=manifest[0]),
                        )
                    )
            except Exception:
                degraded.add(f"degraded_reason:invalid-{record.record_kind}")
        for item in projected:
            degraded.update(item.degraded_reason_refs)
        if query.subject_refs:
            subjects = set(query.subject_refs)
            projected = [item for item in projected if not subjects.isdisjoint(item.subject_refs)]
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = ["AGENT_MEMORY_RESOURCE_KINDS", "AgentMemoryResourceProjectionReader"]
