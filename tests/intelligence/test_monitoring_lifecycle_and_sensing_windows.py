from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application import (
    MonitoringLifecycleError,
    MonitoringLifecycleReplayConflict,
    MonitoringLifecycleService,
    SensingWindowError,
    SensingWindowReplayConflict,
    SensingWindowService,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    CompiledPackRefV1,
    ExactMaterialReferenceV1Alpha1,
    MonitorDisposition,
    MonitoringLifecycleAction,
    MonitoringLifecycleRequestV1Alpha1,
    MonitoringLifecycleState,
    MonitoringTargetKind,
    MonitorV1Alpha1,
    PersonaBindingV1Alpha1,
    SensingWindowDisposition,
    SensingWindowEvaluationV1Alpha1,
    SensingWindowMaterialKind,
    SensingWindowRequestV1Alpha1,
    SensingWindowSuppressionReason,
    SubscriptionDeliveryDisposition,
    SubscriptionV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

BASE = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)
PRODUCT_ID = "product:generic-monitoring"
OWNER = "principal:analyst"
PACK = CompiledPackRefV1(
    pack_id="generic_monitoring",
    pack_version="0.5.0-alpha.1",
    compiled_pack_id="pack_ir:" + "a" * 32,
    pack_digest="sha256:" + "a" * 64,
)


def _auth(*, actor: str = OWNER) -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT_ID,
        actor_ref=actor,
        authentication_receipt_ref=f"authentication:{actor.rsplit(':', 1)[-1]}",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=BASE,
        expires_at=BASE + timedelta(hours=2),
    )


def _intent() -> tuple[MonitorV1Alpha1, PersonaBindingV1Alpha1, SubscriptionV1Alpha1]:
    monitor = MonitorV1Alpha1(
        monitor_id="material_change",
        product_id=PRODUCT_ID,
        subject_entity_type_ids=("subject",),
        subject_refs=("entity:subject:one",),
        detection_rule_ids=("material_change",),
        compiled_pack=PACK,
        activation_revision_ref="activation_revision:one",
        disposition=MonitorDisposition.ENABLED,
    )
    binding = PersonaBindingV1Alpha1(
        product_id=PRODUCT_ID,
        principal_ref=OWNER,
        persona_id="domain_analyst",
        compiled_pack=PACK,
        activation_revision_ref="activation_revision:one",
    )
    subscription = SubscriptionV1Alpha1(
        subscription_id="priority_attention",
        product_id=PRODUCT_ID,
        persona_binding_ref=str(binding.binding_ref),
        monitor_refs=(str(monitor.monitor_ref),),
        signal_types=("material_attention",),
        brief_template_ids=("orientation_brief",),
        minimum_confidence=0.7,
        delivery=SubscriptionDeliveryDisposition.RECORD_ONLY,
    )
    return monitor, binding, subscription


def _target(target: MonitorV1Alpha1 | SubscriptionV1Alpha1) -> ExactMaterialReferenceV1Alpha1:
    if isinstance(target, MonitorV1Alpha1):
        return ExactMaterialReferenceV1Alpha1(
            reference=str(target.monitor_ref),
            digest=str(target.monitor_digest),
        )
    return ExactMaterialReferenceV1Alpha1(
        reference=str(target.subscription_ref),
        digest=str(target.subscription_digest),
    )


def _binding_ref(binding: PersonaBindingV1Alpha1) -> ExactMaterialReferenceV1Alpha1:
    return ExactMaterialReferenceV1Alpha1(
        reference=str(binding.binding_ref),
        digest=str(binding.binding_digest),
    )


def _lifecycle_request(
    *,
    key: str,
    target: MonitorV1Alpha1 | SubscriptionV1Alpha1,
    binding: PersonaBindingV1Alpha1,
    action: MonitoringLifecycleAction,
    sequence: int,
    at: datetime,
    prior=None,
    auth: AuthenticatedRuntimeContextV1Alpha1 | None = None,
) -> MonitoringLifecycleRequestV1Alpha1:
    return MonitoringLifecycleRequestV1Alpha1(
        transition_key=f"monitoring_transition:{key}",
        product_id=PRODUCT_ID,
        authenticated_context=auth or _auth(),
        target_kind=(
            MonitoringTargetKind.MONITOR if isinstance(target, MonitorV1Alpha1) else MonitoringTargetKind.SUBSCRIPTION
        ),
        target=_target(target),
        persona_binding=_binding_ref(binding),
        action=action,
        sequence=sequence,
        prior_receipt=prior.reference() if prior is not None else None,
        requested_at=at,
    )


