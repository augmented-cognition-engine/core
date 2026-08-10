from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core import (
    ACTION_RECORD_SPACE,
    ActionDisposition,
    ActionEffectState,
    ActionIntentV1Alpha1,
    ActionPromotionDisposition,
    ActionResultV1Alpha1,
    ActionReversibility,
    ActionReviewDisposition,
    ActionVerificationDisposition,
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    DecisionActionDisposition,
    DecisionDisposition,
    DecisionIntentV1Alpha1,
    DecisionV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedActionExecutionError,
    GovernedActionExecutionService,
    GovernedActionReplayConflict,
    GovernedActionReviewError,
    GovernedActionReviewReplayConflict,
    GovernedActionReviewService,
    GovernedOperationBindingV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordV1,
    PreparedActionV1Alpha1,
    ReceiptReferenceV1Alpha1,
    canonical_hash,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)
PRODUCT = "product:action"
ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="bounded_action_execution",
    contract="ace.core.action-adapter/v1alpha1",
    implementation_id="fixture_action_adapter",
    implementation_version="0.1.0",
    artifact_digest="sha256:" + "a" * 64,
)


def _head(kind: str, state_id: str, sequence: int) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=f"revision:{kind}:{sequence}",
        commit_receipt_id=f"governed_state_commit:{kind}:{sequence}",
        updated_at=NOW,
    )


CONFIG_HEAD = _head("governed_operation_configuration", "governed_operation_configuration:action", 1)
CAPABILITY_HEAD = _head("capability_state", "capability_state:action", 2)
AUTHORITY_HEAD = _head("authority_grant", "authority_grant:action", 3)
PRECONDITIONS = tuple(
    GovernedStateHeadPreconditionV1Alpha1.from_head(head) for head in (CONFIG_HEAD, CAPABILITY_HEAD, AUTHORITY_HEAD)
)


def _context(actor: str = "principal:operator") -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=actor,
        authentication_receipt_ref="authentication:session",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
    )


def _authorization(at: datetime = NOW + timedelta(seconds=2)) -> GovernedActionAuthorizationProjection:
    return GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id="authorization:action",
            receipt_digest="sha256:" + "c" * 64,
        ),
        authorized_at=at,
        state_preconditions=PRECONDITIONS,
    )


def _binding(artifact: CapabilityArtifactIdentityV1Alpha1 = ARTIFACT) -> GovernedOperationBindingV1Alpha1:
    return GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=artifact,
        configuration_ref=CONFIG_HEAD.state_id,
        authority="execute_action",
        grant_ref=AUTHORITY_HEAD.state_id,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(CONFIG_HEAD),
    )


class _Store(InMemoryImmutableRecordStore):
    def __init__(self) -> None:
        super().__init__(
            governed_state_heads={
                (head.state_kind, head.product_id, head.state_id): head
                for head in (CONFIG_HEAD, CAPABILITY_HEAD, AUTHORITY_HEAD)
            }
        )
        self.admitted = False

    async def append(self, request):
        receipt = await super().append(request)
        if request.records[0].record_kind == "action_admission":
            self.admitted = True
        return receipt


class _FailTerminalOnceStore(_Store):
    def __init__(self) -> None:
        super().__init__()
        self.fail_terminal = True

    async def append(self, request):
        if request.records[0].record_kind == "action_terminal" and self.fail_terminal:
            self.fail_terminal = False
            raise ImmutableRecordPersistenceError("simulated terminal interruption")
        return await super().append(request)


class _Authorizer:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.requests = []

    async def authorize_action(self, request):
        self.requests.append(request)
        if self.deny:
            raise PermissionError("denied")
        return _authorization()


