from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from ace.intelligence.contracts import (
    CompiledPackRefV1,
    MonitorDisposition,
    MonitorV1Alpha1,
    PersonaArchetypeV1,
    PersonaBindingV1Alpha1,
    SubscriptionDeliveryDisposition,
    SubscriptionV1Alpha1,
)

pytestmark = pytest.mark.unit

PACK_DIGEST = "sha256:" + "d" * 64
PACK = CompiledPackRefV1(
    pack_id="generic_intelligence",
    pack_version="0.4.0-alpha.1",
    compiled_pack_id="pack_ir:" + "d" * 32,
    pack_digest=PACK_DIGEST,
)


def _monitor(**updates) -> MonitorV1Alpha1:
    payload = {
        "monitor_id": "material_change",
        "product_id": "product:generic-intelligence",
        "subject_entity_type_ids": ("subject",),
        "subject_refs": ("entity:subject:one",),
        "detection_rule_ids": ("numeric_change",),
        "compiled_pack": PACK,
        "activation_revision_ref": "activation_revision:one",
        "disposition": MonitorDisposition.ENABLED,
    }
    payload.update(updates)
    return MonitorV1Alpha1(**payload)


def _binding(**updates) -> PersonaBindingV1Alpha1:
    payload = {
        "product_id": "product:generic-intelligence",
        "principal_ref": "principal:analyst",
        "persona_id": "domain_analyst",
        "compiled_pack": PACK,
        "activation_revision_ref": "activation_revision:one",
    }
    payload.update(updates)
    return PersonaBindingV1Alpha1(**payload)


def _subscription(**updates) -> SubscriptionV1Alpha1:
    binding = _binding()
    payload = {
        "subscription_id": "priority_attention",
        "product_id": "product:generic-intelligence",
        "persona_binding_ref": binding.binding_ref,
        "monitor_refs": (_monitor().monitor_ref,),
        "signal_types": ("material_attention",),
        "brief_template_ids": ("orientation_brief",),
        "minimum_confidence": 0.7,
        "delivery": SubscriptionDeliveryDisposition.IMMEDIATE,
    }
    payload.update(updates)
    return SubscriptionV1Alpha1(**payload)


def test_monitor_identity_is_exact_and_collections_are_canonical() -> None:
    first = _monitor(
        subject_entity_type_ids=("subject_b", "subject_a"),
        detection_rule_ids=("rule_b", "rule_a"),
    )
    second = _monitor(
        subject_entity_type_ids=("subject_a", "subject_b"),
        detection_rule_ids=("rule_a", "rule_b"),
    )
    assert first == second
    assert first.monitor_ref.startswith("monitor:")
    assert first.monitor_digest.startswith("sha256:")
    with pytest.raises(ValidationError, match="exact material"):
        _monitor(monitor_ref="monitor:wrong")


def test_subscriber_identity_is_a_three_layer_join_not_a_pack_principal() -> None:
    persona = PersonaArchetypeV1(
        persona_id="domain_analyst",
        display_name="Domain Analyst",
        description="Reviews material changes.",
    )
    binding = _binding()
    subscription = _subscription(persona_binding_ref=binding.binding_ref)

    assert not hasattr(persona, "principal_ref")
    assert binding.principal_ref == "principal:analyst"
    assert binding.persona_id == persona.persona_id
    assert subscription.persona_binding_ref == binding.binding_ref


def test_binding_and_subscription_identities_change_with_material() -> None:
    assert _binding().binding_ref != _binding(principal_ref="principal:reviewer").binding_ref
    assert (
        _subscription().subscription_ref
        != _subscription(delivery=SubscriptionDeliveryDisposition.DIGEST).subscription_ref
    )


@pytest.mark.parametrize("value", [1, "0.7", True, math.nan, math.inf])
def test_subscription_confidence_fails_closed_without_coercion(value) -> None:
    with pytest.raises(ValidationError, match="finite float"):
        _subscription(minimum_confidence=value)


def test_subscription_requires_a_selector_and_monitor_requires_a_rule() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        _subscription(monitor_refs=(), signal_types=(), brief_template_ids=())
    with pytest.raises(ValidationError):
        _monitor(detection_rule_ids=())