def _material(name: str, digit: str) -> ExactMaterialReferenceV1Alpha1:
    return ExactMaterialReferenceV1Alpha1(
        reference=f"{name}:one",
        digest="sha256:" + digit * 64,
    )


async def _created_intents(store: InMemoryImmutableRecordStore):
    monitor, binding, subscription = _intent()
    lifecycle = MonitoringLifecycleService(store=store)
    monitor_create = await lifecycle.transition(
        request=_lifecycle_request(
            key="monitor-create",
            target=monitor,
            binding=binding,
            action=MonitoringLifecycleAction.CREATE,
            sequence=1,
            at=BASE + timedelta(minutes=1),
        ),
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=1),
    )
    subscription_create = await lifecycle.transition(
        request=_lifecycle_request(
            key="subscription-create",
            target=subscription,
            binding=binding,
            action=MonitoringLifecycleAction.CREATE,
            sequence=1,
            at=BASE + timedelta(minutes=1),
        ),
        persona_binding=binding,
        target=subscription,
        applied_at=BASE + timedelta(minutes=1),
    )
    return lifecycle, monitor, binding, subscription, monitor_create, subscription_create


@pytest.mark.asyncio
async def test_owner_lifecycle_is_append_only_exact_and_restart_replayable() -> None:
    store = InMemoryImmutableRecordStore()
    lifecycle, monitor, binding, _, created, _ = await _created_intents(store)
    pause_request = _lifecycle_request(
        key="monitor-pause",
        target=monitor,
        binding=binding,
        action=MonitoringLifecycleAction.PAUSE,
        sequence=2,
        prior=created.receipt,
        at=BASE + timedelta(minutes=10),
    )
    paused = await lifecycle.transition(
        request=pause_request,
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=10),
    )
    resumed = await lifecycle.transition(
        request=_lifecycle_request(
            key="monitor-resume",
            target=monitor,
            binding=binding,
            action=MonitoringLifecycleAction.RESUME,
            sequence=3,
            prior=paused.receipt,
            at=BASE + timedelta(minutes=20),
        ),
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=20),
    )

    replay = await MonitoringLifecycleService(store=store).transition(
        request=pause_request,
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=10),
    )
    assert created.receipt.state_after is MonitoringLifecycleState.ACTIVE
    assert paused.receipt.state_after is MonitoringLifecycleState.PAUSED
    assert resumed.receipt.state_after is MonitoringLifecycleState.ACTIVE
    assert paused.receipt.prior_receipt == created.receipt.reference()
    assert replay.receipt == paused.receipt
    assert replay.replayed is True