class _Adapter:
    artifact_identity = ARTIFACT

    def __init__(self, store: _Store, *, mode: str = "success", timeout: float = 1.0) -> None:
        self.store = store
        self.mode = mode
        self.timeout = timeout
        self.prepare_calls = 0
        self.execute_calls = 0

    async def prepare(self, intent):
        self.prepare_calls += 1
        return PreparedActionV1Alpha1(
            product_id=intent.product_id,
            intent_id=intent.intent_id,
            intent_digest=intent.intent_digest,
            artifact=self.artifact_identity,
            action_type=intent.action_type,
            target_ref="workspace:file:report.md",
            target_digest="sha256:" + "d" * 64,
            required_permissions=("workspace.write",),
            declared_side_effects=("modify_file",),
            reversibility=ActionReversibility.REVERSIBLE,
            timeout_seconds=self.timeout,
            prepared_at=NOW + timedelta(seconds=1),
        )

    async def execute(self, plan, authorization):
        self.execute_calls += 1
        assert self.store.admitted is True
        if self.mode == "raise":
            raise RuntimeError("private adapter detail")
        if self.mode == "slow":
            await asyncio.sleep(0.05)
        if self.mode == "block":
            await asyncio.sleep(60)
        if self.mode == "partial":
            return ActionResultV1Alpha1(
                disposition=ActionDisposition.PARTIAL,
                effect_state=ActionEffectState.CONFIRMED,
                result_json='{"files_changed":1}',
                failure_code="verification_failed",
                failure_message="One declared verification did not pass.",
                completed_at=NOW + timedelta(seconds=4),
            )
        return ActionResultV1Alpha1(
            disposition=ActionDisposition.SUCCEEDED,
            effect_state=ActionEffectState.CONFIRMED,
            result_json='{"files_changed":1}',
            completed_at=NOW + timedelta(seconds=4),
        )


class _Clock:
    def __init__(self) -> None:
        self.value = NOW + timedelta(seconds=3)

    def __call__(self):
        value = self.value
        self.value += timedelta(seconds=1)
        return value


async def _seed_decision(store: _Store, *, action_type: str = "write_report", actor: str = "principal:operator"):
    subject_record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="brief",
        record_key="brief:1",
        payload_contract="fixture/brief-v1",
        payload={"title": "fixture"},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=2),
        processing_order=0,
    )
    decision_intent = DecisionIntentV1Alpha1(
        product_id=PRODUCT,
        authenticated_context=_context(actor),
        subject=subject_record.reference(),
        actor_role_ref="persona:operator",
        decision_type="direction",
        disposition=DecisionDisposition.ACCEPT,
        action_disposition=DecisionActionDisposition.AUTHORIZE_ACTION,
        action_type=action_type,
        rationale="Approve the bounded fixture action.",
        decided_at=NOW - timedelta(minutes=1),
    )
    decision = DecisionV1Alpha1(intent=decision_intent, authorization=_authorization(NOW))
    decision_record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="decision",
        record_key=str(decision.decision_id),
        payload_contract=decision.contract,
        payload=decision.model_dump(mode="python"),
        as_of=decision_intent.decided_at,
        available_at=NOW,
        processing_order=0,
    )
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="prepared",
        transaction_key=f"seed:{decision.decision_id}",
        records=(decision_record,),
        submitted_at=NOW,
        governed_state_preconditions=PRECONDITIONS,
    )
    await store.append(request)
    return decision_record.reference()


async def _intent(store: _Store, **updates) -> ActionIntentV1Alpha1:
    decision = await _seed_decision(
        store,
        action_type=updates.pop("decision_action_type", "write_report"),
        actor=updates.get("actor", "principal:operator"),
    )
    actor = updates.pop("actor", "principal:operator")
    values = {
        "action_key": "action:fixture:1",
        "product_id": PRODUCT,
        "authenticated_context": _context(actor),
        "decision": decision,
        "action_type": "write_report",
        "parameters_json": '{"format":"markdown"}',
        "requested_at": NOW,
    }
    values.update(updates)
    return ActionIntentV1Alpha1(**values)


