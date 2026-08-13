"""Rebuildable public Action projections over Core's governed execution ledger."""

from __future__ import annotations

from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.core.action_execution import (
    ACTION_RECORD_SPACE,
    ActionAdmissionV1Alpha1,
    ActionTerminalV1Alpha1,
)
from ace.core.contracts import canonical_json
from ace.core.decisions import DecisionV1Alpha1
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
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

ACTION_RESOURCE_KINDS = frozenset({IntelligenceResourceKind.ACTION})


def _decode_admission(record: ImmutableRecordV1) -> ActionAdmissionV1Alpha1:
    value = ActionAdmissionV1Alpha1.model_validate(record.payload)
    if (
        record.product_id != value.product_id
        or record.record_space != ACTION_RECORD_SPACE
        or record.record_kind != "action_admission"
        or record.record_key != value.receipt_id
        or record.payload_contract != value.contract
        or record.as_of != value.intent.requested_at
        or record.available_at != value.admitted_at
    ):
        raise ValueError("Action admission envelope mismatch")
    return value


def _decode_terminal(
    record: ImmutableRecordV1,
    admission: ActionAdmissionV1Alpha1,
) -> ActionTerminalV1Alpha1:
    value = ActionTerminalV1Alpha1.model_validate(record.payload)
    if (
        record.product_id != value.product_id
        or record.record_space != ACTION_RECORD_SPACE
        or record.record_kind != "action_terminal"
        or record.record_key != value.receipt_id
        or record.payload_contract != value.contract
        or record.as_of != admission.intent.requested_at
        or record.available_at != value.result.completed_at
        or value.product_id != admission.product_id
        or value.action_key != admission.intent.action_key
        or value.admission != admission.reference()
        or value.result.completed_at < admission.admitted_at
    ):
        raise ValueError("Action terminal envelope mismatch")
    return value


async def _decision_reference(
    store: ImmutableRecordStore,
    admission: ActionAdmissionV1Alpha1,
) -> IntelligenceResourceReferenceV1Alpha1:
    expected = admission.intent.decision
    record = await store.load_record(
        expected.storage_id,
        product_id=expected.product_id,
        record_space=expected.record_space,
        record_kind=expected.record_kind,
    )
    if record is None or record.reference() != expected:
        raise ValueError("Action Decision is unavailable")
    decision = DecisionV1Alpha1.model_validate(record.payload)
    if (
        record.payload_contract != decision.contract
        or record.record_key != decision.decision_id
        or record.product_id != admission.product_id
        or record.available_at > admission.admitted_at
    ):
        raise ValueError("Action Decision envelope mismatch")
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=record.product_id,
        resource_kind=IntelligenceResourceKind.DECISION,
        resource_id=record.record_key,
        resource_digest=record.material_hash,
        resource_contract=record.payload_contract,
        revision=1,
        as_of=record.as_of,
        available_at=record.available_at,
    )


def _admission_reference(admission: ActionAdmissionV1Alpha1) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=admission.product_id,
        resource_kind=IntelligenceResourceKind.ACTION,
        resource_id=admission.intent.action_key,
        resource_digest=str(admission.receipt_digest),
        resource_contract=admission.contract,
        revision=1,
        as_of=admission.intent.requested_at,
        available_at=admission.admitted_at,
    )


def _action_record(
    *,
    admission: ActionAdmissionV1Alpha1,
    terminal: ActionTerminalV1Alpha1 | None,
    decision: IntelligenceResourceReferenceV1Alpha1,
) -> IntelligenceResourceRecordV1Alpha1:
    prior = _admission_reference(admission)
    if terminal is None:
        reference = prior
        availability = IntelligenceResourceAvailability.DEGRADED
        summary = "Action was durably admitted; terminal effect state is not yet recorded."
        payload = admission.model_dump(mode="json")
        reasons = ("degraded_reason:action-terminal-pending",)
    else:
        reference = IntelligenceResourceReferenceV1Alpha1(
            product_id=terminal.product_id,
            resource_kind=IntelligenceResourceKind.ACTION,
            resource_id=terminal.action_key,
            resource_digest=str(terminal.receipt_digest),
            resource_contract=terminal.contract,
            revision=2,
            as_of=admission.intent.requested_at,
            available_at=terminal.result.completed_at,
        )
        availability = IntelligenceResourceAvailability.AVAILABLE
        summary = (
            f"Action finished {terminal.result.disposition.value}; "
            f"effect state is {terminal.result.effect_state.value}."
        )
        payload = terminal.model_dump(mode="json")
        reasons = ()
    return IntelligenceResourceRecordV1Alpha1(
        reference=reference,
        availability=availability,
        title=f"Action: {admission.intent.action_type}",
        summary=summary,
        subject_refs=tuple(
            sorted(
                {
                    admission.intent.authenticated_context.actor_ref,
                    admission.intent.action_type,
                    admission.plan.target_ref,
                    admission.intent.decision.record_key,
                }
            )
        ),
        provenance=(decision,),
        supersedes=(prior if terminal is not None else None),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(payload)),
        degraded_reason_refs=reasons,
    )


def _after_cursor(
    records: list[IntelligenceResourceRecordV1Alpha1],
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


class ActionResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project current Action state with exact Decision provenance and terminal honesty."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return ACTION_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - ACTION_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if IntelligenceResourceKind.ACTION not in requested:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            admission_records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=ACTION_RECORD_SPACE,
                record_kind="action_admission",
                available_at=query.available_at,
            )
            terminal_records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=ACTION_RECORD_SPACE,
                record_kind="action_terminal",
                available_at=query.available_at,
            )
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:read-action-execution",),
            )
        admissions: dict[str, tuple[ActionAdmissionV1Alpha1, ImmutableRecordV1]] = {}
        for record in admission_records:
            try:
                admission = _decode_admission(record)
                if admission.intent.action_key in admissions:
                    raise ValueError("duplicate Action key")
                admissions[admission.intent.action_key] = (admission, record)
            except Exception:
                degraded.add("degraded_reason:invalid-action-admission")
        terminals: dict[str, ActionTerminalV1Alpha1] = {}
        for record in terminal_records:
            try:
                raw = ActionTerminalV1Alpha1.model_validate(record.payload)
                matched = next(
                    (admission for admission, _ in admissions.values() if admission.reference() == raw.admission),
                    None,
                )
                if matched is None or raw.action_key in terminals:
                    raise ValueError("Action terminal lacks one exact admission")
                terminals[raw.action_key] = _decode_terminal(record, matched)
            except Exception:
                degraded.add("degraded_reason:invalid-action-terminal")
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        for action_key, (admission, _) in admissions.items():
            if admission.intent.requested_at > query.as_of:
                continue
            try:
                item = _action_record(
                    admission=admission,
                    terminal=terminals.get(action_key),
                    decision=await _decision_reference(self.store, admission),
                )
                if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                    continue
                degraded.update(item.degraded_reason_refs)
                projected.append(item)
            except Exception:
                degraded.add("degraded_reason:invalid-action-decision-lineage")
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = ["ACTION_RESOURCE_KINDS", "ActionResourceProjectionReader"]