@pytest.mark.asyncio
async def test_lifecycle_rejects_non_owner_divergent_replay_and_terminal_resume() -> None:
    store = InMemoryImmutableRecordStore()
    lifecycle, monitor, binding, subscription, monitor_created, subscription_created = await _created_intents(store)
    with pytest.raises(MonitoringLifecycleError, match="bound owner"):
        await lifecycle.transition(
            request=_lifecycle_request(
                key="not-owner",
                target=monitor,
                binding=binding,
                action=MonitoringLifecycleAction.PAUSE,
                sequence=2,
                prior=monitor_created.receipt,
                at=BASE + timedelta(minutes=5),
                auth=_auth(actor="principal:other"),
            ),
            persona_binding=binding,
            target=monitor,
            applied_at=BASE + timedelta(minutes=5),
        )

    original = _lifecycle_request(
        key="stable-pause",
        target=monitor,
        binding=binding,
        action=MonitoringLifecycleAction.PAUSE,
        sequence=2,
        prior=monitor_created.receipt,
        at=BASE + timedelta(minutes=6),
    )
    await lifecycle.transition(
        request=original,
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=6),
    )
    with pytest.raises(MonitoringLifecycleReplayConflict):
        await lifecycle.transition(
            request=original,
            persona_binding=binding,
            target=monitor,
            applied_at=BASE + timedelta(minutes=6, seconds=1),
        )
    with pytest.raises(MonitoringLifecycleError, match="append failed"):
        await lifecycle.transition(
            request=_lifecycle_request(
                key="competing-monitor-revoke",
                target=monitor,
                binding=binding,
                action=MonitoringLifecycleAction.REVOKE,
                sequence=2,
                prior=monitor_created.receipt,
                at=BASE + timedelta(minutes=6, seconds=2),
            ),
            persona_binding=binding,
            target=monitor,
            applied_at=BASE + timedelta(minutes=6, seconds=2),
        )

    revoked = await lifecycle.transition(
        request=_lifecycle_request(
            key="subscription-revoke",
            target=subscription,
            binding=binding,
            action=MonitoringLifecycleAction.REVOKE,
            sequence=2,
            prior=subscription_created.receipt,
            at=BASE + timedelta(minutes=7),
        ),
        persona_binding=binding,
        target=subscription,
        applied_at=BASE + timedelta(minutes=7),
    )
    with pytest.raises(MonitoringLifecycleError, match="not allowed"):
        await lifecycle.transition(
            request=_lifecycle_request(
                key="subscription-resume-after-revoke",
                target=subscription,
                binding=binding,
                action=MonitoringLifecycleAction.RESUME,
                sequence=3,
                prior=revoked.receipt,
                at=BASE + timedelta(minutes=8),
            ),
            persona_binding=binding,
            target=subscription,
            applied_at=BASE + timedelta(minutes=8),
        )
    with pytest.raises(MonitoringLifecycleError, match="append failed"):
        await lifecycle.transition(
            request=_lifecycle_request(
                key="subscription-recreate-after-revoke",
                target=subscription,
                binding=binding,
                action=MonitoringLifecycleAction.CREATE,
                sequence=1,
                at=BASE + timedelta(minutes=9),
            ),
            persona_binding=binding,
            target=subscription,
            applied_at=BASE + timedelta(minutes=9),
        )


def _window_request(*, key: str, monitor, subscription, at: datetime) -> SensingWindowRequestV1Alpha1:
    return SensingWindowRequestV1Alpha1(
        window_key=f"sensing_window:{key}",
        product_id=PRODUCT_ID,
        authenticated_context=_auth(),
        monitor_lifecycle=monitor.receipt.reference(),
        subscription_lifecycle=subscription.receipt.reference(),
        requested_at=at,
        window_started_at=at,
        window_ended_at=at + timedelta(minutes=1),
    )


def _evaluation(
    request: SensingWindowRequestV1Alpha1,
    *,
    disposition: SensingWindowDisposition,
    reason: SensingWindowSuppressionReason | None,
    kind: SensingWindowMaterialKind,
    accepted=(),
    replayed=(),
    routed=(),
    acquisitions=(),
    transactions=(),
    correction_visible: bool = False,
) -> SensingWindowEvaluationV1Alpha1:
    return SensingWindowEvaluationV1Alpha1(
        request=request.reference(),
        acquisition_requests=acquisitions,
        source_transactions=transactions,
        accepted_resources=accepted,
        replayed_resources=replayed,
        routed_resources=routed,
        material_kind=kind,
        disposition=disposition,
        suppression_reason=reason,
        correction_visible=correction_visible,
        evaluated_at=request.window_ended_at,
    )


