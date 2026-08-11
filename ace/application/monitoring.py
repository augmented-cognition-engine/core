"""Append-only owner lifecycle and explicitly requested sensing-window services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ace.core.contracts import canonical_hash
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.intelligence.contracts.monitoring import (
    MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND,
    MONITORING_LIFECYCLE_RECORD_KIND,
    MONITORING_LIFECYCLE_REVISION_RECORD_KIND,
    SENSING_WINDOW_RECORD_KIND,
    ExactMaterialReferenceV1Alpha1,
    MonitoringLifecycleAction,
    MonitoringLifecycleAnchorV1Alpha1,
    MonitoringLifecycleReceiptV1Alpha1,
    MonitoringLifecycleRequestV1Alpha1,
    MonitoringLifecycleRevisionV1Alpha1,
    MonitoringLifecycleState,
    MonitoringTargetKind,
    SensingWindowEvaluationV1Alpha1,
    SensingWindowReceiptV1Alpha1,
    SensingWindowRequestV1Alpha1,
    monitoring_lifecycle_revision_id,
)
from ace.intelligence.contracts.monitors import MonitorDisposition, MonitorV1Alpha1
from ace.intelligence.contracts.subscriptions import PersonaBindingV1Alpha1, SubscriptionV1Alpha1

LIVE_MONITORING_RECORD_SPACE = "ace.intelligence.live-monitoring"


class MonitoringLifecycleError(ValueError):
    """A lifecycle transition failed ownership, chain, or persistence checks."""


class MonitoringLifecycleReplayConflict(MonitoringLifecycleError):
    """One stable transition key already binds different exact material."""


class SensingWindowError(ValueError):
    """A sensing-window evaluation failed lifecycle, guard, or persistence checks."""


class SensingWindowReplayConflict(SensingWindowError):
    """One stable window key already binds different exact material."""


@dataclass(frozen=True, slots=True)
class MonitoringLifecycleAdmission:
    receipt: MonitoringLifecycleReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class SensingWindowAdmission:
    receipt: SensingWindowReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


def _transaction_key(kind: str, stable_key: str) -> str:
    return f"{kind}:{canonical_hash([kind, stable_key])[:32]}"


def _exact_reference(reference: str | None, digest: str | None) -> ExactMaterialReferenceV1Alpha1:
    return ExactMaterialReferenceV1Alpha1(reference=str(reference), digest=str(digest))


def _lifecycle_anchor_record(
    anchor: MonitoringLifecycleAnchorV1Alpha1,
    *,
    available_at: datetime,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=anchor.product_id,
        record_space=LIVE_MONITORING_RECORD_SPACE,
        record_kind=MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND,
        record_key=str(anchor.lifecycle_id),
        payload_contract=anchor.contract,
        payload=anchor.model_dump(mode="python"),
        as_of=available_at,
        available_at=available_at,
        processing_order=0,
    )


def _lifecycle_record(
    receipt: MonitoringLifecycleReceiptV1Alpha1,
    *,
    processing_order: int = 0,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=receipt.product_id,
        record_space=LIVE_MONITORING_RECORD_SPACE,
        record_kind=MONITORING_LIFECYCLE_RECORD_KIND,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.applied_at,
        available_at=receipt.applied_at,
        processing_order=processing_order,
    )


def _lifecycle_revision_record(
    revision: MonitoringLifecycleRevisionV1Alpha1,
    *,
    available_at: datetime,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=revision.product_id,
        record_space=LIVE_MONITORING_RECORD_SPACE,
        record_kind=MONITORING_LIFECYCLE_REVISION_RECORD_KIND,
        record_key=str(revision.revision_id),
        payload_contract=revision.contract,
        payload=revision.model_dump(mode="python"),
        as_of=available_at,
        available_at=available_at,
        processing_order=processing_order,
    )


def _sensing_record(receipt: SensingWindowReceiptV1Alpha1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=receipt.product_id,
        record_space=LIVE_MONITORING_RECORD_SPACE,
        record_kind=SENSING_WINDOW_RECORD_KIND,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.window_ended_at,
        available_at=receipt.evaluated_at,
        processing_order=0,
    )


class _MonitoringStoreService:
    def __init__(self, *, store: ImmutableRecordStore) -> None:
        self.store = store

    async def _load_record(self, *, product_id: str, kind: str, reference: str) -> ImmutableRecordV1:
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=LIVE_MONITORING_RECORD_SPACE,
            record_kind=kind,
            record_key=reference,
        )
        try:
            record = await self.store.load_record(
                storage_id,
                product_id=product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                record_kind=kind,
            )
        except Exception:
            record = None
        if record is None or record.record_key != reference:
            raise ValueError("monitoring record reference is missing from the append-only ledger")
        return record

    async def _load_lifecycle(
        self,
        *,
        product_id: str,
        reference: ExactMaterialReferenceV1Alpha1,
    ) -> MonitoringLifecycleReceiptV1Alpha1:
        record = await self._load_record(
            product_id=product_id,
            kind=MONITORING_LIFECYCLE_RECORD_KIND,
            reference=reference.reference,
        )
        try:
            receipt = MonitoringLifecycleReceiptV1Alpha1.model_validate(record.payload)
        except Exception:
            raise ValueError("monitoring lifecycle record failed exact contract replay") from None
        if (
            receipt.reference() != reference
            or record.payload_contract != receipt.contract
            or record.available_at != receipt.applied_at
            or record.as_of != receipt.applied_at
        ):
            raise ValueError("monitoring lifecycle envelope crossed its exact receipt")
        return receipt

    async def _load_current_lifecycle(
        self,
        *,
        product_id: str,
        reference: ExactMaterialReferenceV1Alpha1,
        available_at: datetime,
    ) -> MonitoringLifecycleReceiptV1Alpha1:
        receipt = await self._load_lifecycle(product_id=product_id, reference=reference)
        try:
            records = await self.store.read_as_of(
                product_id=product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                record_kind=MONITORING_LIFECYCLE_RECORD_KIND,
                available_at=available_at,
            )
            candidates_list: list[MonitoringLifecycleReceiptV1Alpha1] = []
            for record in records:
                candidate = MonitoringLifecycleReceiptV1Alpha1.model_validate(record.payload)
                if (
                    record.record_key != candidate.receipt_id
                    or record.payload_contract != candidate.contract
                    or record.as_of != candidate.applied_at
                    or record.available_at != candidate.applied_at
                ):
                    raise ValueError("lifecycle record envelope crossed its exact receipt")
                if candidate.lifecycle == receipt.lifecycle:
                    candidates_list.append(candidate)
            candidates = tuple(sorted(candidates_list, key=lambda item: item.sequence))
        except Exception:
            raise ValueError("current monitoring lifecycle read failed exact replay") from None
        if not candidates:
            raise ValueError("current monitoring lifecycle is missing at the sensing cutoff")
        if tuple(item.sequence for item in candidates) != tuple(range(1, len(candidates) + 1)):
            raise ValueError("current monitoring lifecycle contains a missing or divergent sequence")
        for previous, current in zip(candidates, candidates[1:]):
            if current.prior_receipt != previous.reference() or current.state_before is not previous.state_after:
                raise ValueError("current monitoring lifecycle chain is not exact")
        latest = candidates[-1]
        if latest.reference() != reference:
            raise ValueError("sensing window cited a stale monitoring lifecycle receipt")
        return receipt


class MonitoringLifecycleService(_MonitoringStoreService):
    """Authorize an owner's append-only Monitor or Subscription transition."""

    @staticmethod
    def _validate_target(
        *,
        request: MonitoringLifecycleRequestV1Alpha1,
        persona_binding: PersonaBindingV1Alpha1,
        target: MonitorV1Alpha1 | SubscriptionV1Alpha1,
    ) -> MonitoringLifecycleState:
        binding_reference = _exact_reference(persona_binding.binding_ref, persona_binding.binding_digest)
        if (
            persona_binding.product_id != request.product_id
            or persona_binding.principal_ref != request.authenticated_context.actor_ref
            or binding_reference != request.persona_binding
        ):
            raise MonitoringLifecycleError("monitoring transition is not authorized by the bound owner")

        if isinstance(target, MonitorV1Alpha1):
            expected_kind = MonitoringTargetKind.MONITOR
            target_reference = _exact_reference(target.monitor_ref, target.monitor_digest)
            if (
                target.product_id != request.product_id
                or target.compiled_pack != persona_binding.compiled_pack
                or target.activation_revision_ref != persona_binding.activation_revision_ref
            ):
                raise MonitoringLifecycleError("monitor lifecycle crossed pack, activation, or product scope")
            initial_state = (
                MonitoringLifecycleState.ACTIVE
                if target.disposition is MonitorDisposition.ENABLED
                else MonitoringLifecycleState.PAUSED
            )
        elif isinstance(target, SubscriptionV1Alpha1):
            expected_kind = MonitoringTargetKind.SUBSCRIPTION
            target_reference = _exact_reference(target.subscription_ref, target.subscription_digest)
            if target.product_id != request.product_id or target.persona_binding_ref != persona_binding.binding_ref:
                raise MonitoringLifecycleError("subscription lifecycle crossed its exact owner binding")
            initial_state = MonitoringLifecycleState.ACTIVE
        else:
            raise MonitoringLifecycleError("unsupported monitoring lifecycle target")

        if request.target_kind is not expected_kind or request.target != target_reference:
            raise MonitoringLifecycleError("monitoring request does not bind the supplied exact target")
        return initial_state

    async def _replay(
        self,
        *,
        product_id: str,
        transition_key: str,
        expected: ExactMaterialReferenceV1Alpha1,
    ) -> MonitoringLifecycleAdmission | None:
        transaction_key = _transaction_key("monitoring_lifecycle", transition_key)
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception:
            raise MonitoringLifecycleError("monitoring lifecycle transaction load failed closed") from None
        if transaction is None:
            return None
        if (
            len(transaction.records) not in {2, 3}
            or transaction.records[-1].record_kind != MONITORING_LIFECYCLE_RECORD_KIND
            or transaction.records[-2].record_kind != MONITORING_LIFECYCLE_REVISION_RECORD_KIND
        ):
            raise MonitoringLifecycleError("monitoring transaction does not contain one exact lifecycle append")
        try:
            record = await self._load_record(
                product_id=product_id,
                kind=MONITORING_LIFECYCLE_RECORD_KIND,
                reference=expected.reference,
            )
            receipt = MonitoringLifecycleReceiptV1Alpha1.model_validate(record.payload)
        except ValueError as exc:
            raise MonitoringLifecycleReplayConflict("transition key already binds different exact material") from exc
        reference = transaction.records[-1]
        if (
            receipt.reference() != expected
            or reference != record.reference()
            or reference.record_key != receipt.receipt_id
            or transaction.committed_at != receipt.applied_at
        ):
            raise MonitoringLifecycleError("monitoring transaction crossed its exact lifecycle receipt")
        revision_id = monitoring_lifecycle_revision_id(
            lifecycle=receipt.lifecycle,
            sequence=receipt.sequence,
        )
        try:
            revision_record = await self._load_record(
                product_id=product_id,
                kind=MONITORING_LIFECYCLE_REVISION_RECORD_KIND,
                reference=revision_id,
            )
            revision = MonitoringLifecycleRevisionV1Alpha1.model_validate(revision_record.payload)
        except Exception:
            raise MonitoringLifecycleError("lifecycle transaction revision slot failed exact replay") from None
        if (
            transaction.records[-2] != revision_record.reference()
            or revision.product_id != receipt.product_id
            or revision.lifecycle != receipt.lifecycle
            or revision.sequence != receipt.sequence
            or revision.receipt != receipt.reference()
        ):
            raise MonitoringLifecycleError("lifecycle transaction crossed its append-once revision slot")
        if receipt.action is MonitoringLifecycleAction.CREATE:
            if len(transaction.records) != 3 or transaction.records[0].record_kind != (
                MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND
            ):
                raise MonitoringLifecycleError("create transaction is missing its stable lifecycle anchor")
            try:
                anchor_record = await self._load_record(
                    product_id=product_id,
                    kind=MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND,
                    reference=receipt.lifecycle.reference,
                )
                anchor = MonitoringLifecycleAnchorV1Alpha1.model_validate(anchor_record.payload)
            except Exception:
                raise MonitoringLifecycleError("create transaction lifecycle anchor failed exact replay") from None
            if (
                anchor.reference() != receipt.lifecycle
                or transaction.records[0] != anchor_record.reference()
                or anchor.target_kind is not receipt.target_kind
                or anchor.target != receipt.target
                or anchor.persona_binding != receipt.persona_binding
            ):
                raise MonitoringLifecycleError("create transaction crossed its exact lifecycle anchor")
        elif len(transaction.records) != 2:
            raise MonitoringLifecycleError("later lifecycle transaction unexpectedly rewrote its anchor")
        return MonitoringLifecycleAdmission(receipt=receipt, transaction_receipt=transaction, replayed=True)

    async def transition(
        self,
        *,
        request: MonitoringLifecycleRequestV1Alpha1,
        persona_binding: PersonaBindingV1Alpha1,
        target: MonitorV1Alpha1 | SubscriptionV1Alpha1,
        applied_at: datetime,
    ) -> MonitoringLifecycleAdmission:
        """Validate, append, or exactly replay one owner transition."""

        try:
            request = MonitoringLifecycleRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            persona_binding = PersonaBindingV1Alpha1.model_validate(persona_binding.model_dump(mode="python"))
            target = type(target).model_validate(target.model_dump(mode="python"))
        except Exception:
            raise MonitoringLifecycleError("monitoring lifecycle inputs failed exact revalidation") from None
        initial_state = self._validate_target(
            request=request,
            persona_binding=persona_binding,
            target=target,
        )
        if (
            applied_at.tzinfo is None
            or applied_at.utcoffset() is None
            or not request.requested_at <= applied_at < request.authenticated_context.expires_at
        ):
            raise MonitoringLifecycleError("monitoring transition must apply inside its authenticated window")

        prior: MonitoringLifecycleReceiptV1Alpha1 | None = None
        if request.prior_receipt is not None:
            try:
                prior = await self._load_lifecycle(
                    product_id=request.product_id,
                    reference=request.prior_receipt,
                )
            except ValueError as exc:
                raise MonitoringLifecycleError(str(exc)) from exc
            if (
                prior.product_id != request.product_id
                or prior.owner_ref != request.authenticated_context.actor_ref
                or prior.target_kind is not request.target_kind
                or prior.target != request.target
                or prior.persona_binding != request.persona_binding
                or prior.lifecycle != request.lifecycle
                or prior.sequence + 1 != request.sequence
                or prior.applied_at > request.requested_at
            ):
                raise MonitoringLifecycleError("monitoring transition crossed its exact owner lifecycle chain")

        before = prior.state_after if prior is not None else None
        if request.action is MonitoringLifecycleAction.CREATE:
            after = initial_state
        elif request.action is MonitoringLifecycleAction.PAUSE:
            after = MonitoringLifecycleState.PAUSED
        elif request.action is MonitoringLifecycleAction.RESUME:
            after = MonitoringLifecycleState.ACTIVE
        else:
            after = MonitoringLifecycleState.REVOKED
        try:
            receipt = MonitoringLifecycleReceiptV1Alpha1(
                product_id=request.product_id,
                owner_ref=request.authenticated_context.actor_ref,
                target_kind=request.target_kind,
                target=request.target,
                persona_binding=request.persona_binding,
                lifecycle=request.lifecycle,
                request=_exact_reference(request.request_id, request.request_digest),
                action=request.action,
                sequence=request.sequence,
                state_before=before,
                state_after=after,
                prior_receipt=request.prior_receipt,
                applied_at=applied_at,
            )
        except Exception:
            raise MonitoringLifecycleError("monitoring lifecycle transition is not allowed") from None

        exact_reference = receipt.reference()
        replay = await self._replay(
            product_id=request.product_id,
            transition_key=request.transition_key,
            expected=exact_reference,
        )
        if replay is not None:
            return replay

        records: tuple[ImmutableRecordV1, ...]
        revision = MonitoringLifecycleRevisionV1Alpha1(
            product_id=request.product_id,
            lifecycle=receipt.lifecycle,
            sequence=receipt.sequence,
            receipt=receipt.reference(),
        )
        if request.action is MonitoringLifecycleAction.CREATE:
            anchor = MonitoringLifecycleAnchorV1Alpha1(
                product_id=request.product_id,
                target_kind=request.target_kind,
                target=request.target,
                persona_binding=request.persona_binding,
                lifecycle_id=request.lifecycle.reference,
                lifecycle_digest=request.lifecycle.digest,
            )
            records = (
                _lifecycle_anchor_record(anchor, available_at=receipt.applied_at),
                _lifecycle_revision_record(revision, available_at=receipt.applied_at, processing_order=1),
                _lifecycle_record(receipt, processing_order=2),
            )
        else:
            records = (
                _lifecycle_revision_record(revision, available_at=receipt.applied_at, processing_order=0),
                _lifecycle_record(receipt, processing_order=1),
            )
        transaction = AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=LIVE_MONITORING_RECORD_SPACE,
            transaction_key=_transaction_key("monitoring_lifecycle", request.transition_key),
            records=records,
            submitted_at=receipt.applied_at,
        )
        try:
            committed = await self.store.append(transaction)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            replay = await self._replay(
                product_id=request.product_id,
                transition_key=request.transition_key,
                expected=exact_reference,
            )
            if replay is None:
                raise MonitoringLifecycleError("monitoring lifecycle append failed closed") from None
            return replay
        except Exception:
            raise MonitoringLifecycleError("monitoring lifecycle append failed closed") from None
        if committed != transaction.receipt():
            raise MonitoringLifecycleError("Core append receipt does not bind the exact lifecycle request")
        return MonitoringLifecycleAdmission(receipt=receipt, transaction_receipt=committed, replayed=False)


