"""Rebuildable resource-plane projections over the immutable Intelligence ledgers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, TypeAdapter

from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.application.monitoring import LIVE_MONITORING_RECORD_SPACE
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.decisions import DecisionV1Alpha1, OutcomeV1Alpha1
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
from ace.core.source import CanonicalSourceSnapshotV1Alpha1
from ace.intelligence.contracts.feedback import FeedbackProposalV1Alpha1
from ace.intelligence.contracts.impact import ImpactGovernanceProposalV1Alpha1
from ace.intelligence.contracts.ledger import IntelligenceRecordKind
from ace.intelligence.contracts.monitoring import (
    MONITORING_LIFECYCLE_RECORD_KIND,
    MonitoringLifecycleReceiptV1Alpha1,
    MonitoringLifecycleState,
    MonitoringTargetKind,
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
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    CaseV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.contracts.source_acquisition import (
    LiveSourceAdmissionReceiptV1Alpha1,
    LiveSourceIngressRecordKind,
    SourceAcquisitionReceiptV1Alpha1,
)

_JSON_OBJECT = TypeAdapter(dict[str, Any])

_RESOURCE_MODELS: dict[IntelligenceRecordKind, type[BaseModel]] = {
    IntelligenceRecordKind.OBSERVATION: ObservationV1Alpha1,
    IntelligenceRecordKind.ENTITY_SNAPSHOT: EntitySnapshotV1Alpha1,
    IntelligenceRecordKind.SHIFT: ShiftV1Alpha1,
    IntelligenceRecordKind.SIGNAL: SignalV1Alpha1,
    IntelligenceRecordKind.CASE: CaseV1Alpha1,
    IntelligenceRecordKind.BRIEF: BriefV1Alpha1,
}
_PUBLIC_TO_LEDGER: dict[IntelligenceResourceKind, IntelligenceRecordKind] = {
    IntelligenceResourceKind.OBSERVATION: IntelligenceRecordKind.OBSERVATION,
    IntelligenceResourceKind.ENTITY: IntelligenceRecordKind.ENTITY_SNAPSHOT,
    IntelligenceResourceKind.SHIFT: IntelligenceRecordKind.SHIFT,
    IntelligenceResourceKind.SIGNAL: IntelligenceRecordKind.SIGNAL,
    IntelligenceResourceKind.CASE: IntelligenceRecordKind.CASE,
    IntelligenceResourceKind.BRIEF: IntelligenceRecordKind.BRIEF,
}
_LEDGER_TO_PUBLIC = {value: key for key, value in _PUBLIC_TO_LEDGER.items()}
LEDGER_RESOURCE_KINDS = frozenset(_PUBLIC_TO_LEDGER)
MONITORING_RESOURCE_KINDS = frozenset({IntelligenceResourceKind.MONITOR, IntelligenceResourceKind.SUBSCRIPTION})
DECISION_OUTCOME_FEEDBACK_RESOURCE_KINDS = frozenset(
    {
        IntelligenceResourceKind.DECISION,
        IntelligenceResourceKind.OUTCOME,
        IntelligenceResourceKind.FEEDBACK,
    }
)
LIVE_SOURCE_RESOURCE_KINDS = frozenset(
    {
        IntelligenceResourceKind.CONNECTION,
        IntelligenceResourceKind.SOURCE,
    }
)
_LINEAGE_TO_PUBLIC: dict[LineageResourceKind, IntelligenceResourceKind] = {
    LineageResourceKind.OBSERVATION: IntelligenceResourceKind.OBSERVATION,
    LineageResourceKind.ENTITY_SNAPSHOT: IntelligenceResourceKind.ENTITY,
    LineageResourceKind.SIGNAL: IntelligenceResourceKind.SIGNAL,
    LineageResourceKind.SHIFT: IntelligenceResourceKind.SHIFT,
    LineageResourceKind.CASE: IntelligenceResourceKind.CASE,
    LineageResourceKind.BRIEF: IntelligenceResourceKind.BRIEF,
}
_LINEAGE_CONTRACTS: dict[LineageResourceKind, str] = {
    LineageResourceKind.OBSERVATION: "ace.intelligence.observation/v1alpha1",
    LineageResourceKind.ENTITY_SNAPSHOT: "ace.intelligence.entity-snapshot/v1alpha1",
    LineageResourceKind.SIGNAL: "ace.intelligence.signal/v1alpha1",
    LineageResourceKind.SHIFT: "ace.intelligence.shift/v1alpha1",
    LineageResourceKind.CASE: "ace.intelligence.case/v1alpha1",
    LineageResourceKind.BRIEF: "ace.intelligence.brief/v1alpha1",
}


class IntelligenceLedgerProjectionError(RuntimeError):
    """An immutable ledger record could not be projected exactly."""


class IntelligenceResourceProjectionContributor(Protocol):
    """A disjoint owner of one or more public resource projection families."""

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]: ...

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch: ...


def _resource_times(resource: BaseModel) -> tuple[datetime, datetime]:
    as_of = resource.as_of
    if isinstance(resource, ObservationV1Alpha1):
        return as_of, resource.ingested_at
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return as_of, resource.projected_at
    if isinstance(resource, (ShiftV1Alpha1, SignalV1Alpha1)):
        return as_of, resource.detected_at
    if isinstance(resource, CaseV1Alpha1):
        return as_of, resource.assembled_at
    if isinstance(resource, BriefV1Alpha1):
        return as_of, resource.generated_at
    raise IntelligenceLedgerProjectionError("unsupported immutable Intelligence resource")


def _resource_title(resource: BaseModel) -> str:
    if isinstance(resource, ObservationV1Alpha1):
        return f"Observation from {resource.source_ref}"
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return resource.entity_ref
    return str(resource.title)


def _resource_summary(resource: BaseModel) -> str | None:
    if isinstance(resource, (ShiftV1Alpha1, SignalV1Alpha1)):
        return resource.summary
    if isinstance(resource, CaseV1Alpha1):
        return resource.purpose
    if isinstance(resource, BriefV1Alpha1):
        return resource.executive_summary
    return None


def _resource_subjects(resource: BaseModel) -> tuple[str, ...]:
    if isinstance(resource, EntitySnapshotV1Alpha1):
        return (resource.entity_ref,)
    if isinstance(resource, (ObservationV1Alpha1, ShiftV1Alpha1, SignalV1Alpha1, CaseV1Alpha1)):
        return resource.subject_refs
    return ()


def _lineage_reference(
    lineage: LineageReferenceV1Alpha1,
    *,
    product_id: str,
) -> IntelligenceResourceReferenceV1Alpha1:
    if lineage.resource_kind not in _LINEAGE_TO_PUBLIC:
        raise IntelligenceLedgerProjectionError(
            "lineage kind lacks an exact resource contract in this projection slice"
        )
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=_LINEAGE_TO_PUBLIC[lineage.resource_kind],
        resource_id=lineage.resource_id,
        resource_digest=lineage.resource_digest,
        resource_contract=_LINEAGE_CONTRACTS[lineage.resource_kind],
        revision=1,
        as_of=lineage.resource_as_of,
        available_at=lineage.resource_available_at,
    )


def _decode_record(
    record: ImmutableRecordV1,
    *,
    mode: IntelligenceResourceMode,
    ledger_kind: IntelligenceRecordKind,
) -> BaseModel:
    model = _RESOURCE_MODELS[ledger_kind]
    if record.record_space != mode.value or record.record_kind != ledger_kind.value:
        raise IntelligenceLedgerProjectionError("immutable record crossed its ledger bucket")
    try:
        resource = model.model_validate_json(_JSON_OBJECT.dump_json(record.payload))
    except (TypeError, ValueError) as exc:
        raise IntelligenceLedgerProjectionError("immutable Intelligence payload failed exact replay") from exc
    as_of, available_at = _resource_times(resource)
    source_ingress_availability = (
        mode is IntelligenceResourceMode.LIVE
        and isinstance(resource, (ObservationV1Alpha1, EntitySnapshotV1Alpha1))
        and available_at <= record.available_at
    )
    if (
        resource.product_id != record.product_id
        or resource.mode is not mode
        or resource.resource_id != record.record_key
        or resource.contract != record.payload_contract
        or as_of != record.as_of
        or (available_at != record.available_at and not source_ingress_availability)
    ):
        raise IntelligenceLedgerProjectionError("immutable record envelope does not match its Intelligence payload")
    return resource


def _project_record(
    record: ImmutableRecordV1,
    *,
    mode: IntelligenceResourceMode,
    ledger_kind: IntelligenceRecordKind,
) -> IntelligenceResourceRecordV1Alpha1:
    resource = _decode_record(record, mode=mode, ledger_kind=ledger_kind)
    as_of, _ = _resource_times(resource)
    available_at = record.available_at
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=record.product_id,
            resource_kind=_LEDGER_TO_PUBLIC[ledger_kind],
            resource_id=str(resource.resource_id),
            resource_digest=str(resource.resource_digest),
            resource_contract=str(resource.contract),
            revision=1,
            as_of=as_of,
            available_at=available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=_resource_title(resource),
        summary=_resource_summary(resource),
        subject_refs=_resource_subjects(resource),
        provenance=tuple(_lineage_reference(item, product_id=record.product_id) for item in resource.lineage),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(resource.model_dump(mode="json"))),
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


class IntelligenceLedgerResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Rebuild the supported public resource slice from PREPARED and LIVE records."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        modes: tuple[IntelligenceResourceMode, ...] = (
            IntelligenceResourceMode.PREPARED,
            IntelligenceResourceMode.LIVE,
        ),
        degrade_unsupported: bool = True,
    ) -> None:
        if not modes or len(modes) != len(set(modes)):
            raise ValueError("projection modes must be a non-empty unique sequence")
        self.store = store
        self.modes = modes
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return LEDGER_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        degraded: set[str] = set()
        for public_kind in query.resource_kinds:
            ledger_kind = _PUBLIC_TO_LEDGER.get(public_kind)
            if ledger_kind is None:
                if self.degrade_unsupported:
                    degraded.add(f"degraded_reason:unsupported-{public_kind.value}")
                continue
            for mode in self.modes:
                try:
                    records = await self.store.read_as_of(
                        product_id=query.product_id,
                        record_space=mode.value,
                        record_kind=ledger_kind.value,
                        available_at=query.available_at,
                    )
                    projected.extend(
                        _project_record(record, mode=mode, ledger_kind=ledger_kind)
                        for record in records
                        if record.as_of <= query.as_of
                    )
                except Exception:
                    degraded.add(f"degraded_reason:read-{mode.value}-{ledger_kind.value}")

        if query.subject_refs:
            requested = set(query.subject_refs)
            projected = [item for item in projected if not requested.isdisjoint(item.subject_refs)]
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


def _monitoring_kind(receipt: MonitoringLifecycleReceiptV1Alpha1) -> IntelligenceResourceKind:
    if receipt.target_kind is MonitoringTargetKind.MONITOR:
        return IntelligenceResourceKind.MONITOR
    return IntelligenceResourceKind.SUBSCRIPTION


def _monitoring_reference(
    receipt: MonitoringLifecycleReceiptV1Alpha1,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=receipt.product_id,
        resource_kind=_monitoring_kind(receipt),
        resource_id=receipt.lifecycle.reference,
        resource_digest=str(receipt.receipt_digest),
        resource_contract=receipt.contract,
        revision=receipt.sequence,
        as_of=receipt.applied_at,
        available_at=receipt.applied_at,
    )


def _monitoring_projection(
    receipt: MonitoringLifecycleReceiptV1Alpha1,
    *,
    previous: MonitoringLifecycleReceiptV1Alpha1 | None,
) -> IntelligenceResourceRecordV1Alpha1:
    tombstoned = receipt.state_after is MonitoringLifecycleState.REVOKED
    label = "Monitor" if receipt.target_kind is MonitoringTargetKind.MONITOR else "Subscription"
    return IntelligenceResourceRecordV1Alpha1(
        reference=_monitoring_reference(receipt),
        availability=(
            IntelligenceResourceAvailability.TOMBSTONED if tombstoned else IntelligenceResourceAvailability.AVAILABLE
        ),
        title=f"{label}: {receipt.target.reference}",
        summary=f"{label} lifecycle is {receipt.state_after.value}.",
        subject_refs=tuple(
            sorted(
                {
                    receipt.owner_ref,
                    receipt.persona_binding.reference,
                    receipt.target.reference,
                }
            )
        ),
        supersedes=_monitoring_reference(previous) if previous is not None else None,
        payload=(
            None
            if tombstoned
            else CanonicalJsonValueV1Alpha1(value_json=canonical_json(receipt.model_dump(mode="json")))
        ),
    )


class MonitoringResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project current Monitor and Subscription lifecycle revisions."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        degrade_unsupported: bool = True,
    ) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return MONITORING_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & MONITORING_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - MONITORING_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if not relevant:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                record_kind=MONITORING_LIFECYCLE_RECORD_KIND,
                available_at=query.available_at,
            )
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:read-monitoring-lifecycle",),
            )

        chains: dict[str, list[MonitoringLifecycleReceiptV1Alpha1]] = defaultdict(list)
        for record in records:
            try:
                receipt = MonitoringLifecycleReceiptV1Alpha1.model_validate(record.payload)
                if (
                    record.product_id != query.product_id
                    or record.record_space != LIVE_MONITORING_RECORD_SPACE
                    or record.record_kind != MONITORING_LIFECYCLE_RECORD_KIND
                    or record.record_key != receipt.receipt_id
                    or record.payload_contract != receipt.contract
                    or record.as_of != receipt.applied_at
                    or record.available_at != receipt.applied_at
                ):
                    raise ValueError("monitoring envelope mismatch")
                if _monitoring_kind(receipt) not in relevant:
                    continue
                if receipt.applied_at <= query.as_of:
                    chains[receipt.lifecycle.reference].append(receipt)
            except Exception:
                degraded.add("degraded_reason:invalid-monitoring-lifecycle")

        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        for lifecycle_id, chain in chains.items():
            ordered = sorted(chain, key=lambda item: item.sequence)
            if [item.sequence for item in ordered] != list(range(1, len(ordered) + 1)):
                degraded.add(f"degraded_reason:incomplete-{lifecycle_id}")
                continue
            if any(
                current.prior_receipt != previous.reference() or current.state_before is not previous.state_after
                for previous, current in zip(ordered, ordered[1:])
            ):
                degraded.add(f"degraded_reason:divergent-{lifecycle_id}")
                continue
            current = ordered[-1]
            public_kind = _monitoring_kind(current)
            if public_kind not in relevant:
                continue
            item = _monitoring_projection(
                current,
                previous=ordered[-2] if len(ordered) > 1 else None,
            )
            if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                continue
            projected.append(item)

        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


_DECISION_RESOURCE_MODELS: dict[
    IntelligenceResourceKind,
    tuple[
        tuple[
            str,
            type[DecisionV1Alpha1 | OutcomeV1Alpha1 | FeedbackProposalV1Alpha1 | ImpactGovernanceProposalV1Alpha1],
        ],
        ...,
    ],
] = {
    IntelligenceResourceKind.DECISION: (("decision", DecisionV1Alpha1),),
    IntelligenceResourceKind.OUTCOME: (("outcome", OutcomeV1Alpha1),),
    IntelligenceResourceKind.FEEDBACK: (
        ("feedback_proposal", FeedbackProposalV1Alpha1),
        ("impact_governance_proposal", ImpactGovernanceProposalV1Alpha1),
    ),
}


def _immutable_reference(
    record,
    *,
    kind: IntelligenceResourceKind,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=record.product_id,
        resource_kind=kind,
        resource_id=record.record_key,
        resource_digest=record.material_hash,
        resource_contract=record.payload_contract,
        revision=1,
        as_of=record.as_of,
        available_at=record.available_at,
    )


def _record_reference(
    reference,
    *,
    kind: IntelligenceResourceKind,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=reference.product_id,
        resource_kind=kind,
        resource_id=reference.record_key,
        resource_digest=reference.material_hash,
        resource_contract=reference.payload_contract,
        revision=1,
        as_of=reference.as_of,
        available_at=reference.available_at,
    )


def _decision_loop_projection(
    record: ImmutableRecordV1,
    *,
    kind: IntelligenceResourceKind,
    value: DecisionV1Alpha1 | OutcomeV1Alpha1 | FeedbackProposalV1Alpha1 | ImpactGovernanceProposalV1Alpha1,
    decision_subject: IntelligenceResourceReferenceV1Alpha1 | None = None,
) -> IntelligenceResourceRecordV1Alpha1:
    payload = CanonicalJsonValueV1Alpha1(value_json=canonical_json(value.model_dump(mode="json")))
    availability = IntelligenceResourceAvailability.AVAILABLE
    degraded_reason_refs: tuple[str, ...] = ()
    if isinstance(value, DecisionV1Alpha1):
        subject = value.intent.subject
        if decision_subject is not None:
            provenance = (decision_subject,)
        elif subject.record_kind == "brief":
            provenance = ()
            availability = IntelligenceResourceAvailability.DEGRADED
            degraded_reason_refs = ("degraded_reason:unresolved-decision-subject",)
        else:
            provenance = ()
            availability = IntelligenceResourceAvailability.DEGRADED
            degraded_reason_refs = ("degraded_reason:unsupported-decision-subject",)
        title = f"Decision: {value.intent.decision_type}"
        summary = (
            f"Disposition is {value.intent.disposition.value}; "
            f"action disposition is {value.intent.action_disposition.value}."
        )
        subject_refs = (
            value.intent.authenticated_context.actor_ref,
            value.intent.actor_role_ref,
            subject.record_key,
        )
    elif isinstance(value, OutcomeV1Alpha1):
        provenance = (_record_reference(value.intent.decision, kind=IntelligenceResourceKind.DECISION),)
        title = f"Outcome: {value.intent.outcome_type}"
        summary = f"Observed measure {value.intent.measure_id}."
        subject_refs = (
            value.intent.authenticated_context.actor_ref,
            value.intent.decision.record_key,
            value.intent.measure_id,
        )
    elif isinstance(value, FeedbackProposalV1Alpha1):
        provenance = (
            _record_reference(value.intent.decision, kind=IntelligenceResourceKind.DECISION),
            _record_reference(value.intent.outcome, kind=IntelligenceResourceKind.OUTCOME),
        )
        title = f"Feedback proposal: {value.intent.policy_id}"
        summary = f"Proposes policy value {value.intent.prior_value} → {value.intent.proposed_value}."
        subject_refs = (
            value.intent.decision.record_key,
            value.intent.outcome.record_key,
            value.intent.policy_id,
        )
    else:
        if value.target.record_kind == IntelligenceRecordKind.BRIEF.value:
            provenance = (_record_reference(value.target, kind=IntelligenceResourceKind.BRIEF),)
        else:
            provenance = ()
            availability = IntelligenceResourceAvailability.DEGRADED
            degraded_reason_refs = ("degraded_reason:unsupported-impact-target",)
        title = f"Feedback proposal: {value.action.value}"
        summary = value.rationale
        subject_refs = (
            value.evaluation_id,
            value.target.record_key,
        )
    return IntelligenceResourceRecordV1Alpha1(
        reference=_immutable_reference(record, kind=kind),
        availability=availability,
        title=title,
        summary=summary,
        subject_refs=tuple(sorted(set(subject_refs))),
        provenance=provenance,
        payload=payload,
        degraded_reason_refs=degraded_reason_refs,
    )


def _decision_loop_envelope_is_exact(
    record: ImmutableRecordV1,
    *,
    kind: IntelligenceResourceKind,
    value: DecisionV1Alpha1 | OutcomeV1Alpha1 | FeedbackProposalV1Alpha1 | ImpactGovernanceProposalV1Alpha1,
) -> bool:
    if isinstance(value, ImpactGovernanceProposalV1Alpha1):
        return (
            kind is IntelligenceResourceKind.FEEDBACK
            and record.product_id == value.product_id
            and record.record_kind == "impact_governance_proposal"
            and record.record_key == value.proposal_id
            and record.payload_contract == value.contract
            and record.available_at == value.proposed_at
            and record.as_of <= value.proposed_at
            and value.live_effect is False
            and value.selectable is False
        )
    if (
        record.product_id != value.intent.product_id
        or record.payload_contract != value.contract
        or record.available_at != value.authorization.authorized_at
    ):
        return False
    if isinstance(value, DecisionV1Alpha1):
        return (
            kind is IntelligenceResourceKind.DECISION
            and record.record_kind == "decision"
            and record.record_key == value.decision_id
            and record.as_of == value.intent.decided_at
        )
    if isinstance(value, OutcomeV1Alpha1):
        return (
            kind is IntelligenceResourceKind.OUTCOME
            and record.record_kind == "outcome"
            and record.record_key == value.outcome_id
            and record.as_of == value.intent.observed_at
        )
    return (
        kind is IntelligenceResourceKind.FEEDBACK
        and record.record_kind == "feedback_proposal"
        and record.record_key == value.proposal_id
        and record.as_of == value.intent.outcome.as_of
    )


async def _decision_subject_reference(
    store: ImmutableRecordStore,
    value: DecisionV1Alpha1,
) -> IntelligenceResourceReferenceV1Alpha1 | None:
    subject = value.intent.subject
    if subject.record_kind != "brief" or subject.record_space not in {
        IntelligenceResourceMode.PREPARED.value,
        IntelligenceResourceMode.LIVE.value,
    }:
        return None
    try:
        stored = await store.load_record(
            subject.storage_id,
            product_id=subject.product_id,
            record_space=subject.record_space,
            record_kind=subject.record_kind,
        )
        if stored is None or stored.reference() != subject:
            return None
        mode = IntelligenceResourceMode(subject.record_space)
        return _project_record(
            stored,
            mode=mode,
            ledger_kind=IntelligenceRecordKind.BRIEF,
        ).reference
    except Exception:
        return None


class DecisionOutcomeFeedbackResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project product-fenced Decisions, Outcomes, and non-effective Feedback proposals."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return DECISION_OUTCOME_FEEDBACK_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & DECISION_OUTCOME_FEEDBACK_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - DECISION_OUTCOME_FEEDBACK_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        try:
            product_records = await self.store.scan_product_records(product_id=query.product_id)
        except Exception:
            product_records = ()
            degraded.add("degraded_reason:read-decision-loop")
        for kind in sorted(relevant, key=lambda item: item.value):
            for record_kind, model in _DECISION_RESOURCE_MODELS[kind]:
                records = (
                    record
                    for record in product_records
                    if record.record_kind == record_kind
                    and record.available_at <= query.available_at
                    and record.as_of <= query.as_of
                )
                for record in records:
                    try:
                        value = model.model_validate(record.payload)
                        if not _decision_loop_envelope_is_exact(record, kind=kind, value=value):
                            raise ValueError("decision-loop envelope mismatch")
                        decision_subject = (
                            await _decision_subject_reference(self.store, value)
                            if isinstance(value, DecisionV1Alpha1)
                            else None
                        )
                        item = _decision_loop_projection(
                            record,
                            kind=kind,
                            value=value,
                            decision_subject=decision_subject,
                        )
                        if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                            continue
                        degraded.update(item.degraded_reason_refs)
                        projected.append(item)
                    except Exception:
                        degraded.add(f"degraded_reason:invalid-{record_kind}")
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


def _source_reference(
    *,
    product_id: str,
    source_definition_ref: str,
    snapshot: CanonicalSourceSnapshotV1Alpha1,
    admission: LiveSourceAdmissionReceiptV1Alpha1,
    revision: int,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=IntelligenceResourceKind.SOURCE,
        resource_id=source_definition_ref,
        resource_digest=str(snapshot.source_snapshot_digest),
        resource_contract=snapshot.contract,
        revision=revision,
        as_of=snapshot.as_of,
        available_at=admission.admitted_at,
    )


def _connection_reference(
    *,
    product_id: str,
    source_definition_ref: str,
    acquisition: SourceAcquisitionReceiptV1Alpha1,
    admission: LiveSourceAdmissionReceiptV1Alpha1,
    revision: int,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=IntelligenceResourceKind.CONNECTION,
        resource_id=f"connection:{canonical_hash([product_id, source_definition_ref])[:32]}",
        resource_digest=str(admission.receipt_digest),
        resource_contract=admission.contract,
        revision=revision,
        as_of=acquisition.captured_at,
        available_at=admission.admitted_at,
    )


def _live_source_records(
    *,
    acquisition: SourceAcquisitionReceiptV1Alpha1,
    snapshot: CanonicalSourceSnapshotV1Alpha1,
    admission: LiveSourceAdmissionReceiptV1Alpha1,
    revision: int,
    prior_connection: IntelligenceResourceReferenceV1Alpha1 | None = None,
    prior_source: IntelligenceResourceReferenceV1Alpha1 | None = None,
) -> tuple[IntelligenceResourceRecordV1Alpha1, IntelligenceResourceRecordV1Alpha1]:
    source_definition_ref = acquisition.source_definition_ref
    source_reference = _source_reference(
        product_id=acquisition.product_id,
        source_definition_ref=source_definition_ref,
        snapshot=snapshot,
        admission=admission,
        revision=revision,
    )
    connection_reference = _connection_reference(
        product_id=acquisition.product_id,
        source_definition_ref=source_definition_ref,
        acquisition=acquisition,
        admission=admission,
        revision=revision,
    )
    if revision == 1 and (prior_connection is not None or prior_source is not None):
        raise ValueError("first live source revision cannot supersede prior material")
    if revision > 1 and (
        prior_connection is None
        or prior_source is None
        or prior_connection.resource_id != connection_reference.resource_id
        or prior_source.resource_id != source_reference.resource_id
        or prior_connection.revision != revision - 1
        or prior_source.revision != revision - 1
    ):
        raise ValueError("later live source revision requires both exact prior references")
    connection_payload = {
        "actor_ref": acquisition.actor_ref,
        "source_definition_ref": source_definition_ref,
        "source_type_ref": acquisition.source_type_ref,
        "configuration_ref": acquisition.configuration_ref,
        "configuration_digest": acquisition.configuration_digest,
        "adapter_artifact": acquisition.adapter_artifact.model_dump(mode="json"),
        "capability_use_receipt_ref": admission.capability_use_receipt_ref,
        "capability_use_receipt_digest": admission.capability_use_receipt_digest,
        "authority_use_receipt_ref": admission.authority_use_receipt_ref,
        "authority_use_receipt_digest": admission.authority_use_receipt_digest,
        "acquisition_receipt_ref": str(acquisition.receipt_id),
        "acquisition_receipt_digest": str(acquisition.receipt_digest),
        "admission_receipt_ref": str(admission.receipt_id),
        "admission_receipt_digest": str(admission.receipt_digest),
        "captured_at": acquisition.captured_at.isoformat(),
        "admitted_at": admission.admitted_at.isoformat(),
    }
    source_payload = {
        "source_definition_ref": source_definition_ref,
        "source_type_ref": snapshot.source_type_ref,
        "source_snapshot_ref": str(snapshot.source_snapshot_ref),
        "source_snapshot_digest": str(snapshot.source_snapshot_digest),
        "source_published_at": (
            None if snapshot.source_published_at is None else snapshot.source_published_at.isoformat()
        ),
        "event_effective_at": (
            None if snapshot.event_effective_at is None else snapshot.event_effective_at.isoformat()
        ),
        "observed_at": snapshot.observed_at.isoformat(),
        "ingested_at": snapshot.ingested_at.isoformat(),
        "acquisition_receipt_ref": str(acquisition.receipt_id),
        "acquisition_receipt_digest": str(acquisition.receipt_digest),
        "admission_receipt_ref": str(admission.receipt_id),
        "admission_receipt_digest": str(admission.receipt_digest),
        "captured_payload_redacted": True,
    }
    subjects = tuple(
        sorted(
            {
                acquisition.actor_ref,
                source_definition_ref,
                acquisition.source_type_ref,
            }
        )
    )
    connection = IntelligenceResourceRecordV1Alpha1(
        reference=connection_reference,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"Connection: {source_definition_ref}",
        summary=f"Successful governed capture through {acquisition.adapter_artifact.implementation_id}.",
        subject_refs=subjects,
        supersedes=prior_connection,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(connection_payload)),
    )
    source = IntelligenceResourceRecordV1Alpha1(
        reference=source_reference,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"Source: {source_definition_ref}",
        summary=f"Latest admitted {snapshot.source_type_ref} capture metadata; captured payload is redacted.",
        subject_refs=subjects,
        provenance=(connection_reference,),
        supersedes=prior_source,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(source_payload)),
    )
    return connection, source


def _decode_live_source_chain(
    *,
    acquisition_record: ImmutableRecordV1,
    snapshot_record: ImmutableRecordV1,
    admission_record: ImmutableRecordV1,
) -> tuple[SourceAcquisitionReceiptV1Alpha1, CanonicalSourceSnapshotV1Alpha1, LiveSourceAdmissionReceiptV1Alpha1]:
    acquisition = SourceAcquisitionReceiptV1Alpha1.model_validate(acquisition_record.payload)
    snapshot = CanonicalSourceSnapshotV1Alpha1.model_validate(snapshot_record.payload)
    admission = LiveSourceAdmissionReceiptV1Alpha1.model_validate(admission_record.payload)
    if (
        len({acquisition_record.product_id, snapshot_record.product_id, admission_record.product_id}) != 1
        or acquisition_record.record_space != IntelligenceResourceMode.LIVE.value
        or snapshot_record.record_space != IntelligenceResourceMode.LIVE.value
        or admission_record.record_space != IntelligenceResourceMode.LIVE.value
        or acquisition_record.record_kind != LiveSourceIngressRecordKind.SOURCE_ACQUISITION.value
        or snapshot_record.record_kind != LiveSourceIngressRecordKind.SOURCE_SNAPSHOT.value
        or admission_record.record_kind != LiveSourceIngressRecordKind.SOURCE_ADMISSION.value
        or acquisition_record.record_key != acquisition.receipt_id
        or snapshot_record.record_key != snapshot.source_snapshot_ref
        or admission_record.record_key != admission.receipt_id
        or acquisition_record.payload_contract != acquisition.contract
        or snapshot_record.payload_contract != snapshot.contract
        or admission_record.payload_contract != admission.contract
        or acquisition_record.as_of != acquisition.captured_at
        or snapshot_record.as_of != snapshot.as_of
        or admission_record.as_of != admission.admitted_at
        or acquisition_record.available_at != admission.admitted_at
        or snapshot_record.available_at != admission.admitted_at
        or admission_record.available_at != admission.admitted_at
        or snapshot.acquisition_receipt_ref != acquisition.receipt_id
        or snapshot.acquisition_receipt_digest != acquisition.receipt_digest
        or admission.acquisition_receipt_ref != acquisition.receipt_id
        or admission.acquisition_receipt_digest != acquisition.receipt_digest
        or admission.source_snapshot_ref != snapshot.source_snapshot_ref
        or admission.source_snapshot_digest != snapshot.source_snapshot_digest
        or acquisition.product_id != admission.product_id
        or acquisition.actor_ref != admission.actor_ref
        or acquisition.use_subject_ref != admission.use_subject_ref
        or acquisition.use_subject_digest != admission.use_subject_digest
        or acquisition.operation != admission.operation
        or acquisition.source_definition_ref != snapshot.source_definition_ref
        or acquisition.source_type_ref != snapshot.source_type_ref
        or acquisition.source_definition_head_precondition != admission.source_definition_head_precondition
        or acquisition.receipt_id != snapshot.acquisition_receipt_ref
        or acquisition.receipt_digest != snapshot.acquisition_receipt_digest
        or acquisition.captured_payload_digest != snapshot.captured_payload_digest
        or acquisition.source_published_at != snapshot.source_published_at
        or acquisition.event_effective_at != snapshot.event_effective_at
        or acquisition.observed_at != snapshot.observed_at
        or acquisition.capability_use.receipt_id != admission.capability_use_receipt_ref
        or acquisition.capability_use.receipt_digest != admission.capability_use_receipt_digest
        or acquisition.authority_use.receipt_id != admission.authority_use_receipt_ref
        or acquisition.authority_use.receipt_digest != admission.authority_use_receipt_digest
        or admission.source_definition_head_precondition.state_id != acquisition.source_definition_ref
    ):
        raise ValueError("live source records do not form one exact admitted chain")
    return acquisition, snapshot, admission


class LiveSourceResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project successful governed captures as Connection and redacted Source revisions."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return LIVE_SOURCE_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & LIVE_SOURCE_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - LIVE_SOURCE_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if not relevant:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        buckets: dict[str, tuple[ImmutableRecordV1, ...]] = {}
        for kind in (
            LiveSourceIngressRecordKind.SOURCE_ACQUISITION,
            LiveSourceIngressRecordKind.SOURCE_SNAPSHOT,
            LiveSourceIngressRecordKind.SOURCE_ADMISSION,
        ):
            try:
                buckets[kind.value] = await self.store.read_as_of(
                    product_id=query.product_id,
                    record_space=IntelligenceResourceMode.LIVE.value,
                    record_kind=kind.value,
                    available_at=query.available_at,
                )
            except Exception:
                degraded.add(f"degraded_reason:read-live-{kind.value}")
                buckets[kind.value] = ()
        acquisition_records = buckets[LiveSourceIngressRecordKind.SOURCE_ACQUISITION]
        snapshot_records = buckets[LiveSourceIngressRecordKind.SOURCE_SNAPSHOT]
        acquisitions = {record.record_key: record for record in acquisition_records}
        snapshots = {record.record_key: record for record in snapshot_records}
        if len(acquisitions) != len(acquisition_records) or len(snapshots) != len(snapshot_records):
            degraded.add("degraded_reason:duplicate-live-source-record")
        chains: dict[
            str,
            list[
                tuple[
                    SourceAcquisitionReceiptV1Alpha1,
                    CanonicalSourceSnapshotV1Alpha1,
                    LiveSourceAdmissionReceiptV1Alpha1,
                ]
            ],
        ] = defaultdict(list)
        used_acquisition_refs: set[str] = set()
        used_snapshot_refs: set[str] = set()
        for admission_record in buckets[LiveSourceIngressRecordKind.SOURCE_ADMISSION]:
            try:
                admission = LiveSourceAdmissionReceiptV1Alpha1.model_validate(admission_record.payload)
                acquisition_record = acquisitions[str(admission.acquisition_receipt_ref)]
                snapshot_record = snapshots[str(admission.source_snapshot_ref)]
                chain = _decode_live_source_chain(
                    acquisition_record=acquisition_record,
                    snapshot_record=snapshot_record,
                    admission_record=admission_record,
                )
                chains[chain[0].source_definition_ref].append(chain)
                used_acquisition_refs.add(str(chain[0].receipt_id))
                used_snapshot_refs.add(str(chain[1].source_snapshot_ref))
            except Exception:
                degraded.add("degraded_reason:invalid-live-source-chain")
        if set(acquisitions) - used_acquisition_refs or set(snapshots) - used_snapshot_refs:
            degraded.add("degraded_reason:orphan-live-source-record")
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        for source_definition_ref, source_chains in chains.items():
            ordered = sorted(
                source_chains,
                key=lambda chain: (chain[2].admitted_at, str(chain[2].receipt_digest)),
            )
            prior_connection: IntelligenceResourceReferenceV1Alpha1 | None = None
            prior_source: IntelligenceResourceReferenceV1Alpha1 | None = None
            for revision, (acquisition, snapshot, admission) in enumerate(ordered, start=1):
                connection, source = _live_source_records(
                    acquisition=acquisition,
                    snapshot=snapshot,
                    admission=admission,
                    revision=revision,
                    prior_connection=prior_connection,
                    prior_source=prior_source,
                )
                prior_connection = connection.reference
                prior_source = source.reference
                for item in (connection, source):
                    if item.reference.resource_kind not in relevant or item.reference.as_of > query.as_of:
                        continue
                    if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                        continue
                    projected.append(item)
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


class CompositeIntelligenceResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Merge disjoint rebuildable projection contributors into one stable page."""

    def __init__(self, *contributors: IntelligenceResourceProjectionContributor) -> None:
        if not contributors:
            raise ValueError("at least one resource projection contributor is required")
        supported: set[IntelligenceResourceKind] = set()
        for contributor in contributors:
            overlap = supported & set(contributor.supported_kinds)
            if overlap:
                raise ValueError(f"resource projection contributors overlap: {sorted(item.value for item in overlap)}")
            supported.update(contributor.supported_kinds)
        self.contributors = contributors
        self.supported_kinds = frozenset(supported)

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        records: list[IntelligenceResourceRecordV1Alpha1] = []
        degraded = {
            f"degraded_reason:unsupported-{kind.value}" for kind in set(query.resource_kinds) - self.supported_kinds
        }
        for contributor in self.contributors:
            if not (set(query.resource_kinds) & contributor.supported_kinds):
                continue
            batch = await contributor.read(query=query, after=after, limit=limit)
            records.extend(batch.records)
            degraded.update(batch.degraded_reason_refs)
        visible = _after_cursor(records, after)[:limit]
        keys = [
            (
                item.reference.resource_kind,
                item.reference.resource_id,
                item.reference.revision,
            )
            for item in visible
        ]
        if len(keys) != len(set(keys)):
            raise IntelligenceLedgerProjectionError("resource projection contributors returned duplicate revisions")
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = [
    "CompositeIntelligenceResourceProjectionReader",
    "DecisionOutcomeFeedbackResourceProjectionReader",
    "IntelligenceLedgerProjectionError",
    "IntelligenceLedgerResourceProjectionReader",
    "IntelligenceResourceProjectionContributor",
    "LiveSourceResourceProjectionReader",
    "MonitoringResourceProjectionReader",
]
