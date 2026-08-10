"""Exact human review, repair lineage, verification, and promotion for actions.

The existing action executor remains the only boundary that admits effects.  This
module adds immutable lifecycle receipts around it without changing B1A receipts
or allowing a review, repair, or promotion record to perform an effect itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Literal, Self

from pydantic import ConfigDict, field_validator, model_validator
from pydantic_core import to_json

from ace.core.action_execution import (
    ACTION_RECORD_SPACE,
    ActionDisposition,
    ActionEffectState,
    ActionIntentV1Alpha1,
    ActionTerminalV1Alpha1,
    GovernedActionExecutionService,
    GovernedActionOutcome,
    GovernedPreparedAction,
    PreparedActionV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import GovernedActionAuthorizationProjection
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1

ACTION_REVIEW_VERSION = "ace.core.action-review/v1alpha1"
ACTION_VERIFICATION_VERSION = "ace.core.action-verification/v1alpha1"
ACTION_REPAIR_VERSION = "ace.core.action-repair/v1alpha1"
ACTION_PROMOTION_VERSION = "ace.core.action-promotion/v1alpha1"


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, *, name: str, maximum: int = 2_000) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str) -> None:
    material = instance.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if instance.receipt_id is not None and instance.receipt_id != expected_id:
        raise ValueError("receipt_id does not match exact material")
    if instance.receipt_digest is not None and instance.receipt_digest != expected_digest:
        raise ValueError("receipt_digest does not match exact material")
    object.__setattr__(instance, "receipt_id", expected_id)
    object.__setattr__(instance, "receipt_digest", expected_digest)


def _context_covers(
    context: AuthenticatedRuntimeContextV1Alpha1,
    *,
    product_id: str,
    at: datetime,
) -> bool:
    return context.product_id == product_id and context.authenticated_at <= at < context.expires_at


class ActionReviewDisposition(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ActionVerificationDisposition(StrEnum):
    VERIFIED = "verified"
    REPAIR_REQUIRED = "repair_required"


class ActionPromotionDisposition(StrEnum):
    PROMOTED = "promoted"
    REJECTED = "rejected"


class ActionReviewReceiptV1Alpha1(_StrictFrozenContract):
    """Human judgment over the exact effect-free material that may be executed."""

    contract: Literal["ace.core.action-review/v1alpha1"] = ACTION_REVIEW_VERSION
    review_key: str
    product_id: str
    intent: ActionIntentV1Alpha1
    plan: PreparedActionV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    reviewer_context: AuthenticatedRuntimeContextV1Alpha1
    authority: Literal["human"] = "human"
    disposition: ActionReviewDisposition
    rationale: str
    reviewed_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("review_key", "product_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=240)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale")

    @field_validator("reviewed_at")
    @classmethod
    def normalize_reviewed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="reviewed_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        plan = self.plan
        if (
            self.intent.product_id != self.product_id
            or plan.product_id != self.product_id
            or plan.intent_id != self.intent.intent_id
            or plan.intent_digest != self.intent.intent_digest
            or plan.action_type != self.intent.action_type
            or plan.prepared_at < self.intent.requested_at
            or self.authorization.authorized_at < plan.prepared_at
            or self.reviewed_at < self.authorization.authorized_at
            or not _context_covers(
                self.intent.authenticated_context,
                product_id=self.product_id,
                at=self.reviewed_at,
            )
            or not _context_covers(self.reviewer_context, product_id=self.product_id, at=self.reviewed_at)
            or any(item.product_id != self.product_id for item in self.authorization.state_preconditions)
        ):
            raise ValueError("action review crossed exact intent, plan, authorization, reviewer, or product scope")
        _derive_identity(self, prefix="action_review")
        return self


class ActionVerificationReceiptV1Alpha1(_StrictFrozenContract):
    """Post-effect judgment kept separate from execution and adoption."""

    contract: Literal["ace.core.action-verification/v1alpha1"] = ACTION_VERIFICATION_VERSION
    verification_key: str
    product_id: str
    review: ActionReviewReceiptV1Alpha1
    terminal: ActionTerminalV1Alpha1
    verifier_context: AuthenticatedRuntimeContextV1Alpha1
    authority: Literal["human"] = "human"
    disposition: ActionVerificationDisposition
    rationale: str
    verified_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("verification_key", "product_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=240)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale")

    @field_validator("verified_at")
    @classmethod
    def normalize_verified_at(cls, value: datetime) -> datetime:
        return _aware(value, name="verified_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        if (
            self.review.product_id != self.product_id
            or self.review.disposition is not ActionReviewDisposition.APPROVE
            or self.terminal.product_id != self.product_id
            or self.terminal.action_key != self.review.intent.action_key
            or self.verified_at < self.terminal.result.completed_at
            or not _context_covers(self.verifier_context, product_id=self.product_id, at=self.verified_at)
        ):
            raise ValueError("action verification crossed exact review, terminal, verifier, or product scope")
        if self.disposition is ActionVerificationDisposition.VERIFIED and (
            self.terminal.result.disposition is not ActionDisposition.SUCCEEDED
            or self.terminal.result.effect_state is not ActionEffectState.CONFIRMED
        ):
            raise ValueError("only a confirmed successful action can be verified")
        _derive_identity(self, prefix="action_verification")
        return self


class ActionRepairReceiptV1Alpha1(_StrictFrozenContract):
    """Explicit linked successor request; it never executes or silently retries."""

    contract: Literal["ace.core.action-repair/v1alpha1"] = ACTION_REPAIR_VERSION
    repair_key: str
    product_id: str
    verification: ActionVerificationReceiptV1Alpha1
    successor_intent: ActionIntentV1Alpha1
    requester_context: AuthenticatedRuntimeContextV1Alpha1
    authority: Literal["human"] = "human"
    rationale: str
    requested_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("repair_key", "product_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=240)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale")

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        parent = self.verification.terminal
        if (
            self.verification.product_id != self.product_id
            or self.verification.disposition is not ActionVerificationDisposition.REPAIR_REQUIRED
            or parent.result.effect_state is ActionEffectState.UNKNOWN
            or self.successor_intent.product_id != self.product_id
            or self.successor_intent.action_key == parent.action_key
            or self.successor_intent.requested_at < self.verification.verified_at
            or self.requested_at < self.successor_intent.requested_at
            or not _context_covers(self.requester_context, product_id=self.product_id, at=self.requested_at)
        ):
            raise ValueError("action repair requires known effects, explicit verification, and a fresh successor")
        _derive_identity(self, prefix="action_repair")
        return self


class ActionPromotionReceiptV1Alpha1(_StrictFrozenContract):
    """Human adoption decision over an exactly verified action result."""

    contract: Literal["ace.core.action-promotion/v1alpha1"] = ACTION_PROMOTION_VERSION
    promotion_key: str
    product_id: str
    verification: ActionVerificationReceiptV1Alpha1
    promoter_context: AuthenticatedRuntimeContextV1Alpha1
    authority: Literal["human"] = "human"
    disposition: ActionPromotionDisposition
    target_ref: str
    rationale: str
    promoted_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("promotion_key", "product_id", "target_ref")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=240)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale")

    @field_validator("promoted_at")
    @classmethod
    def normalize_promoted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="promoted_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        if (
            self.verification.product_id != self.product_id
            or self.promoted_at < self.verification.verified_at
            or not _context_covers(self.promoter_context, product_id=self.product_id, at=self.promoted_at)
        ):
            raise ValueError("action promotion crossed exact verification, promoter, or product scope")
        if (
            self.disposition is ActionPromotionDisposition.PROMOTED
            and self.verification.disposition is not ActionVerificationDisposition.VERIFIED
        ):
            raise ValueError("promotion requires an explicitly verified action")
        _derive_identity(self, prefix="action_promotion")
        return self


class GovernedActionReviewError(RuntimeError):
    """The reviewed action lifecycle failed closed."""


class GovernedActionReviewReplayConflict(GovernedActionReviewError):
    """One stable lifecycle key already binds different exact material."""


def _transaction_key(key: str, stage: str) -> str:
    return f"action_{stage}:{canonical_hash([key, stage])[:32]}"


class _FrozenAuthorizer:
    def __init__(self, review: ActionReviewReceiptV1Alpha1) -> None:
        self.review = review

    async def authorize_action(self, request):
        if (
            request.product_id != self.review.product_id
            or request.subject_ref != self.review.plan.plan_id
            or request.subject_digest != self.review.plan.plan_digest
            or request.authenticated_context != self.review.intent.authenticated_context
        ):
            raise GovernedActionReviewError("review authorization crossed exact prepared material")
        return self.review.authorization


class _FrozenPlanAdapter:
    def __init__(self, review: ActionReviewReceiptV1Alpha1, delegate) -> None:
        self.review = review
        self.delegate = delegate
        self.artifact_identity = delegate.artifact_identity

    async def prepare(self, intent):
        if intent != self.review.intent:
            raise GovernedActionReviewError("review intent crossed exact prepared material")
        return self.review.plan

    async def execute(self, plan, authorization):
        if plan != self.review.plan or authorization != self.review.authorization:
            raise GovernedActionReviewError("execution crossed exact reviewed material")
        return await self.delegate.execute(plan, authorization)


class GovernedActionReviewService:
    """Replay-safe human gates around one explicitly composed action executor."""

    _MODELS = {
        "review": ActionReviewReceiptV1Alpha1,
        "verification": ActionVerificationReceiptV1Alpha1,
        "repair": ActionRepairReceiptV1Alpha1,
        "promotion": ActionPromotionReceiptV1Alpha1,
    }

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        executor: GovernedActionExecutionService,
        clock: Callable[[], datetime],
    ) -> None:
        if executor.store is not store:
            raise GovernedActionReviewError("review and execution must share one immutable record store")
        self.store = store
        self.executor = executor
        self.clock = clock

    def _now(self) -> datetime:
        try:
            return _aware(self.clock(), name="action review service clock")
        except Exception:
            raise GovernedActionReviewError("action review service clock must return a timezone-aware value") from None

    async def prepare_for_review(self, intent: ActionIntentV1Alpha1) -> GovernedPreparedAction:
        existing = await self.executor._load_stage(intent=intent, stage="admission")
        if existing is not None:
            raise GovernedActionReviewError("an already admitted action cannot be prepared for later review")
        return await self.executor.prepare(intent)

    async def _load(self, *, product_id: str, key: str, stage: str):
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=ACTION_RECORD_SPACE,
                transaction_key=_transaction_key(key, stage),
            )
        except Exception as exc:
            raise GovernedActionReviewError(f"action_{stage} replay load failed closed") from exc
        if transaction is None:
            return None
        kind = f"action_{stage}"
        if len(transaction.records) != 1 or transaction.records[0].record_kind != kind:
            raise GovernedActionReviewReplayConflict(f"{kind} transaction has an invalid exact shape")
        reference = transaction.records[0]
        try:
            record = await self.store.load_record(
                reference.storage_id,
                product_id=product_id,
                record_space=ACTION_RECORD_SPACE,
                record_kind=kind,
            )
        except Exception as exc:
            raise GovernedActionReviewError(f"{kind} exact record load failed closed") from exc
        if record is None or record.reference() != reference:
            raise GovernedActionReviewReplayConflict(f"{kind} exact immutable record is unavailable")
        model = self._MODELS[stage]
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception as exc:
            raise GovernedActionReviewReplayConflict(f"{kind} payload failed exact replay") from exc
        key_field = {
            "review": "review_key",
            "verification": "verification_key",
            "repair": "repair_key",
            "promotion": "promotion_key",
        }[stage]
        reconstructed = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=ACTION_RECORD_SPACE,
            transaction_key=_transaction_key(key, stage),
            records=(record,),
            submitted_at=transaction.committed_at,
            governed_state_preconditions=transaction.governed_state_preconditions,
        )
        expected_preconditions = (
            value.review.authorization.state_preconditions
            if stage == "verification"
            else (
                value.verification.review.authorization.state_preconditions
                if stage in {"repair", "promotion"}
                else value.authorization.state_preconditions
            )
        )
        if (
            record.payload_contract != value.contract
            or transaction.committed_at != record.available_at
            or record.as_of != record.available_at
            or getattr(value, key_field) != key
            or transaction.governed_state_preconditions != expected_preconditions
            or transaction != reconstructed.receipt()
        ):
            raise GovernedActionReviewReplayConflict(f"{kind} crossed its exact durable envelope")
        return value, transaction

    async def _append(self, value, *, key: str, stage: str) -> tuple[object, AppendOnlyTransactionReceiptV1, bool]:
        kind = f"action_{stage}"
        available_at = getattr(
            value,
            {
                "review": "reviewed_at",
                "verification": "verified_at",
                "repair": "requested_at",
                "promotion": "promoted_at",
            }[stage],
        )
        record = ImmutableRecordV1(
            product_id=value.product_id,
            record_space=ACTION_RECORD_SPACE,
            record_kind=kind,
            record_key=str(value.receipt_id),
            payload_contract=value.contract,
            payload=value.model_dump(mode="python"),
            as_of=available_at,
            available_at=available_at,
            processing_order=0,
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=value.product_id,
            record_space=ACTION_RECORD_SPACE,
            transaction_key=_transaction_key(key, stage),
            records=(record,),
            submitted_at=available_at,
            governed_state_preconditions=value.review.authorization.state_preconditions
            if stage == "verification"
            else (
                value.verification.review.authorization.state_preconditions
                if stage in {"repair", "promotion"}
                else value.authorization.state_preconditions
            ),
        )
        try:
            receipt = await self.store.append(request)
        except ImmutableRecordReplayConflict:
            loaded = await self._load(product_id=value.product_id, key=key, stage=stage)
            if loaded is None or loaded[0] != value:
                raise GovernedActionReviewReplayConflict(
                    f"stable action {stage} key already binds different exact material"
                ) from None
            return loaded[0], loaded[1], True
        if receipt != request.receipt():
            raise GovernedActionReviewReplayConflict(f"action_{stage} append returned divergent material")
        return value, receipt, False

    async def review(
        self,
        prepared: GovernedPreparedAction,
        *,
        review_key: str,
        reviewer_context: AuthenticatedRuntimeContextV1Alpha1,
        disposition: ActionReviewDisposition,
        rationale: str,
    ) -> ActionReviewReceiptV1Alpha1:
        if prepared.plan.artifact != self.executor.operation_binding.artifact:
            raise GovernedActionReviewError("prepared review material crossed the composed adapter binding")
        receipt = ActionReviewReceiptV1Alpha1(
            review_key=review_key,
            product_id=prepared.intent.product_id,
            intent=prepared.intent,
            plan=prepared.plan,
            authorization=prepared.authorization,
            reviewer_context=reviewer_context,
            disposition=disposition,
            rationale=rationale,
            reviewed_at=self._now(),
        )
        persisted, _, _ = await self._append(receipt, key=review_key, stage="review")
        return ActionReviewReceiptV1Alpha1.model_validate(persisted)

    async def load_review(self, *, product_id: str, review_key: str) -> ActionReviewReceiptV1Alpha1 | None:
        """Reload one exact durable review after process or service reconstruction."""

        loaded = await self._load(product_id=product_id, key=review_key, stage="review")
        return None if loaded is None else ActionReviewReceiptV1Alpha1.model_validate(loaded[0])

    async def load_verification(
        self,
        *,
        product_id: str,
        verification_key: str,
    ) -> ActionVerificationReceiptV1Alpha1 | None:
        """Reload one exact durable post-effect verification."""

        loaded = await self._load(product_id=product_id, key=verification_key, stage="verification")
        return None if loaded is None else ActionVerificationReceiptV1Alpha1.model_validate(loaded[0])

    async def execute_reviewed(self, review: ActionReviewReceiptV1Alpha1) -> GovernedActionOutcome:
        loaded = await self._load(product_id=review.product_id, key=review.review_key, stage="review")
        if loaded is None or loaded[0] != review:
            raise GovernedActionReviewError("exact action review is not durably available")
        if review.disposition is not ActionReviewDisposition.APPROVE:
            raise GovernedActionReviewError("rejected action review cannot execute")
        reviewed_executor = GovernedActionExecutionService(
            store=self.store,
            authorizer=_FrozenAuthorizer(review),
            operation_binding=self.executor.operation_binding,
            adapter=_FrozenPlanAdapter(review, self.executor.adapter),
            clock=self.executor.clock,
        )
        outcome = await reviewed_executor.execute(review.intent)
        if outcome.admission.plan != review.plan or outcome.admission.authorization != review.authorization:
            raise GovernedActionReviewReplayConflict("durable admission crossed exact reviewed material")
        return outcome

    async def verify(
        self,
        review: ActionReviewReceiptV1Alpha1,
        outcome: GovernedActionOutcome,
        *,
        verification_key: str,
        verifier_context: AuthenticatedRuntimeContextV1Alpha1,
        disposition: ActionVerificationDisposition,
        rationale: str,
    ) -> ActionVerificationReceiptV1Alpha1:
        loaded_review = await self._load(product_id=review.product_id, key=review.review_key, stage="review")
        terminal_loaded = await self.executor._load_stage(intent=review.intent, stage="terminal")
        if (
            loaded_review is None
            or loaded_review[0] != review
            or terminal_loaded is None
            or terminal_loaded[0] != outcome.terminal
            or outcome.admission.plan != review.plan
            or outcome.admission.authorization != review.authorization
            or outcome.terminal.admission != outcome.admission.reference()
            or outcome.terminal.action_key != review.intent.action_key
        ):
            raise GovernedActionReviewError("verification outcome crossed exact reviewed action")
        receipt = ActionVerificationReceiptV1Alpha1(
            verification_key=verification_key,
            product_id=review.product_id,
            review=review,
            terminal=outcome.terminal,
            verifier_context=verifier_context,
            disposition=disposition,
            rationale=rationale,
            verified_at=self._now(),
        )
        persisted, _, _ = await self._append(receipt, key=verification_key, stage="verification")
        return ActionVerificationReceiptV1Alpha1.model_validate(persisted)

    async def request_repair(
        self,
        verification: ActionVerificationReceiptV1Alpha1,
        successor_intent: ActionIntentV1Alpha1,
        *,
        repair_key: str,
        requester_context: AuthenticatedRuntimeContextV1Alpha1,
        rationale: str,
    ) -> ActionRepairReceiptV1Alpha1:
        loaded = await self._load(
            product_id=verification.product_id,
            key=verification.verification_key,
            stage="verification",
        )
        if loaded is None or loaded[0] != verification:
            raise GovernedActionReviewError("exact action verification is not durably available")
        receipt = ActionRepairReceiptV1Alpha1(
            repair_key=repair_key,
            product_id=verification.product_id,
            verification=verification,
            successor_intent=successor_intent,
            requester_context=requester_context,
            rationale=rationale,
            requested_at=self._now(),
        )
        persisted, _, _ = await self._append(receipt, key=repair_key, stage="repair")
        return ActionRepairReceiptV1Alpha1.model_validate(persisted)

    async def promote(
        self,
        verification: ActionVerificationReceiptV1Alpha1,
        *,
        promotion_key: str,
        promoter_context: AuthenticatedRuntimeContextV1Alpha1,
        disposition: ActionPromotionDisposition,
        target_ref: str,
        rationale: str,
    ) -> ActionPromotionReceiptV1Alpha1:
        loaded = await self._load(
            product_id=verification.product_id,
            key=verification.verification_key,
            stage="verification",
        )
        if loaded is None or loaded[0] != verification:
            raise GovernedActionReviewError("exact action verification is not durably available")
        receipt = ActionPromotionReceiptV1Alpha1(
            promotion_key=promotion_key,
            product_id=verification.product_id,
            verification=verification,
            promoter_context=promoter_context,
            disposition=disposition,
            target_ref=target_ref,
            rationale=rationale,
            promoted_at=self._now(),
        )
        persisted, _, _ = await self._append(receipt, key=promotion_key, stage="promotion")
        return ActionPromotionReceiptV1Alpha1.model_validate(persisted)


__all__ = [
    "ACTION_PROMOTION_VERSION",
    "ACTION_REPAIR_VERSION",
    "ACTION_REVIEW_VERSION",
    "ACTION_VERIFICATION_VERSION",
    "ActionPromotionDisposition",
    "ActionPromotionReceiptV1Alpha1",
    "ActionRepairReceiptV1Alpha1",
    "ActionReviewDisposition",
    "ActionReviewReceiptV1Alpha1",
    "ActionVerificationDisposition",
    "ActionVerificationReceiptV1Alpha1",
    "GovernedActionReviewError",
    "GovernedActionReviewReplayConflict",
    "GovernedActionReviewService",
]