def _service(store: _Store, adapter: _Adapter, authorizer: _Authorizer | None = None):
    return GovernedActionExecutionService(
        store=store,
        authorizer=authorizer or _Authorizer(),
        operation_binding=_binding(),
        adapter=adapter,
        clock=_Clock(),
    )


def _review_service(store: _Store, adapter: _Adapter, *, clock: _Clock | None = None):
    return GovernedActionReviewService(
        store=store,
        executor=_service(store, adapter),
        clock=clock or _Clock(),
    )


@pytest.mark.asyncio
async def test_success_is_admitted_before_effect_and_replays_without_reexecution():
    store = _Store()
    intent = await _intent(store)
    adapter = _Adapter(store)
    service = _service(store, adapter)

    first = await service.execute(intent)
    replay = await service.execute(intent)

    assert first.result.disposition is ActionDisposition.SUCCEEDED
    assert first.result.effect_state is ActionEffectState.CONFIRMED
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.terminal == first.terminal
    assert adapter.prepare_calls == 1
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_calls_converge_before_adapter_execution():
    store = _Store()
    intent = await _intent(store)
    adapter = _Adapter(store)
    service = _service(store, adapter)

    first, second = await asyncio.gather(service.execute(intent), service.execute(intent))

    assert first.terminal == second.terminal
    assert {first.replayed, second.replayed} == {False, True}
    assert adapter.prepare_calls == 1
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_reused_action_key_with_different_material_fails_closed():
    store = _Store()
    intent = await _intent(store)
    service = _service(store, _Adapter(store))
    await service.execute(intent)
    changed = ActionIntentV1Alpha1.model_validate(
        {
            **intent.model_dump(mode="python", exclude={"intent_id", "intent_digest"}),
            "parameters_json": '{"format":"html"}',
        }
    )

    with pytest.raises(GovernedActionReplayConflict, match="different intent"):
        await service.execute(changed)


@pytest.mark.asyncio
async def test_denied_authorization_never_executes_or_admits():
    store = _Store()
    intent = await _intent(store)
    adapter = _Adapter(store)
    service = _service(store, adapter, _Authorizer(deny=True))

    with pytest.raises(GovernedActionExecutionError, match="authorization failed"):
        await service.execute(intent)

    assert adapter.execute_calls == 0
    assert store.admitted is False


@pytest.mark.asyncio
async def test_decision_must_authorize_exact_action_type():
    store = _Store()
    intent = await _intent(store, decision_action_type="publish_report")
    adapter = _Adapter(store)

    with pytest.raises(GovernedActionExecutionError, match="does not authorize"):
        await _service(store, adapter).execute(intent)

    assert adapter.prepare_calls == 0


@pytest.mark.asyncio
async def test_partial_effect_is_never_reported_as_success():
    store = _Store()
    outcome = await _service(store, _Adapter(store, mode="partial")).execute(await _intent(store))

    assert outcome.result.disposition is ActionDisposition.PARTIAL
    assert outcome.result.failure_code == "verification_failed"
    assert outcome.result.effect_state is ActionEffectState.CONFIRMED


@pytest.mark.asyncio
async def test_adapter_exception_is_bounded_and_effect_unknown():
    store = _Store()
    outcome = await _service(store, _Adapter(store, mode="raise")).execute(await _intent(store))

    assert outcome.result.disposition is ActionDisposition.FAILED
    assert outcome.result.effect_state is ActionEffectState.UNKNOWN
    assert outcome.result.failure_code == "adapter_failed"
    assert "private" not in outcome.result.failure_message


@pytest.mark.asyncio
async def test_timeout_is_degraded_and_effect_unknown():
    store = _Store()
    outcome = await _service(store, _Adapter(store, mode="slow", timeout=0.001)).execute(await _intent(store))

    assert outcome.result.disposition is ActionDisposition.DEGRADED
    assert outcome.result.effect_state is ActionEffectState.UNKNOWN
    assert outcome.result.failure_code == "timed_out"