class SensingWindowService(_MonitoringStoreService):
    """Append one explicit routed-or-suppressed sensing-window receipt."""

    async def _replay(
        self,
        *,
        product_id: str,
        window_key: str,
        expected: ExactMaterialReferenceV1Alpha1,
    ) -> SensingWindowAdmission | None:
        transaction_key = _transaction_key("sensing_window", window_key)
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=LIVE_MONITORING_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception:
            raise SensingWindowError("sensing-window transaction load failed closed") from None
        if transaction is None:
            return None
        if len(transaction.records) != 1 or transaction.records[0].record_kind != SENSING_WINDOW_RECORD_KIND:
            raise SensingWindowError("sensing transaction does not contain one window receipt")
        reference = transaction.records[0]
        try:
            record = await self._load_record(
                product_id=product_id,
                kind=SENSING_WINDOW_RECORD_KIND,
                reference=expected.reference,
            )
            receipt = SensingWindowReceiptV1Alpha1.model_validate(record.payload)
        except Exception:
            raise SensingWindowReplayConflict("window key already binds different exact material") from None
        if (
            receipt.reference() != expected
            or reference != record.reference()
            or reference.record_key != receipt.receipt_id
            or record.payload_contract != receipt.contract
            or record.as_of != receipt.window_ended_at
            or record.available_at != receipt.evaluated_at
            or transaction.committed_at != receipt.evaluated_at
        ):
            raise SensingWindowError("sensing transaction crossed its exact window receipt")
        return SensingWindowAdmission(receipt=receipt, transaction_receipt=transaction, replayed=True)

    async def record(
        self,
        *,
        request: SensingWindowRequestV1Alpha1,
        evaluation: SensingWindowEvaluationV1Alpha1,
    ) -> SensingWindowAdmission:
        """Validate lifecycle guards, append, or exactly replay one window."""

        try:
            request = SensingWindowRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            evaluation = SensingWindowEvaluationV1Alpha1.model_validate(evaluation.model_dump(mode="python"))
        except Exception:
            raise SensingWindowError("sensing-window inputs failed exact revalidation") from None
        if evaluation.request != request.reference() or evaluation.evaluated_at < request.window_ended_at:
            raise SensingWindowError("sensing evaluation crossed its exact bounded request")
        try:
            monitor = await self._load_current_lifecycle(
                product_id=request.product_id,
                reference=request.monitor_lifecycle,
                available_at=request.window_started_at,
            )
            subscription = await self._load_current_lifecycle(
                product_id=request.product_id,
                reference=request.subscription_lifecycle,
                available_at=request.window_started_at,
            )
        except ValueError as exc:
            raise SensingWindowError(str(exc)) from exc
        if (
            monitor.target_kind is not MonitoringTargetKind.MONITOR
            or subscription.target_kind is not MonitoringTargetKind.SUBSCRIPTION
            or monitor.product_id != request.product_id
            or subscription.product_id != request.product_id
            or monitor.owner_ref != request.authenticated_context.actor_ref
            or subscription.owner_ref != request.authenticated_context.actor_ref
            or monitor.owner_ref != subscription.owner_ref
            or monitor.persona_binding != subscription.persona_binding
            or monitor.applied_at > request.window_started_at
            or subscription.applied_at > request.window_started_at
        ):
            raise SensingWindowError("sensing window crossed owner, target, product, or lifecycle scope")
        try:
            receipt = SensingWindowReceiptV1Alpha1(
                product_id=request.product_id,
                owner_ref=request.authenticated_context.actor_ref,
                request=request.reference(),
                monitor_lifecycle=request.monitor_lifecycle,
                subscription_lifecycle=request.subscription_lifecycle,
                monitor_state=monitor.state_after,
                subscription_state=subscription.state_after,
                requested_at=request.requested_at,
                window_started_at=request.window_started_at,
                window_ended_at=request.window_ended_at,
                acquisition_requests=evaluation.acquisition_requests,
                source_transactions=evaluation.source_transactions,
                accepted_resources=evaluation.accepted_resources,
                replayed_resources=evaluation.replayed_resources,
                routed_resources=evaluation.routed_resources,
                material_kind=evaluation.material_kind,
                disposition=evaluation.disposition,
                suppression_reason=evaluation.suppression_reason,
                correction_visible=evaluation.correction_visible,
                evaluated_at=evaluation.evaluated_at,
            )
        except Exception:
            raise SensingWindowError("sensing-window disposition violated lifecycle or material guards") from None

        exact_reference = receipt.reference()
        replay = await self._replay(
            product_id=request.product_id,
            window_key=request.window_key,
            expected=exact_reference,
        )
        if replay is not None:
            return replay
        transaction = AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=LIVE_MONITORING_RECORD_SPACE,
            transaction_key=_transaction_key("sensing_window", request.window_key),
            records=(_sensing_record(receipt),),
            submitted_at=receipt.evaluated_at,
        )
        try:
            committed = await self.store.append(transaction)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            replay = await self._replay(
                product_id=request.product_id,
                window_key=request.window_key,
                expected=exact_reference,
            )
            if replay is None:
                raise SensingWindowError("sensing-window append failed closed") from None
            return replay
        except Exception:
            raise SensingWindowError("sensing-window append failed closed") from None
        if committed != transaction.receipt():
            raise SensingWindowError("Core append receipt does not bind the exact sensing window")
        return SensingWindowAdmission(receipt=receipt, transaction_receipt=committed, replayed=False)


__all__ = [
    "LIVE_MONITORING_RECORD_SPACE",
    "MonitoringLifecycleAdmission",
    "MonitoringLifecycleError",
    "MonitoringLifecycleReplayConflict",
    "MonitoringLifecycleService",
    "SensingWindowAdmission",
    "SensingWindowError",
    "SensingWindowReplayConflict",
    "SensingWindowService",
]
