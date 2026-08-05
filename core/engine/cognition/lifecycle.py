"""Human-authorized cognition head lifecycle transitions and rollback."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from core.engine.cognition.contracts import (
    CognitionHeadV1,
    CognitionRevisionV1,
    FrozenContract,
    stable_id,
)
from core.engine.cognition.governance import ActorClass, ReviewActorV1
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    CognitionPersistenceError,
    CognitionScopeError,
    _head_content,
    _query_or_raise,
    _record_key,
)
from core.engine.core.db import parse_one, parse_record_id

COGNITION_LIFECYCLE_VERSION = "ace.cognition.lifecycle/v1"
COGNITION_LIFECYCLE_POLICY = "ace.cognition.lifecycle-policy/v1"


class LifecycleAction(StrEnum):
    ROLLBACK = "rollback"
    REACTIVATE = "reactivate"
    DISABLE = "disable"
    EXPIRE = "expire"
    RETIRE = "retire"


class CognitionLifecycleReceiptV1(FrozenContract):
    contract_version: str = COGNITION_LIFECYCLE_VERSION
    receipt_id: str | None = None
    review_request_id: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    head_id: str
    cognition_id: str
    actor: ReviewActorV1
    action: LifecycleAction
    rationale: str = Field(min_length=1, max_length=4_000)
    expected_generation: int = Field(ge=1)
    prior_revision_id: str
    target_revision_id: str
    result_generation: int = Field(ge=2)
    result_lifecycle: str = Field(pattern=r"^(active|disabled|expired|retired)$")
    expires_at: datetime | None = None
    policy_version: str = COGNITION_LIFECYCLE_POLICY

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("lifecycle expiry must include a timezone")
        return value

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = stable_id(
            "cognition_lifecycle",
            self.model_dump(mode="json", exclude={"receipt_id"}),
        )
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("lifecycle receipt identity does not match exact transition")
        object.__setattr__(self, "receipt_id", expected)
        return self


def build_lifecycle_transition(
    *,
    head: CognitionHeadV1,
    current_revision: CognitionRevisionV1,
    target_revision: CognitionRevisionV1 | None,
    product_id: str,
    review_request_id: str,
    actor: ReviewActorV1,
    action: LifecycleAction,
    rationale: str,
    expected_generation: int,
    expires_at: datetime | None = None,
) -> tuple[CognitionLifecycleReceiptV1, CognitionHeadV1]:
    if actor.actor_class is not ActorClass.HUMAN or "cognition-review" not in actor.authorities:
        raise PermissionError("human_authority_required")
    if head.scope.product_id != product_id:
        raise CognitionScopeError("head is unavailable in product scope")
    if head.generation != expected_generation:
        raise CognitionPersistenceError(
            f"cognition_head_generation_conflict:expected={expected_generation}:actual={head.generation}"
        )
    if current_revision.revision_id != head.active_revision_id:
        raise CognitionPersistenceError("active head revision is unavailable")

    target = target_revision or current_revision
    if action is LifecycleAction.ROLLBACK:
        if target_revision is None or target_revision.revision_id == current_revision.revision_id:
            raise CognitionPersistenceError("rollback requires a distinct prior revision")
    elif target_revision is not None and action is not LifecycleAction.REACTIVATE:
        raise CognitionPersistenceError("target revision is only valid for rollback/reactivate")
    if target.identity.cognition_id != head.cognition_id:
        raise CognitionPersistenceError("lifecycle target revision belongs to another cognition")

    lifecycle = {
        LifecycleAction.ROLLBACK: "active",
        LifecycleAction.REACTIVATE: "active",
        LifecycleAction.DISABLE: "disabled",
        LifecycleAction.EXPIRE: "expired",
        LifecycleAction.RETIRE: "retired",
    }[action]
    provisional_receipt = CognitionLifecycleReceiptV1(
        review_request_id=review_request_id,
        product_id=product_id,
        head_id=str(head.head_id),
        cognition_id=head.cognition_id,
        actor=actor,
        action=action,
        rationale=rationale,
        expected_generation=expected_generation,
        prior_revision_id=str(current_revision.revision_id),
        target_revision_id=str(target.revision_id),
        result_generation=expected_generation + 1,
        result_lifecycle=lifecycle,
        expires_at=expires_at,
    )
    next_head = CognitionHeadV1(
        cognition_id=head.cognition_id,
        scope=head.scope,
        active_revision_id=str(target.revision_id),
        generation=expected_generation + 1,
        lifecycle=lifecycle,
        authority_receipt_id=str(provisional_receipt.receipt_id),
        expires_at=expires_at if lifecycle == "active" else None,
    )
    return provisional_receipt, next_head


class CognitionLifecycleService:
    def __init__(self, pool: Any) -> None:
        self.pool = pool
        self.governance = CognitionGovernanceStore(pool)

    async def transition(
        self,
        *,
        head_id: str,
        product_id: str,
        review_request_id: str,
        actor: ReviewActorV1,
        action: LifecycleAction,
        rationale: str,
        expected_generation: int,
        target_revision_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> CognitionLifecycleReceiptV1:
        head = await self.governance.load_head(head_id)
        if head is None or head.scope.product_id != product_id:
            raise CognitionScopeError("head is unavailable in product scope")
        current_revision = await self.governance.load_revision(head.active_revision_id)
        if current_revision is None:
            raise CognitionPersistenceError("active head revision is unavailable")
        target_revision = (
            await self.governance.load_revision(target_revision_id) if target_revision_id is not None else None
        )
        if target_revision_id is not None and target_revision is None:
            raise CognitionPersistenceError("target revision is unavailable")
        receipt, next_head = build_lifecycle_transition(
            head=head,
            current_revision=current_revision,
            target_revision=target_revision,
            product_id=product_id,
            review_request_id=review_request_id,
            actor=actor,
            action=action,
            rationale=rationale,
            expected_generation=expected_generation,
            expires_at=expires_at,
        )
        try:
            result = await self._persist(head, next_head, receipt)
        except Exception:
            from core.engine.core.metrics import cognition_lifecycle_total

            cognition_lifecycle_total.labels(action=action.value, status="failed").inc()
            raise
        from core.engine.core.metrics import cognition_lifecycle_total

        cognition_lifecycle_total.labels(action=action.value, status="completed").inc()
        return result

    async def _persist(
        self,
        prior_head: CognitionHeadV1,
        next_head: CognitionHeadV1,
        receipt: CognitionLifecycleReceiptV1,
    ) -> CognitionLifecycleReceiptV1:
        event_id = stable_id("cognition_activation", {"lifecycle_receipt_id": receipt.receipt_id})
        event_key = _record_key(event_id)
        async with self.pool.connection() as db:
            existing = parse_one(
                await db.query(
                    "SELECT payload.lifecycle_receipt AS receipt FROM ONLY "
                    "type::record('cognition_activation_event', $event_key) LIMIT 1",
                    {"event_key": event_key},
                )
            )
            if existing and isinstance(existing.get("receipt"), dict):
                stored = CognitionLifecycleReceiptV1.model_validate(existing["receipt"])
                if stored == receipt:
                    return stored
                raise CognitionPersistenceError("cognition lifecycle replay conflict")
            current = parse_one(
                await db.query(
                    "SELECT generation, payload FROM ONLY type::record('cognition_head', $head_key) LIMIT 1",
                    {"head_key": _record_key(str(prior_head.head_id))},
                )
            )
            actual_generation = int(current.get("generation", 0)) if current else 0
            if actual_generation != receipt.expected_generation:
                raise CognitionPersistenceError(
                    f"cognition_head_generation_conflict:expected={receipt.expected_generation}:"
                    f"actual={actual_generation}"
                )
            params = {
                "head_key": _record_key(str(prior_head.head_id)),
                "head_content": _head_content(next_head),
                "event_key": event_key,
                "event_content": {
                    "contract_version": receipt.contract_version,
                    "cognition": parse_record_id(receipt.cognition_id),
                    "scope": next_head.scope.model_dump(mode="python"),
                    "prior_revision": parse_record_id(receipt.prior_revision_id),
                    "active_revision": parse_record_id(receipt.target_revision_id),
                    "generation": receipt.result_generation,
                    "disposition": receipt.action.value,
                    "authority_receipt_id": receipt.receipt_id,
                    "payload": {"lifecycle_receipt": receipt.model_dump(mode="python")},
                },
            }
            await _query_or_raise(
                db,
                ";\n".join(
                    [
                        "BEGIN TRANSACTION",
                        "UPDATE ONLY type::record('cognition_head', $head_key) CONTENT $head_content",
                        "CREATE ONLY type::record('cognition_activation_event', $event_key) CONTENT $event_content",
                        "COMMIT TRANSACTION",
                    ]
                )
                + ";",
                params,
            )
        return receipt
