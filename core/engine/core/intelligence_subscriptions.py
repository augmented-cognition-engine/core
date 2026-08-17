"""Authenticated host boundary for record-only Intelligence subscriptions.

This module exposes the existing append-only monitoring lifecycle without
claiming a scheduler, outbound destination, stream, webhook, or delivery
receipt.  Immediate and digest preferences remain contract material only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ace.application.monitoring import (
    ExactMaterialReferenceV1Alpha1,
    MonitoringLifecycleAction,
    MonitoringLifecycleAdmission,
    MonitoringLifecycleError,
    MonitoringLifecycleReceiptV1Alpha1,
    MonitoringLifecycleReplayConflict,
    MonitoringLifecycleRequestV1Alpha1,
    MonitoringLifecycleService,
    MonitoringTargetKind,
    PersonaBindingV1Alpha1,
    SubscriptionV1Alpha1,
)
from ace.core import AppendOnlyTransactionReceiptV1, ImmutableRecordStore
from core.engine.core.agent_composition_runtime import persist_task_authentication_receipt
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore

INTELLIGENCE_SUBSCRIPTION_RESULT_VERSION = "ace.http.intelligence-subscription-lifecycle-result/v1alpha1"
INTELLIGENCE_SUBSCRIPTION_AUTHORITY = "administer_lifecycle"


class IntelligenceSubscriptionLifecycleHttpRequestV1(BaseModel):
    """Owner material; authenticated identity and application time are host-owned."""

    model_config = ConfigDict(extra="forbid")

    transition_key: str = Field(min_length=1, max_length=240)
    persona_binding: PersonaBindingV1Alpha1
    subscription: SubscriptionV1Alpha1
    action: MonitoringLifecycleAction
    sequence: int = Field(ge=1)
    prior_receipt: ExactMaterialReferenceV1Alpha1 | None = None


class IntelligenceSubscriptionLifecycleResultV1Alpha1(BaseModel):
    """Durable lifecycle result with literal non-delivery capability flags."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.intelligence-subscription-lifecycle-result/v1alpha1"] = (
        INTELLIGENCE_SUBSCRIPTION_RESULT_VERSION
    )
    lifecycle: MonitoringLifecycleReceiptV1Alpha1
    transaction: AppendOnlyTransactionReceiptV1
    replayed: bool
    record_only: Literal[True] = True
    scheduler_started: Literal[False] = False
    outbound_delivery_configured: Literal[False] = False
    delivery_receipt_created: Literal[False] = False
    destination_authority_used: Literal[False] = False


@dataclass(frozen=True, slots=True)
class IntelligenceSubscriptionHttpRuntime:
    records: ImmutableRecordStore


class IntelligenceSubscriptionHttpError(RuntimeError):
    pass


class IntelligenceSubscriptionHttpUnauthenticated(IntelligenceSubscriptionHttpError):
    pass


class IntelligenceSubscriptionHttpDenied(IntelligenceSubscriptionHttpError):
    pass


class IntelligenceSubscriptionHttpConflict(IntelligenceSubscriptionHttpError):
    pass


class IntelligenceSubscriptionHttpUnavailable(IntelligenceSubscriptionHttpError):
    pass


def intelligence_subscription_runtime() -> IntelligenceSubscriptionHttpRuntime:
    return IntelligenceSubscriptionHttpRuntime(records=SurrealImmutableRecordStore(pool))


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceSubscriptionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or INTELLIGENCE_SUBSCRIPTION_AUTHORITY not in authorities:
        raise IntelligenceSubscriptionHttpDenied("Intelligence lifecycle authority is required")
    return actor_ref, product_id


def _target_reference(subscription: SubscriptionV1Alpha1) -> ExactMaterialReferenceV1Alpha1:
    return ExactMaterialReferenceV1Alpha1(
        reference=str(subscription.subscription_ref),
        digest=str(subscription.subscription_digest),
    )


def _binding_reference(binding: PersonaBindingV1Alpha1) -> ExactMaterialReferenceV1Alpha1:
    return ExactMaterialReferenceV1Alpha1(
        reference=str(binding.binding_ref),
        digest=str(binding.binding_digest),
    )


def _same_transition(
    admission: MonitoringLifecycleAdmission,
    *,
    product_id: str,
    actor_ref: str,
    selector: IntelligenceSubscriptionLifecycleHttpRequestV1,
) -> bool:
    receipt = admission.receipt
    return (
        receipt.product_id == product_id
        and receipt.owner_ref == actor_ref
        and receipt.target_kind is MonitoringTargetKind.SUBSCRIPTION
        and receipt.target == _target_reference(selector.subscription)
        and receipt.persona_binding == _binding_reference(selector.persona_binding)
        and receipt.action is selector.action
        and receipt.sequence == selector.sequence
        and receipt.prior_receipt == selector.prior_receipt
    )