@pytest.mark.asyncio
async def test_cooperative_cancellation_persists_non_success_terminal():
    store = _Store()
    intent = await _intent(store)
    adapter = _Adapter(store, mode="block", timeout=120)
    service = _service(store, adapter)
    running = asyncio.create_task(service.execute(intent))
    while adapter.execute_calls == 0:
        await asyncio.sleep(0)
    running.cancel()

    with pytest.raises(asyncio.CancelledError):
        await running
    replay = await service.execute(intent)

    assert replay.replayed is True
    assert replay.result.disposition is ActionDisposition.CANCELLED
    assert replay.result.effect_state is ActionEffectState.UNKNOWN
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_restart_orphan_is_not_reexecuted_and_becomes_effect_unknown():
    store = _FailTerminalOnceStore()
    intent = await _intent(store)
    first_adapter = _Adapter(store)
    with pytest.raises(ImmutableRecordPersistenceError):
        await _service(store, first_adapter).execute(intent)
    assert first_adapter.execute_calls == 1

    restarted_adapter = _Adapter(store)
    restarted = await _service(store, restarted_adapter).execute(intent)

    assert restarted.replayed is True
    assert restarted.result.disposition is ActionDisposition.DEGRADED
    assert restarted.result.effect_state is ActionEffectState.UNKNOWN
    assert restarted.result.failure_code == "runtime_restarted"
    assert restarted_adapter.prepare_calls == 0
    assert restarted_adapter.execute_calls == 0


def test_secret_shaped_parameters_fail_contract_validation():
    with pytest.raises(ValidationError, match="credential-shaped"):
        ActionIntentV1Alpha1(
            action_key="action:fixture:secret",
            product_id=PRODUCT,
            authenticated_context=_context(),
            decision=ImmutableRecordV1(
                product_id=PRODUCT,
                record_space="prepared",
                record_kind="decision",
                record_key="decision:fixture",
                payload_contract="fixture/decision-v1",
                payload={},
                as_of=NOW,
                available_at=NOW,
                processing_order=0,
            ).reference(),
            action_type="write_report",
            parameters_json='{"api_key":"nope"}',
            requested_at=NOW,
        )


def test_adapter_must_match_exact_governed_binding():
    store = _Store()
    other = CapabilityArtifactIdentityV1Alpha1.model_validate(
        {**ARTIFACT.model_dump(mode="python"), "implementation_version": "0.2.0"}
    )
    adapter = _Adapter(store)
    adapter.artifact_identity = other

    with pytest.raises(GovernedActionExecutionError, match="does not match"):
        GovernedActionExecutionService(
            store=store,
            authorizer=_Authorizer(),
            operation_binding=_binding(),
            adapter=adapter,
            clock=_Clock(),
        )


def test_non_success_result_requires_explicit_failure():
    with pytest.raises(ValidationError, match="explicit bounded failure"):
        ActionResultV1Alpha1(
            disposition=ActionDisposition.FAILED,
            effect_state=ActionEffectState.NONE,
            completed_at=NOW,
        )


def test_action_record_space_remains_domain_neutral():
    assert ACTION_RECORD_SPACE == "action_execution"
    assert canonical_hash({"space": ACTION_RECORD_SPACE})


