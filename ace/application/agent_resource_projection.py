"""Rebuildable public Agent projections over governed onboarding audit records."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel

from ace.application.agent_governance import AGENT_GOVERNANCE_RECORD_SPACE
from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.records import ImmutableRecordStore, ImmutableRecordV1
from ace.intelligence.contracts.agent_governance import (
    AGENT_BINDING_LIFECYCLE_REVISION_VERSION,
    AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION,
    AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION,
    AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION,
    AGENT_RUNTIME_HEALTH_REVISION_VERSION,
    AgentActivationReceiptV1Alpha1,
    AgentBindingLifecycleRevisionV1Alpha1,
    AgentDefinitionLifecycleRevisionV1Alpha1,
    AgentGrantRequestLifecycleRevisionV1Alpha1,
    AgentPrincipalLifecycleRevisionV1Alpha1,
    AgentRuntimeHealthRevisionV1Alpha1,
    GovernedContentState,
    GrantRequestState,
    PrincipalLifecycleState,
    RuntimeHealthState,
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

AGENT_RESOURCE_PROJECTION_VERSION = "ace.intelligence.agent-resource-projection/v1alpha1"
AGENT_RESOURCE_KINDS = frozenset({IntelligenceResourceKind.AGENT})

LifecycleRevision: TypeAlias = (
    AgentPrincipalLifecycleRevisionV1Alpha1
    | AgentDefinitionLifecycleRevisionV1Alpha1
    | AgentBindingLifecycleRevisionV1Alpha1
    | AgentGrantRequestLifecycleRevisionV1Alpha1
    | AgentRuntimeHealthRevisionV1Alpha1
)

_LIFECYCLE_MODELS: dict[str, type[BaseModel]] = {
    AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION: AgentPrincipalLifecycleRevisionV1Alpha1,
    AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION: AgentDefinitionLifecycleRevisionV1Alpha1,
    AGENT_BINDING_LIFECYCLE_REVISION_VERSION: AgentBindingLifecycleRevisionV1Alpha1,
    AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION: AgentGrantRequestLifecycleRevisionV1Alpha1,
    AGENT_RUNTIME_HEALTH_REVISION_VERSION: AgentRuntimeHealthRevisionV1Alpha1,
}


def _revision_id(value: LifecycleRevision) -> str:
    return str(
        value.health_revision_id
        if isinstance(value, AgentRuntimeHealthRevisionV1Alpha1)
        else value.lifecycle_revision_id
    )


def _revision_digest(value: LifecycleRevision) -> str:
    return str(
        value.health_revision_digest
        if isinstance(value, AgentRuntimeHealthRevisionV1Alpha1)
        else value.lifecycle_revision_digest
    )


def _occurred_at(value: LifecycleRevision) -> datetime:
    return value.observed_at if isinstance(value, AgentRuntimeHealthRevisionV1Alpha1) else value.occurred_at


def _component_key(value: LifecycleRevision) -> str:
    if isinstance(value, AgentPrincipalLifecycleRevisionV1Alpha1):
        return "principal"
    if isinstance(value, AgentDefinitionLifecycleRevisionV1Alpha1):
        return "definition"
    if isinstance(value, AgentBindingLifecycleRevisionV1Alpha1):
        return f"binding:{value.binding_key}"
    if isinstance(value, AgentGrantRequestLifecycleRevisionV1Alpha1):
        return "grants"
    return "health"


def _decode_lifecycle_record(record: ImmutableRecordV1) -> LifecycleRevision:
    model = _LIFECYCLE_MODELS.get(record.payload_contract)
    if model is None:
        raise ValueError("unsupported agent lifecycle contract")
    value = model.model_validate(record.payload)
    if not isinstance(
        value,
        (
            AgentPrincipalLifecycleRevisionV1Alpha1,
            AgentDefinitionLifecycleRevisionV1Alpha1,
            AgentBindingLifecycleRevisionV1Alpha1,
            AgentGrantRequestLifecycleRevisionV1Alpha1,
            AgentRuntimeHealthRevisionV1Alpha1,
        ),
    ):
        raise ValueError("unsupported agent lifecycle value")
    if (
        record.product_id != value.governance.product_id
        or record.record_space != AGENT_GOVERNANCE_RECORD_SPACE
        or record.record_kind != "lifecycle_revision"
        or record.record_key != _revision_id(value)
        or record.payload_contract != value.contract
        or record.payload != value.model_dump(mode="python")
        or record.as_of != record.available_at
        or record.as_of < _occurred_at(value)
    ):
        raise ValueError("agent lifecycle envelope mismatch")
    return value


def _decode_activation_record(record: ImmutableRecordV1) -> AgentActivationReceiptV1Alpha1:
    value = AgentActivationReceiptV1Alpha1.model_validate(record.payload)
    if (
        record.product_id != value.governance.product_id
        or record.record_space != AGENT_GOVERNANCE_RECORD_SPACE
        or record.record_kind != "activation_receipt"
        or record.record_key != value.receipt_id
        or record.payload_contract != value.contract
        or record.payload != value.model_dump(mode="python")
        or record.as_of != value.activated_at
        or record.available_at != value.activated_at
    ):
        raise ValueError("agent activation envelope mismatch")
    return value


def _chain_is_exact(values: list[LifecycleRevision]) -> bool:
    ordered = sorted(values, key=lambda item: item.sequence)
    return [item.sequence for item in ordered] == list(range(1, len(ordered) + 1)) and all(
        current.prior_revision_id == _revision_id(previous) and _occurred_at(current) > _occurred_at(previous)
        for previous, current in zip(ordered, ordered[1:])
    )


def _activation_matches_heads(
    activation: AgentActivationReceiptV1Alpha1,
    heads: dict[str, LifecycleRevision],
) -> bool:
    binding = next(
        (
            value
            for key, value in heads.items()
            if key.startswith("binding:") and _revision_id(value) == activation.binding_lifecycle_revision_id
        ),
        None,
    )
    return (
        (
            _revision_id(heads["principal"]) == activation.principal_lifecycle_revision_id
            and _revision_id(heads["definition"]) == activation.definition_lifecycle_revision_id
            and _revision_id(heads["grants"]) == activation.grant_request_lifecycle_revision_id
            and _revision_id(heads["health"]) == activation.runtime_health_revision_id
            and binding is not None
        )
        if {"principal", "definition", "grants", "health"}.issubset(heads)
        else False
    )


def _agent_state(
    activation: AgentActivationReceiptV1Alpha1,
    heads: dict[str, LifecycleRevision],
) -> tuple[IntelligenceResourceAvailability, tuple[str, ...], dict[str, object]]:
    principal = heads.get("principal")
    definition = heads.get("definition")
    grants = heads.get("grants")
    health = heads.get("health")
    binding = next(
        (
            value
            for value in heads.values()
            if isinstance(value, AgentBindingLifecycleRevisionV1Alpha1)
            and _revision_id(value) == activation.binding_lifecycle_revision_id
        ),
        None,
    )
    exact = (
        isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
        and isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
        and isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1)
        and isinstance(grants, AgentGrantRequestLifecycleRevisionV1Alpha1)
        and isinstance(health, AgentRuntimeHealthRevisionV1Alpha1)
    )
    reasons: set[str] = set()
    if not exact or not _activation_matches_heads(activation, heads):
        reasons.add("degraded_reason:agent-activation-stale")
    if (
        isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
        and principal.state is not PrincipalLifecycleState.ACTIVE
    ):
        reasons.add(f"degraded_reason:agent-principal-{principal.state.value}")
    if (
        isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
        and definition.state is not GovernedContentState.ACTIVE
    ):
        reasons.add(f"degraded_reason:agent-definition-{definition.state.value}")
    if isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1) and binding.state is not GovernedContentState.ACTIVE:
        reasons.add(f"degraded_reason:agent-binding-{binding.state.value}")
    if (
        isinstance(grants, AgentGrantRequestLifecycleRevisionV1Alpha1)
        and grants.state is not GrantRequestState.REQUESTED
    ):
        reasons.add(f"degraded_reason:agent-grants-{grants.state.value}")
    if isinstance(health, AgentRuntimeHealthRevisionV1Alpha1) and health.state is not RuntimeHealthState.HEALTHY:
        reasons.add(f"degraded_reason:agent-health-{health.state.value}")

    tombstoned = isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1) and principal.state in {
        PrincipalLifecycleState.REVOKED,
        PrincipalLifecycleState.RETIRED,
    }
    availability = (
        IntelligenceResourceAvailability.TOMBSTONED
        if tombstoned
        else IntelligenceResourceAvailability.DEGRADED
        if reasons
        else IntelligenceResourceAvailability.AVAILABLE
    )
    payload: dict[str, object] = {
        "governance_id": str(activation.governance.governance_id),
        "principal_key": activation.governance.principal_key,
        "activation_receipt_id": str(activation.receipt_id),
        "activation_receipt_digest": str(activation.receipt_digest),
        "activated_at": activation.activated_at.isoformat(),
        "activation_eligibility_only": True,
        "reusable_authority": False,
        "current_lifecycle": {
            key: {
                "revision_id": _revision_id(value),
                "revision_digest": _revision_digest(value),
                "state": value.state.value,
            }
            for key, value in sorted(heads.items())
        },
    }
    if isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1):
        payload["registration"] = {
            "artifact_id": principal.registration_snapshot.artifact_id,
            "implementation_ref": principal.registration_implementation_ref,
            "protocol_refs": principal.registration_protocol_refs,
        }
    if isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1):
        payload["definition"] = {
            "purpose": definition.definition.purpose,
            "eligible_stages": tuple(item.value for item in definition.definition.eligible_stages),
            "implementation_protocol_ref": definition.definition.implementation_protocol_ref,
        }
    if isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1):
        payload["binding"] = {
            "binding_key": binding.binding_key,
            "stage": binding.binding.stage.value,
            "role_label": binding.binding.role_label,
        }
    return availability, tuple(sorted(reasons)), payload


def _reference(
    *,
    product_id: str,
    governance_id: str,
    revision: int,
    as_of: datetime,
    payload: dict[str, object],
    availability: IntelligenceResourceAvailability,
) -> IntelligenceResourceReferenceV1Alpha1:
    material = {
        "availability": availability.value,
        "payload": payload,
        "revision": revision,
    }
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=IntelligenceResourceKind.AGENT,
        resource_id=governance_id,
        resource_digest=f"sha256:{canonical_hash(material)}",
        resource_contract=AGENT_RESOURCE_PROJECTION_VERSION,
        revision=revision,
        as_of=as_of,
        available_at=as_of,
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


class AgentResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project current governed, activated Agent state without carrying authority forward."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return AGENT_RESOURCE_KINDS

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
            for kind in requested - AGENT_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if IntelligenceResourceKind.AGENT not in requested:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            lifecycle_records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                record_kind="lifecycle_revision",
                available_at=query.available_at,
            )
            activation_records = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                record_kind="activation_receipt",
                available_at=query.available_at,
            )
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:read-agent-governance",),
            )

        lifecycle_by_governance: dict[str, list[tuple[ImmutableRecordV1, LifecycleRevision]]] = defaultdict(list)
        activation_by_governance: dict[str, list[tuple[ImmutableRecordV1, AgentActivationReceiptV1Alpha1]]] = (
            defaultdict(list)
        )
        for record in lifecycle_records:
            try:
                value = _decode_lifecycle_record(record)
                lifecycle_by_governance[str(value.governance.governance_id)].append((record, value))
            except Exception:
                degraded.add("degraded_reason:invalid-agent-lifecycle")
        for record in activation_records:
            try:
                value = _decode_activation_record(record)
                activation_by_governance[str(value.governance.governance_id)].append((record, value))
            except Exception:
                degraded.add("degraded_reason:invalid-agent-activation")

        current_records: list[IntelligenceResourceRecordV1Alpha1] = []
        for governance_id, activations in activation_by_governance.items():
            lifecycle = lifecycle_by_governance.get(governance_id, [])
            chains: dict[str, list[LifecycleRevision]] = defaultdict(list)
            for _, value in lifecycle:
                chains[_component_key(value)].append(value)
            if not chains or any(not _chain_is_exact(chain) for chain in chains.values()):
                degraded.add(f"degraded_reason:invalid-agent-chain:{governance_id}")
                continue

            events: list[tuple[datetime, int, str, ImmutableRecordV1, BaseModel]] = [
                (record.available_at, record.processing_order, record.record_key, record, value)
                for record, value in lifecycle
                if record.as_of <= query.as_of
            ] + [
                (record.available_at, record.processing_order, record.record_key, record, value)
                for record, value in activations
                if record.as_of <= query.as_of
            ]
            heads: dict[str, LifecycleRevision] = {}
            active_activation: AgentActivationReceiptV1Alpha1 | None = None
            previous_reference: IntelligenceResourceReferenceV1Alpha1 | None = None
            public_revision = 0
            current: IntelligenceResourceRecordV1Alpha1 | None = None
            for event_time, _, _, _, value in sorted(events, key=lambda item: item[:3]):
                if isinstance(value, AgentActivationReceiptV1Alpha1):
                    if not _activation_matches_heads(value, heads):
                        degraded.add(f"degraded_reason:invalid-agent-activation-chain:{governance_id}")
                        continue
                    active_activation = value
                else:
                    heads[_component_key(value)] = value
                if active_activation is None:
                    continue
                public_revision += 1
                availability, reasons, payload = _agent_state(active_activation, heads)
                reference = _reference(
                    product_id=query.product_id,
                    governance_id=governance_id,
                    revision=public_revision,
                    as_of=event_time,
                    payload=payload,
                    availability=availability,
                )
                current = IntelligenceResourceRecordV1Alpha1(
                    reference=reference,
                    availability=availability,
                    title=f"Agent: {active_activation.governance.principal_key}",
                    summary=(
                        "Governed agent is currently eligible."
                        if availability is IntelligenceResourceAvailability.AVAILABLE
                        else "Governed agent requires lifecycle review."
                    ),
                    subject_refs=(
                        governance_id,
                        active_activation.governance.principal_key,
                    ),
                    supersedes=previous_reference,
                    payload=(
                        None
                        if availability is IntelligenceResourceAvailability.TOMBSTONED
                        else CanonicalJsonValueV1Alpha1(value_json=canonical_json(payload))
                    ),
                    degraded_reason_refs=(reasons if availability is IntelligenceResourceAvailability.DEGRADED else ()),
                )
                previous_reference = reference
            if current is None:
                continue
            degraded.update(current.degraded_reason_refs)
            if query.subject_refs and set(query.subject_refs).isdisjoint(current.subject_refs):
                continue
            current_records.append(current)

        visible = _after_cursor(current_records, after)[:limit]
        reasons = tuple(sorted(degraded))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = [
    "AGENT_RESOURCE_KINDS",
    "AGENT_RESOURCE_PROJECTION_VERSION",
    "AgentResourceProjectionReader",
]
