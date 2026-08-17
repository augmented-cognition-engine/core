from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.intelligence import (
    CompiledPackRefV1,
    MonitoringLifecycleAction,
    PersonaBindingV1Alpha1,
    SubscriptionDeliveryDisposition,
    SubscriptionV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_subscriptions import router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_subscriptions import (
    IntelligenceSubscriptionHttpRuntime,
    intelligence_subscription_runtime,
)

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
PRODUCT = "product:consumer-intelligence"
OWNER = "principal:consumer-owner"
PACK = CompiledPackRefV1(
    pack_id="world_intelligence",
    pack_version="1.0.0",
    compiled_pack_id="pack_ir:" + "a" * 32,
    pack_digest="sha256:" + "a" * 64,
)


def _claims(*, actor: str = OWNER, authorities: list[str] | None = None) -> dict:
    return {
        "sub": actor,
        "product": PRODUCT,
        "authorities": ["administer_lifecycle"] if authorities is None else authorities,
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _binding(*, actor: str = OWNER) -> PersonaBindingV1Alpha1:
    return PersonaBindingV1Alpha1(
        product_id=PRODUCT,
        principal_ref=actor,
        persona_id="domain_analyst",
        compiled_pack=PACK,
        activation_revision_ref="activation_revision:world-current",
    )


def _subscription(
    *,
    binding: PersonaBindingV1Alpha1 | None = None,
    delivery: SubscriptionDeliveryDisposition = SubscriptionDeliveryDisposition.RECORD_ONLY,
    signal_types: tuple[str, ...] = ("material_attention",),
) -> SubscriptionV1Alpha1:
    exact_binding = binding or _binding()
    return SubscriptionV1Alpha1(
        subscription_id="world_attention",
        product_id=PRODUCT,
        persona_binding_ref=str(exact_binding.binding_ref),
        signal_types=signal_types,
        minimum_confidence=0.7,
        delivery=delivery,
    )


def _body(
    *,
    key: str,
    action: MonitoringLifecycleAction = MonitoringLifecycleAction.CREATE,
    sequence: int = 1,
    prior: dict | None = None,
    binding: PersonaBindingV1Alpha1 | None = None,
    subscription: SubscriptionV1Alpha1 | None = None,
) -> dict:
    exact_binding = binding or _binding()
    exact_subscription = subscription or _subscription(binding=exact_binding)
    return {
        "transition_key": key,
        "persona_binding": exact_binding.model_dump(mode="json"),
        "subscription": exact_subscription.model_dump(mode="json"),
        "action": action.value,
        "sequence": sequence,
        "prior_receipt": prior,
    }


async def _request(*, store, claims: dict, body: dict):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_subscription_runtime] = lambda: IntelligenceSubscriptionHttpRuntime(
        records=store
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/intelligence/subscriptions/lifecycle", json=body)


@pytest.mark.asyncio
async def test_record_only_subscription_lifecycle_is_authenticated_durable_and_restart_replayable() -> None:
    store = InMemoryImmutableRecordStore()
    create_body = _body(key="subscription_transition:world-create")

    created = await _request(store=store, claims=_claims(), body=create_body)
    replayed = await _request(store=store, claims=_claims(), body=create_body)

    assert created.status_code == 200
    assert replayed.status_code == 200
    result = created.json()
    assert result["contract"] == "ace.http.intelligence-subscription-lifecycle-result/v1alpha1"
    assert result["lifecycle"]["state_after"] == "active"
    assert result["record_only"] is True
    assert result["scheduler_started"] is False
    assert result["outbound_delivery_configured"] is False
    assert result["delivery_receipt_created"] is False
    assert result["destination_authority_used"] is False
    assert result["transaction"]["records"]
    assert replayed.json()["lifecycle"] == result["lifecycle"]
    assert replayed.json()["transaction"] == result["transaction"]
    assert replayed.json()["replayed"] is True

    prior = {
        "reference": result["lifecycle"]["receipt_id"],
        "digest": result["lifecycle"]["receipt_digest"],
    }
    paused = await _request(
        store=store,
        claims=_claims(),
        body=_body(
            key="subscription_transition:world-pause",
            action=MonitoringLifecycleAction.PAUSE,
            sequence=2,
            prior=prior,
        ),
    )
    assert paused.status_code == 200
    assert paused.json()["lifecycle"]["state_after"] == "paused"
    assert paused.json()["lifecycle"]["prior_receipt"] == {
        "contract": "ace.intelligence.exact-material-reference/v1alpha1",
        **prior,
    }


@pytest.mark.asyncio
async def test_subscription_http_rejects_unimplemented_delivery_and_unowned_or_unauthorized_material() -> None:
    store = InMemoryImmutableRecordStore()
    binding = _binding()
    immediate = _subscription(binding=binding, delivery=SubscriptionDeliveryDisposition.IMMEDIATE)
    response = await _request(
        store=store,
        claims=_claims(),
        body=_body(
            key="subscription_transition:immediate",
            binding=binding,
            subscription=immediate,
        ),
    )
    assert response.status_code == 409
    assert "destination runtime" in response.json()["detail"]

    not_owner = await _request(
        store=store,
        claims=_claims(actor="principal:other"),
        body=_body(key="subscription_transition:not-owner"),
    )
    assert not_owner.status_code == 403

    no_authority = await _request(
        store=store,
        claims=_claims(authorities=[]),
        body=_body(key="subscription_transition:no-authority"),
    )
    assert no_authority.status_code == 403


@pytest.mark.asyncio
async def test_subscription_transition_key_cannot_be_reused_for_different_exact_material() -> None:
    store = InMemoryImmutableRecordStore()
    key = "subscription_transition:stable"
    first = await _request(store=store, claims=_claims(), body=_body(key=key))
    changed = _subscription(signal_types=("critical_attention",))
    conflict = await _request(
        store=store,
        claims=_claims(),
        body=_body(key=key, subscription=changed),
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert "different subscription lifecycle material" in conflict.json()["detail"]