@pytest.mark.asyncio
async def test_sensing_windows_route_suppress_and_replay_without_effect_authority() -> None:
    store = InMemoryImmutableRecordStore()
    _, _, _, _, monitor_created, subscription_created = await _created_intents(store)
    service = SensingWindowService(store=store)

    routed_request = _window_request(
        key="initial",
        monitor=monitor_created,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=2),
    )
    accepted = _material("observation", "c")
    routed = await service.record(
        request=routed_request,
        evaluation=_evaluation(
            routed_request,
            disposition=SensingWindowDisposition.ROUTED,
            reason=None,
            kind=SensingWindowMaterialKind.MATERIAL_CHANGE,
            acquisitions=(_material("acquisition_request", "d"),),
            transactions=(_material("source_transaction", "e"),),
            accepted=(accepted,),
            routed=(accepted,),
        ),
    )
    no_change_request = _window_request(
        key="no-change",
        monitor=monitor_created,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=4),
    )
    replayed_material = _material("observation", "f")
    no_change_evaluation = _evaluation(
        no_change_request,
        disposition=SensingWindowDisposition.SUPPRESSED,
        reason=SensingWindowSuppressionReason.NO_MATERIAL_CHANGE,
        kind=SensingWindowMaterialKind.NONE,
        acquisitions=(_material("acquisition_request", "1"),),
        transactions=(_material("source_transaction", "2"),),
        replayed=(replayed_material,),
    )
    no_change = await service.record(request=no_change_request, evaluation=no_change_evaluation)
    reopened = await SensingWindowService(store=store).record(
        request=no_change_request,
        evaluation=no_change_evaluation,
    )

    assert routed.receipt.disposition is SensingWindowDisposition.ROUTED
    assert no_change.receipt.suppression_reason is SensingWindowSuppressionReason.NO_MATERIAL_CHANGE
    assert no_change.receipt.scheduler_authority is False
    assert no_change.receipt.delivery_authority is False
    assert no_change.receipt.external_action_authority is False
    assert reopened.receipt == no_change.receipt
    assert reopened.replayed is True

    false_guard_request = _window_request(
        key="false-active-guard",
        monitor=monitor_created,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=6),
    )
    with pytest.raises(SensingWindowError, match="guards"):
        await service.record(
            request=false_guard_request,
            evaluation=_evaluation(
                false_guard_request,
                disposition=SensingWindowDisposition.SUPPRESSED,
                reason=SensingWindowSuppressionReason.OWNER_PAUSED,
                kind=SensingWindowMaterialKind.NONE,
            ),
        )


