"""Pure Overlay compilation and Domain Activation preparation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ace.intelligence.contracts.activation import (
    ActivationState,
    AuthorityBindingV1,
    CapabilityBindingV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
    DomainActivationRevisionV1,
    DomainActivationSpecV1,
    OrganizationOverlayV1,
    OverlayValueV1,
    overlay_value_matches_kind,
)
from ace.intelligence.contracts.pack import CompiledDomainPackV1


def _validate_overlay_values(pack: CompiledDomainPackV1, values: tuple[OverlayValueV1, ...]) -> None:
    slots = {item.slot_id: item for item in pack.overlay_slots}
    value_by_slot = {item.slot_id: item for item in values}
    if len(value_by_slot) != len(values):
        raise ValueError("overlay values must use unique slot IDs")
    undeclared = set(value_by_slot) - set(slots)
    if undeclared:
        raise ValueError(f"overlay contains undeclared slots: {sorted(undeclared)}")
    missing = {slot_id for slot_id, slot in slots.items() if slot.required and slot_id not in value_by_slot}
    if missing:
        raise ValueError(f"overlay is missing required slots: {sorted(missing)}")
    for slot_id, value in value_by_slot.items():
        slot = slots[slot_id]
        parsed = value.parsed_value()
        if not overlay_value_matches_kind(parsed, slot.value_kind.value):
            raise ValueError(f"overlay slot {slot_id} does not match {slot.value_kind.value}")
        if slot.allowed_values_json and value.value_json not in slot.allowed_values_json:
            raise ValueError(f"overlay slot {slot_id} is outside its declared allowed values")
        if slot.minimum is not None and parsed < slot.minimum:
            raise ValueError(f"overlay slot {slot_id} is below its declared minimum")
        if slot.maximum is not None and parsed > slot.maximum:
            raise ValueError(f"overlay slot {slot_id} is above its declared maximum")
        if slot.min_items is not None and len(parsed) < slot.min_items:
            raise ValueError(f"overlay slot {slot_id} has fewer than its declared minimum items")
        if slot.max_items is not None and len(parsed) > slot.max_items:
            raise ValueError(f"overlay slot {slot_id} has more than its declared maximum items")


def compile_overlay(pack: CompiledDomainPackV1, overlay: OrganizationOverlayV1) -> CompiledOverlayV1:
    """Validate organization values against exact Pack IR without mutating state."""

    if overlay.pack_id != pack.metadata.pack_id or overlay.pack_version != pack.metadata.version:
        raise ValueError("overlay targets a different pack identity or version")
    if overlay.pack_digest != pack.pack_digest:
        raise ValueError("overlay targets a different compiled pack digest")

    _validate_overlay_values(pack, overlay.values)

    return CompiledOverlayV1(
        overlay_id=overlay.overlay_id,
        version=overlay.version,
        pack_id=overlay.pack_id,
        pack_version=overlay.pack_version,
        pack_digest=overlay.pack_digest,
        values=overlay.values,
    )


def prepare_domain_activation(
    *,
    product_id: str,
    activation_key: str,
    pack: CompiledDomainPackV1,
    overlay: CompiledOverlayV1,
    compilation_receipt_ref: str,
    conformance_receipt_refs: Iterable[str],
    capability_bindings: Iterable[CapabilityBindingV1] = (),
    authority_bindings: Iterable[AuthorityBindingV1] = (),
) -> DomainActivationSpecV1:
    """Prepare an exact activation specification; persistence and approval remain Core services."""

    if overlay.pack_id != pack.metadata.pack_id or overlay.pack_version != pack.metadata.version:
        raise ValueError("compiled overlay targets a different pack identity or version")
    if overlay.pack_digest != pack.pack_digest:
        raise ValueError("compiled overlay targets a different pack digest")
    _validate_overlay_values(pack, overlay.values)

    capability_items = tuple(capability_bindings)
    capability_map = {item.requirement_id: item for item in capability_items}
    if len(capability_map) != len(capability_items):
        raise ValueError("capability bindings must use unique requirement IDs")
    required_capabilities = {item.requirement_id: item for item in pack.capability_requirements}
    if set(capability_map) != set(required_capabilities):
        missing = sorted(set(required_capabilities) - set(capability_map))
        undeclared = sorted(set(capability_map) - set(required_capabilities))
        raise ValueError(f"capability binding mismatch: missing={missing}; undeclared={undeclared}")
    for requirement_id, binding in capability_map.items():
        requirement = required_capabilities[requirement_id]
        if binding.capability != requirement.capability or binding.contract != requirement.contract:
            raise ValueError(f"capability binding {requirement_id} does not satisfy the declared contract")

    authority_items = tuple(authority_bindings)
    authority_map = {item.request_id: item for item in authority_items}
    if len(authority_map) != len(authority_items):
        raise ValueError("authority bindings must use unique request IDs")
    required_authorities = {item.request_id: item for item in pack.authority_requests}
    if set(authority_map) != set(required_authorities):
        missing = sorted(set(required_authorities) - set(authority_map))
        undeclared = sorted(set(authority_map) - set(required_authorities))
        raise ValueError(f"authority binding mismatch: missing={missing}; undeclared={undeclared}")
    for request_id, binding in authority_map.items():
        if binding.authority != required_authorities[request_id].authority:
            raise ValueError(f"authority binding {request_id} does not satisfy the declared request")

    return DomainActivationSpecV1(
        product_id=product_id,
        activation_key=activation_key,
        pack=CompiledPackRefV1(
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            compiled_pack_id=pack.compiled_pack_id,
            pack_digest=pack.pack_digest,
        ),
        overlay=overlay,
        compilation_receipt_ref=compilation_receipt_ref,
        capability_bindings=capability_items,
        authority_bindings=authority_items,
        conformance_receipt_refs=tuple(conformance_receipt_refs),
    )


def prepare_activation_revision(
    *,
    spec: DomainActivationSpecV1,
    state: ActivationState,
    actor_ref: str,
    approval_receipt_ref: str,
    occurred_at: datetime,
    prior_revision: DomainActivationRevisionV1 | None = None,
    rollback_of: DomainActivationRevisionV1 | None = None,
) -> DomainActivationRevisionV1:
    """Create a locally valid append-only transition; Core later owns atomic persistence."""

    if prior_revision is None and rollback_of is not None:
        raise ValueError("rollback requires a prior activation revision")
    if prior_revision is not None:
        same_scope = (
            prior_revision.spec.product_id == spec.product_id
            and prior_revision.spec.activation_key == spec.activation_key
        )
        if not same_scope:
            raise ValueError("the next activation revision must remain in the same product and activation scope")
    if rollback_of is not None:
        if rollback_of.activation_id != prior_revision.activation_id:
            raise ValueError("rollback target must belong to the same logical activation")
        if rollback_of.state is not ActivationState.ACTIVE:
            raise ValueError("rollback target must be an earlier active revision")
        if rollback_of.spec.spec_id != spec.spec_id:
            raise ValueError("rollback must restore the exact target activation specification")
        if state is not ActivationState.ACTIVE:
            raise ValueError("rollback creates a new active revision")

    return DomainActivationRevisionV1(
        revision=1 if prior_revision is None else prior_revision.revision + 1,
        spec=spec,
        state=state,
        prior_revision_id=None if prior_revision is None else prior_revision.revision_id,
        rollback_of_revision_id=None if rollback_of is None else rollback_of.revision_id,
        actor_ref=actor_ref,
        approval_receipt_ref=approval_receipt_ref,
        occurred_at=occurred_at,
    )