def _result(admission: MonitoringLifecycleAdmission, *, replayed: bool | None = None):
    return IntelligenceSubscriptionLifecycleResultV1Alpha1(
        lifecycle=admission.receipt,
        transaction=admission.transaction_receipt,
        replayed=admission.replayed if replayed is None else replayed,
    )


async def transition_record_only_subscription(
    *,
    selector: IntelligenceSubscriptionLifecycleHttpRequestV1,
    user: dict,
    runtime: IntelligenceSubscriptionHttpRuntime,
) -> IntelligenceSubscriptionLifecycleResultV1Alpha1:
    """Append or replay one owner lifecycle transition; never deliver externally."""

    actor_ref, product_id = _verified_claims(user)
    try:
        binding = PersonaBindingV1Alpha1.model_validate(selector.persona_binding.model_dump(mode="python"))
        subscription = SubscriptionV1Alpha1.model_validate(selector.subscription.model_dump(mode="python"))
    except (TypeError, ValueError) as exc:
        raise IntelligenceSubscriptionHttpConflict("subscription material failed exact validation") from exc
    if subscription.delivery.value != "record_only":
        raise IntelligenceSubscriptionHttpConflict(
            "immediate and digest delivery remain unavailable until a destination runtime exists"
        )
    if binding.product_id != product_id or subscription.product_id != product_id:
        raise IntelligenceSubscriptionHttpDenied("subscription crossed verified product scope")
    if binding.principal_ref != actor_ref:
        raise IntelligenceSubscriptionHttpDenied("subscription is not owned by the verified principal")

    service = MonitoringLifecycleService(store=runtime.records)
    try:
        existing = await service.lookup_transition(
            product_id=product_id,
            transition_key=selector.transition_key,
        )
        if existing is not None:
            if not _same_transition(
                existing,
                product_id=product_id,
                actor_ref=actor_ref,
                selector=selector,
            ):
                raise IntelligenceSubscriptionHttpConflict(
                    "transition_key already binds different subscription lifecycle material"
                )
            return _result(existing, replayed=True)

        now = datetime.now(UTC)
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = MonitoringLifecycleRequestV1Alpha1(
            transition_key=selector.transition_key,
            product_id=product_id,
            authenticated_context=authentication.runtime_context(),
            target_kind=MonitoringTargetKind.SUBSCRIPTION,
            target=_target_reference(subscription),
            persona_binding=_binding_reference(binding),
            action=selector.action,
            sequence=selector.sequence,
            prior_receipt=selector.prior_receipt,
            requested_at=now,
        )
        admission = await service.transition(
            request=request,
            persona_binding=binding,
            target=subscription,
            applied_at=now,
        )
        return _result(admission)
    except MonitoringLifecycleReplayConflict:
        # A concurrent equivalent call may win after the preflight lookup.
        try:
            existing = await service.lookup_transition(
                product_id=product_id,
                transition_key=selector.transition_key,
            )
        except MonitoringLifecycleError as exc:
            raise IntelligenceSubscriptionHttpUnavailable("subscription lifecycle replay is unavailable") from exc
        if existing is not None and _same_transition(
            existing,
            product_id=product_id,
            actor_ref=actor_ref,
            selector=selector,
        ):
            return _result(existing, replayed=True)
        raise IntelligenceSubscriptionHttpConflict(
            "transition_key already binds different subscription lifecycle material"
        ) from None
    except MonitoringLifecycleError as exc:
        message = str(exc)
        if "load failed" in message or "unavailable" in message or "append failed" in message:
            raise IntelligenceSubscriptionHttpUnavailable("subscription lifecycle storage is unavailable") from exc
        raise IntelligenceSubscriptionHttpConflict(message) from exc
    except IntelligenceSubscriptionHttpConflict:
        raise
    except Exception as exc:
        raise IntelligenceSubscriptionHttpUnavailable("subscription lifecycle storage is unavailable") from exc


__all__ = [
    "INTELLIGENCE_SUBSCRIPTION_AUTHORITY",
    "IntelligenceSubscriptionHttpConflict",
    "IntelligenceSubscriptionHttpDenied",
    "IntelligenceSubscriptionHttpRuntime",
    "IntelligenceSubscriptionHttpUnauthenticated",
    "IntelligenceSubscriptionHttpUnavailable",
    "IntelligenceSubscriptionLifecycleHttpRequestV1",
    "IntelligenceSubscriptionLifecycleResultV1Alpha1",
    "intelligence_subscription_runtime",
    "transition_record_only_subscription",
]