@pytest.mark.asyncio
async def test_pause_and_revocation_prove_zero_acquisition_before_adapter_use() -> None:
    store = InMemoryImmutableRecordStore()
    lifecycle, monitor, binding, subscription, monitor_created, subscription_created = await _created_intents(store)
    paused = await lifecycle.transition(
        request=_lifecycle_request(
            key="pause-before-window",
            target=monitor,
            binding=binding,
            action=MonitoringLifecycleAction.PAUSE,
            sequence=2,
            prior=monitor_created.receipt,
            at=BASE + timedelta(minutes=5),
        ),
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=5),
    )
    paused_request = _window_request(
        key="paused",
        monitor=paused,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=6),
    )
    paused_evaluation = _evaluation(
        paused_request,
        disposition=SensingWindowDisposition.SUPPRESSED,
        reason=SensingWindowSuppressionReason.OWNER_PAUSED,
        kind=SensingWindowMaterialKind.NONE,
    )
    paused_receipt = await SensingWindowService(store=store).record(
        request=paused_request,
        evaluation=paused_evaluation,
    )
    assert paused_receipt.receipt.acquisition_requests == ()
    assert paused_receipt.receipt.source_transactions == ()

    stale_request = _window_request(
        key="stale-active-after-pause",
        monitor=monitor_created,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=6),
    )
    with pytest.raises(SensingWindowError, match="stale"):
        await SensingWindowService(store=store).record(
            request=stale_request,
            evaluation=_evaluation(
                stale_request,
                disposition=SensingWindowDisposition.SUPPRESSED,
                reason=SensingWindowSuppressionReason.NO_MATERIAL_CHANGE,
                kind=SensingWindowMaterialKind.NONE,
                replayed=(_material("observation", "0"),),
            ),
        )

    invalid_paused_evaluation = paused_evaluation.model_copy(
        update={"acquisition_requests": (_material("acquisition_request", "3"),)}
    )
    with pytest.raises(SensingWindowError, match="revalidation"):
        await SensingWindowService(store=store).record(
            request=SensingWindowRequestV1Alpha1(
                **paused_request.model_dump(mode="python", exclude={"window_key", "request_id", "request_digest"}),
                window_key="sensing_window:paused-with-acquisition",
            ),
            evaluation=invalid_paused_evaluation.model_copy(
                update={
                    "request": SensingWindowRequestV1Alpha1(
                        **paused_request.model_dump(
                            mode="python",
                            exclude={"window_key", "request_id", "request_digest"},
                        ),
                        window_key="sensing_window:paused-with-acquisition",
                    ).reference()
                }
            ),
        )

    resumed = await lifecycle.transition(
        request=_lifecycle_request(
            key="resume-before-revocation",
            target=monitor,
            binding=binding,
            action=MonitoringLifecycleAction.RESUME,
            sequence=3,
            prior=paused.receipt,
            at=BASE + timedelta(minutes=7),
        ),
        persona_binding=binding,
        target=monitor,
        applied_at=BASE + timedelta(minutes=7),
    )
    revoked = await lifecycle.transition(
        request=_lifecycle_request(
            key="revoke-before-window",
            target=subscription,
            binding=binding,
            action=MonitoringLifecycleAction.REVOKE,
            sequence=2,
            prior=subscription_created.receipt,
            at=BASE + timedelta(minutes=8),
        ),
        persona_binding=binding,
        target=subscription,
        applied_at=BASE + timedelta(minutes=8),
    )
    revoked_request = _window_request(
        key="revoked",
        monitor=resumed,
        subscription=revoked,
        at=BASE + timedelta(minutes=9),
    )
    revoked_receipt = await SensingWindowService(store=store).record(
        request=revoked_request,
        evaluation=_evaluation(
            revoked_request,
            disposition=SensingWindowDisposition.SUPPRESSED,
            reason=SensingWindowSuppressionReason.SUBSCRIPTION_REVOKED,
            kind=SensingWindowMaterialKind.NONE,
        ),
    )
    assert revoked_receipt.receipt.suppression_reason is SensingWindowSuppressionReason.SUBSCRIPTION_REVOKED
    assert revoked_receipt.receipt.accepted_resources == ()