@pytest.mark.asyncio
async def test_exact_human_review_survives_reconstruction_and_executes_once():
    store = _Store()
    intent = await _intent(store)
    adapter = _Adapter(store)
    first_service = _review_service(store, adapter)

    prepared = await first_service.prepare_for_review(intent)
    review = await first_service.review(
        prepared,
        review_key="review:fixture:1",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.APPROVE,
        rationale="The exact target, permissions, and declared effect are approved.",
    )

    assert adapter.prepare_calls == 1
    assert adapter.execute_calls == 0
    assert store.admitted is False

    restarted = _review_service(store, adapter)
    first = await restarted.execute_reviewed(review)
    replay = await restarted.execute_reviewed(review)

    assert first.admission.plan == review.plan
    assert first.admission.authorization == review.authorization
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.terminal == first.terminal
    assert adapter.prepare_calls == 1
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_rejected_review_is_durable_and_never_admits_or_executes():
    store = _Store()
    adapter = _Adapter(store)
    service = _review_service(store, adapter)
    review = await service.review(
        await service.prepare_for_review(await _intent(store)),
        review_key="review:fixture:rejected",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.REJECT,
        rationale="The target is not approved for this run.",
    )

    with pytest.raises(GovernedActionReviewError, match="rejected"):
        await service.execute_reviewed(review)

    assert store.admitted is False
    assert adapter.execute_calls == 0


@pytest.mark.asyncio
async def test_review_cannot_be_added_after_action_admission():
    store = _Store()
    adapter = _Adapter(store)
    intent = await _intent(store)
    await _service(store, adapter).execute(intent)

    with pytest.raises(GovernedActionReviewError, match="already admitted"):
        await _review_service(store, adapter).prepare_for_review(intent)


@pytest.mark.asyncio
async def test_expired_or_cross_product_reviewer_fails_before_review_persistence():
    store = _Store()
    service = _review_service(store, _Adapter(store))
    prepared = await service.prepare_for_review(await _intent(store))
    expired = AuthenticatedRuntimeContextV1Alpha1.model_validate(
        {
            **_context("principal:reviewer").model_dump(mode="python"),
            "expires_at": NOW + timedelta(seconds=3),
        }
    )

    with pytest.raises(ValidationError, match="reviewer, or product scope"):
        await service.review(
            prepared,
            review_key="review:fixture:expired",
            reviewer_context=expired,
            disposition=ActionReviewDisposition.APPROVE,
            rationale="This expired authenticated window must fail closed.",
        )


@pytest.mark.asyncio
async def test_stable_review_key_cannot_change_human_disposition():
    store = _Store()
    service = _review_service(store, _Adapter(store))
    prepared = await service.prepare_for_review(await _intent(store))
    await service.review(
        prepared,
        review_key="review:fixture:stable",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.APPROVE,
        rationale="Approve the exact prepared material.",
    )

    with pytest.raises(GovernedActionReviewReplayConflict, match="different exact material"):
        await service.review(
            prepared,
            review_key="review:fixture:stable",
            reviewer_context=_context("principal:reviewer"),
            disposition=ActionReviewDisposition.REJECT,
            rationale="Attempt to change the already durable judgment.",
        )


@pytest.mark.asyncio
async def test_success_requires_separate_verification_before_promotion():
    store = _Store()
    adapter = _Adapter(store)
    clock = _Clock()
    service = _review_service(store, adapter, clock=clock)
    review = await service.review(
        await service.prepare_for_review(await _intent(store)),
        review_key="review:fixture:promotion",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.APPROVE,
        rationale="Approve the exact prepared export.",
    )
    outcome = await service.execute_reviewed(review)

    with pytest.raises(ValidationError, match="promotion requires"):
        from ace.core import ActionPromotionReceiptV1Alpha1, ActionVerificationReceiptV1Alpha1

        repair_required = ActionVerificationReceiptV1Alpha1(
            verification_key="verification:not-ready",
            product_id=PRODUCT,
            review=review,
            terminal=outcome.terminal,
            verifier_context=_context("principal:verifier"),
            disposition=ActionVerificationDisposition.REPAIR_REQUIRED,
            rationale="Verification has not passed.",
            verified_at=NOW + timedelta(seconds=4),
        )
        ActionPromotionReceiptV1Alpha1(
            promotion_key="promotion:too-early",
            product_id=PRODUCT,
            verification=repair_required,
            promoter_context=_context("principal:promoter"),
            disposition=ActionPromotionDisposition.PROMOTED,
            target_ref="workspace:approved",
            rationale="Must not promote before verification.",
            promoted_at=NOW + timedelta(seconds=5),
        )

    verification = await service.verify(
        review,
        outcome,
        verification_key="verification:fixture:promotion",
        verifier_context=_context("principal:verifier"),
        disposition=ActionVerificationDisposition.VERIFIED,
        rationale="The exact output and effect evidence passed verification.",
    )
    promotion = await service.promote(
        verification,
        promotion_key="promotion:fixture:1",
        promoter_context=_context("principal:promoter"),
        disposition=ActionPromotionDisposition.PROMOTED,
        target_ref="workspace:approved",
        rationale="Adopt the verified output.",
    )

    assert verification.terminal == outcome.terminal
    assert promotion.verification == verification
    assert promotion.disposition is ActionPromotionDisposition.PROMOTED


