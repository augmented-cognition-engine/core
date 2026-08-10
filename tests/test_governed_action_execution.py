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
    ActionResultV1Alpha1,
    ActionReversibility,
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