@pytest.mark.parametrize(
    ("target_name", "action", "reason"),
    [
        (
            "monitor",
            MonitoringLifecycleAction.REVOKE,
            SensingWindowSuppressionReason.MONITOR_REVOKED,
        ),
        (
            "subscription",
            MonitoringLifecycleAction.PAUSE,
            SensingWindowSuppressionReason.SUBSCRIPTION_PAUSED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_every_non_active_lifecycle_state_has_an_exact_zero_acquisition_guard(
    target_name: str,
    action: MonitoringLifecycleAction,
    reason: SensingWindowSuppressionReason,
) -> None:
    store = InMemoryImmutableRecordStore()
    lifecycle, monitor, binding, subscription, monitor_created, subscription_created = await _created_intents(store)
    target = monitor if target_name == "monitor" else subscription
    prior = monitor_created if target_name == "monitor" else subscription_created
    advanced = await lifecycle.transition(
        request=_lifecycle_request(
            key=f"{target_name}-{action.value}-guard",
            target=target,
            binding=binding,
            action=action,
            sequence=2,
            prior=prior.receipt,
            at=BASE + timedelta(minutes=5),
        ),
        persona_binding=binding,
        target=target,
        applied_at=BASE + timedelta(minutes=5),
    )
    request = _window_request(
        key=f"{target_name}-{action.value}",
        monitor=advanced if target_name == "monitor" else monitor_created,
        subscription=advanced if target_name == "subscription" else subscription_created,
        at=BASE + timedelta(minutes=6),
    )
    admission = await SensingWindowService(store=store).record(
        request=request,
        evaluation=_evaluation(
            request,
            disposition=SensingWindowDisposition.SUPPRESSED,
            reason=reason,
            kind=SensingWindowMaterialKind.NONE,
        ),
    )
    assert admission.receipt.suppression_reason is reason
    assert admission.receipt.acquisition_requests == ()


@pytest.mark.asyncio
async def test_corrections_are_always_visible_and_window_keys_fail_closed() -> None:
    store = InMemoryImmutableRecordStore()
    _, _, _, _, monitor_created, subscription_created = await _created_intents(store)
    request = _window_request(
        key="correction",
        monitor=monitor_created,
        subscription=subscription_created,
        at=BASE + timedelta(minutes=3),
    )
    corrected = _material("observation", "4")
    evaluation = _evaluation(
        request,
        disposition=SensingWindowDisposition.ROUTED,
        reason=None,
        kind=SensingWindowMaterialKind.CORRECTION,
        acquisitions=(_material("acquisition_request", "5"),),
        transactions=(_material("source_transaction", "6"),),
        accepted=(corrected,),
        routed=(corrected,),
        correction_visible=True,
    )
    first = await SensingWindowService(store=store).record(request=request, evaluation=evaluation)
    assert first.receipt.correction_visible is True

    with pytest.raises(ValidationError, match="visibly routed"):
        _evaluation(
            request,
            disposition=SensingWindowDisposition.SUPPRESSED,
            reason=SensingWindowSuppressionReason.NO_MATERIAL_CHANGE,
            kind=SensingWindowMaterialKind.CORRECTION,
            replayed=(corrected,),
        )

    divergent = SensingWindowEvaluationV1Alpha1(
        **evaluation.model_dump(mode="python", exclude={"evaluated_at"}),
        evaluated_at=evaluation.evaluated_at + timedelta(seconds=1),
    )
    with pytest.raises(SensingWindowReplayConflict):
        await SensingWindowService(store=store).record(request=request, evaluation=divergent)


def test_contracts_fail_closed_on_sequence_time_and_extra_authority() -> None:
    monitor, binding, _ = _intent()
    with pytest.raises(ValidationError, match="first monitoring transition"):
        _lifecycle_request(
            key="bad-first",
            target=monitor,
            binding=binding,
            action=MonitoringLifecycleAction.PAUSE,
            sequence=1,
            at=BASE + timedelta(minutes=1),
        )
    with pytest.raises(ValidationError, match="positive interval"):
        SensingWindowRequestV1Alpha1(
            window_key="sensing_window:bad-time",
            product_id=PRODUCT_ID,
            authenticated_context=_auth(),
            monitor_lifecycle=_material("monitoring_lifecycle", "7"),
            subscription_lifecycle=_material("monitoring_lifecycle", "8"),
            requested_at=BASE + timedelta(minutes=1),
            window_started_at=BASE + timedelta(minutes=2),
            window_ended_at=BASE + timedelta(minutes=2),
        )
    with pytest.raises(ValidationError):
        SensingWindowRequestV1Alpha1(
            window_key="sensing_window:extra-authority",
            product_id=PRODUCT_ID,
            authenticated_context=_auth(),
            monitor_lifecycle=_material("monitoring_lifecycle", "7"),
            subscription_lifecycle=_material("monitoring_lifecycle", "8"),
            requested_at=BASE + timedelta(minutes=1),
            window_started_at=BASE + timedelta(minutes=1),
            window_ended_at=BASE + timedelta(minutes=2),
            scheduler_authority=True,
        )
    duplicate_request = SensingWindowRequestV1Alpha1(
        window_key="sensing_window:duplicate-reference",
        product_id=PRODUCT_ID,
        authenticated_context=_auth(),
        monitor_lifecycle=_material("monitoring_lifecycle", "7"),
        subscription_lifecycle=_material("monitoring_lifecycle", "8"),
        requested_at=BASE + timedelta(minutes=1),
        window_started_at=BASE + timedelta(minutes=1),
        window_ended_at=BASE + timedelta(minutes=2),
    )
    with pytest.raises(ValidationError, match="at most once"):
        _evaluation(
            duplicate_request,
            disposition=SensingWindowDisposition.SUPPRESSED,
            reason=SensingWindowSuppressionReason.NO_MATERIAL_CHANGE,
            kind=SensingWindowMaterialKind.NONE,
            replayed=(
                _material("observation", "9"),
                _material("observation", "a"),
            ),
        )