@pytest.mark.asyncio
async def test_unknown_effect_cannot_create_repair_successor():
    store = _Store()
    service = _review_service(store, _Adapter(store, mode="raise"), clock=_Clock())
    review = await service.review(
        await service.prepare_for_review(await _intent(store)),
        review_key="review:fixture:unknown",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.APPROVE,
        rationale="Approve the bounded attempt.",
    )
    outcome = await service.execute_reviewed(review)
    verification = await service.verify(
        review,
        outcome,
        verification_key="verification:fixture:unknown",
        verifier_context=_context("principal:verifier"),
        disposition=ActionVerificationDisposition.REPAIR_REQUIRED,
        rationale="The adapter failed and the effect is unknown.",
    )
    successor = await _intent(
        store,
        action_key="action:fixture:repair-unknown",
        requested_at=NOW + timedelta(seconds=5),
    )

    with pytest.raises(ValidationError, match="known effects"):
        await service.request_repair(
            verification,
            successor,
            repair_key="repair:fixture:unknown",
            requester_context=_context("principal:reviewer"),
            rationale="Must not retry an action whose effect may have happened.",
        )


@pytest.mark.asyncio
async def test_confirmed_partial_effect_can_only_create_distinct_linked_repair():
    store = _Store()
    service = _review_service(store, _Adapter(store, mode="partial"), clock=_Clock())
    review = await service.review(
        await service.prepare_for_review(await _intent(store)),
        review_key="review:fixture:partial",
        reviewer_context=_context("principal:reviewer"),
        disposition=ActionReviewDisposition.APPROVE,
        rationale="Approve the bounded attempt.",
    )
    outcome = await service.execute_reviewed(review)
    verification = await service.verify(
        review,
        outcome,
        verification_key="verification:fixture:partial",
        verifier_context=_context("principal:verifier"),
        disposition=ActionVerificationDisposition.REPAIR_REQUIRED,
        rationale="A declared verification failed after a confirmed partial effect.",
    )
    successor = await _intent(
        store,
        action_key="action:fixture:repair-partial",
        requested_at=NOW + timedelta(seconds=5),
    )
    repair = await service.request_repair(
        verification,
        successor,
        repair_key="repair:fixture:partial",
        requester_context=_context("principal:reviewer"),
        rationale="Create a separately reviewed corrective attempt.",
    )

    assert repair.verification == verification
    assert repair.successor_intent.action_key != outcome.terminal.action_key
    assert repair.successor_intent.intent_id != review.intent.intent_id

    reused_key = ActionIntentV1Alpha1.model_validate(
        {
            **successor.model_dump(mode="python", exclude={"intent_id", "intent_digest"}),
            "action_key": outcome.terminal.action_key,
        }
    )
    with pytest.raises(ValidationError, match="fresh successor"):
        await service.request_repair(
            verification,
            reused_key,
            repair_key="repair:fixture:reused-parent",
            requester_context=_context("principal:reviewer"),
            rationale="A repair must not reuse the parent action identity.",
        )
