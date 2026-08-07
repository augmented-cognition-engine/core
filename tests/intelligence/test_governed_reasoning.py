from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core import (
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    ContextBindingV1Alpha1,
    FrozenContextItemV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningError,
    GovernedReasoningOrphanedAttempt,
    GovernedReasoningReplayConflict,
    GovernedReasoningRequestV1Alpha1,
    GovernedReasoningService,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordV1,
    ProviderRouteV1Alpha1,
    ProviderStructuredOutputV1Alpha1,
    ProviderUsageV1Alpha1,
    ReasoningAcceptanceReceiptV1Alpha1,
    ReasoningExecutionBindingV1Alpha1,
    ReceiptReferenceV1Alpha1,
    canonical_hash,
    canonical_json,
    capability_state_ref_for_artifact,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
PRODUCT = "product:reasoning"
ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="structured_reasoning",
    contract="ace.core.reasoning-provider/v1alpha1",
    implementation_id="deterministic_fixture",
    implementation_version="0.1.0",
    artifact_digest="sha256:" + "a" * 64,
)
APPEND_ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="append_immutable_records",
    contract="ace.core.immutable-record-appender/v1alpha1",
    implementation_id="deterministic_append_fixture",
    implementation_version="0.1.0",
    artifact_digest="sha256:" + "f" * 64,
)


def _head(kind: str, state_id: str, *, sequence: int = 1) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=f"{kind}_revision:{sequence}",
        commit_receipt_id=f"governed_state_commit:{kind}-{sequence}",
        updated_at=NOW,
    )


CAPABILITY_HEAD = _head("capability_state", capability_state_ref_for_artifact(ARTIFACT))
AUTHORITY_HEAD = _head("authority_grant", "authority_grant:reason")
POLICY_HEAD = _head(
    "reasoning_configuration",
    "reasoning_configuration:primary",
)
APPEND_CONFIGURATION_HEAD = _head(
    "governed_operation_configuration",
    "governed_operation_configuration:append",
)
APPEND_CAPABILITY_HEAD = _head(
    "capability_state",
    capability_state_ref_for_artifact(APPEND_ARTIFACT),
)
APPEND_AUTHORITY_HEAD = _head("authority_grant", "authority_grant:append")


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:operator",
        authentication_receipt_ref="authentication:session",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


class _Runtime:
    def __init__(self) -> None:
        self.capability_calls = 0
        self.authority_calls = 0
        self.drift_capability = False
        self.drift_authority_hash = False
        self.deny_capability = False
        self.renew_authority = False

    async def resolve_capability_use(self, **kwargs):
        self.capability_calls += 1
        if self.deny_capability:
            raise RuntimeError("secret current capability denial")
        head = _head(
            "capability_state",
            capability_state_ref_for_artifact(kwargs["artifact"]),
        )
        if self.drift_capability and self.capability_calls > 1:
            head = _head("capability_state", capability_state_ref_for_artifact(ARTIFACT), sequence=2)
        return CapabilityUseReceiptV1Alpha1(
            product_id=PRODUCT,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            artifact=kwargs["artifact"],
            capability_state_ref=kwargs["capability_state_ref"],
            configuration_ref=kwargs["configuration_ref"],
            evaluated_at=kwargs["evaluated_at"],
            resolved_at=kwargs["evaluated_at"],
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(head),
        )

    async def resolve_authority_use(self, **kwargs):
        self.authority_calls += 1
        renewed = self.renew_authority and self.authority_calls > 2
        return AuthorityUseReceiptV1Alpha1(
            product_id=PRODUCT,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash=("e" if renewed or (self.drift_authority_hash and self.authority_calls > 1) else "d") * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(minutes=19 if renewed else 9),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(
                _head(
                    "authority_grant",
                    kwargs["grant_ref"],
                    sequence=2 if renewed else 1,
                )
            ),
        )


class _Provider:
    artifact_identity = ARTIFACT

    def __init__(self, *, error: Exception | None = None, invalid: bool = False) -> None:
        self.calls = 0
        self.error = error
        self.invalid = invalid

    async def execute(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.invalid:
            return {"not": "a contract"}
        return ProviderStructuredOutputV1Alpha1(
            route=ProviderRouteV1Alpha1(
                provider_id="fixture",
                model_id="deterministic",
                model_version="1",
                configuration_digest="sha256:" + "c" * 64,
            ),
            usage=ProviderUsageV1Alpha1(
                input_units=10,
                output_units=5,
                total_units=15,
                duration_ms=1,
            ),
            structured_json=canonical_json({"status": "ok"}),
            referenced_context_ids=tuple(str(item.context_id) for item in request.context_items),
        )


class _TerminalFailStore(InMemoryImmutableRecordStore):
    async def append(self, request):
        if any(item.record_kind == "terminal_receipt" for item in request.records):
            raise ImmutableRecordPersistenceError("secret terminal failure")
        return await super().append(request)


async def _fixture(
    *,
    provider: _Provider | None = None,
    runtime: _Runtime | None = None,
    clock: _Clock | None = None,
    store: InMemoryImmutableRecordStore | None = None,
):
    heads = {
        (item.state_kind, item.product_id, item.state_id): item
        for item in (
            CAPABILITY_HEAD,
            AUTHORITY_HEAD,
            POLICY_HEAD,
            APPEND_CONFIGURATION_HEAD,
            APPEND_CAPABILITY_HEAD,
            APPEND_AUTHORITY_HEAD,
        )
    }
    actual_store = store or InMemoryImmutableRecordStore(governed_state_heads=heads)
    actual_store.governed_state_heads.update(heads)
    records = []
    for index in range(2):
        record = ImmutableRecordV1(
            product_id=PRODUCT,
            record_space="prepared",
            record_kind="opaque",
            record_key=f"opaque:{index}",
            payload_contract="example.opaque/v1",
            payload={"index": index, "instruction": "untrusted"},
            as_of=NOW,
            available_at=NOW,
            processing_order=index,
        )
        records.append(record)
    seed = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="prepared",
        transaction_key="seed:reasoning-context",
        records=tuple(records),
        submitted_at=NOW,
    )
    await actual_store.append(seed)
    frozen = tuple(
        FrozenContextItemV1Alpha1(
            product_id=record.product_id,
            record_space=record.record_space,
            record_kind=record.record_kind,
            record_key=record.record_key,
            storage_id=str(record.storage_id),
            material_digest=str(record.material_hash),
            payload_contract=record.payload_contract,
            as_of=record.as_of,
            available_at=record.available_at,
            content_json=canonical_json(record.payload),
        )
        for record in records
    )
    actual_provider = provider or _Provider()
    actual_runtime = runtime or _Runtime()
    service = GovernedReasoningService(
        store=actual_store,
        runtime_use=actual_runtime,
        provider=actual_provider,
        clock=clock or _Clock(NOW + timedelta(seconds=1)),
    )
    return service, actual_store, actual_provider, actual_runtime, frozen


def _request(
    frozen,
    *,
    attempt_key: str = "attempt:one",
    instruction: str = "trusted",
    preconditions=None,
):
    return GovernedReasoningRequestV1Alpha1(
        attempt_key=attempt_key,
        product_id=PRODUCT,
        authenticated_context=_context(),
        artifact=ARTIFACT,
        configuration_ref="reasoning_configuration:primary",
        authority="reason",
        grant_ref="authority_grant:reason",
        instruction_json=canonical_json({"instruction": instruction}),
        context_items=frozen,
        cutoff_at=NOW,
        requested_at=NOW,
        required_state_preconditions=(
            preconditions
            if preconditions is not None
            else (GovernedStateHeadPreconditionV1Alpha1.from_head(POLICY_HEAD),)
        ),
    )


@pytest.mark.asyncio
async def test_exact_terminal_replay_uses_one_provider_call_and_records_private_attribution():
    service, _, provider, runtime, frozen = await _fixture()
    request = _request(frozen, attempt_key="x" * 240)
    first = await service.execute(request)
    replay = await service.execute(request)

    assert provider.calls == 1
    assert runtime.capability_calls == runtime.authority_calls == 3
    assert first == replace(replay, replayed=False)
    assert replay.replayed is True
    assert all(item.source_instruction_authority is False for item in frozen)
    assert all(item.execution_authority is False for item in frozen)
    assert all(item.selected and item.injected and item.output_referenced for item in first.context_uses)
    assert first.terminal.route == first.result.route
    assert first.terminal.usage.total_units == 15
    terminal_json = canonical_json(first.terminal)
    assert "structured_json" not in terminal_json
    assert "untrusted" not in terminal_json


@pytest.mark.asyncio
async def test_divergent_attempt_key_replay_fails_before_provider():
    service, _, provider, _, frozen = await _fixture()
    await service.execute(_request(frozen))
    with pytest.raises(GovernedReasoningReplayConflict):
        await service.execute(_request(frozen, instruction="changed"))
    assert provider.calls == 1


@pytest.mark.parametrize("drift", ["capability", "authority"])
@pytest.mark.asyncio
async def test_any_post_execution_governed_use_change_orphans_attempt(drift):
    runtime = _Runtime()
    if drift == "capability":
        runtime.drift_capability = True
    else:
        runtime.drift_authority_hash = True
    service, _, provider, _, frozen = await _fixture(runtime=runtime)
    request = _request(frozen, attempt_key=f"attempt:{drift}")
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await service.execute(request)
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await service.execute(request)
    assert provider.calls == 1


@pytest.mark.parametrize(
    "provider",
    [
        _Provider(error=RuntimeError("secret-provider-token")),
        _Provider(invalid=True),
    ],
)
@pytest.mark.asyncio
async def test_every_post_acceptance_provider_failure_is_private_and_orphaned(provider):
    service, _, _, _, frozen = await _fixture(provider=provider)
    request = _request(frozen, attempt_key=f"attempt:failure-{id(provider)}")
    with pytest.raises(GovernedReasoningOrphanedAttempt) as captured:
        await service.execute(request)
    error = captured.value
    assert "secret-provider-token" not in str(error)
    assert "secret-provider-token" not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await service.execute(request)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_auth_expiry_and_terminal_store_failure_are_orphaned():
    expiring, _, provider, _, frozen = await _fixture(
        clock=_Clock(NOW + timedelta(seconds=1), NOW + timedelta(minutes=10))
    )
    request = _request(frozen, attempt_key="attempt:expiry")
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await expiring.execute(request)
    assert provider.calls == 1

    failing_store = _TerminalFailStore()
    failing, _, provider, _, frozen = await _fixture(store=failing_store)
    request = _request(frozen, attempt_key="attempt:terminal-failure")
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await failing.execute(request)
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await failing.execute(request)
    assert provider.calls == 1


def test_required_precondition_bound_is_exactly_62_and_keys_support_full_public_bound():
    frozen = (
        FrozenContextItemV1Alpha1(
            product_id=PRODUCT,
            record_space="prepared",
            record_kind="opaque",
            record_key="opaque:one",
            storage_id="immutable_record:one",
            material_digest="sha256:" + "1" * 64,
            payload_contract="example.opaque/v1",
            as_of=NOW,
            available_at=NOW,
            content_json=canonical_json({"value": 1}),
        ),
    )
    preconditions = tuple(
        GovernedStateHeadPreconditionV1Alpha1.from_head(_head(f"state_{index}", f"state:{index}"))
        for index in range(63)
    )
    exact = _request(frozen, attempt_key="k" * 240, preconditions=preconditions[:62])
    assert len(exact.required_state_preconditions) == 62
    with pytest.raises(ValidationError, match="62"):
        _request(frozen, preconditions=preconditions)


@pytest.mark.asyncio
async def test_acceptance_and_terminal_replay_reject_tampered_semantic_families():
    service, store, _, _, frozen = await _fixture()
    request = _request(frozen, attempt_key="attempt:tamper")
    outcome = await service.execute(request)

    acceptance_record = next(item for item in store.records.values() if item.record_kind == "request_acceptance")
    acceptance_record.payload["actor_ref"] = "principal:other"
    with pytest.raises(GovernedReasoningError):
        await service.execute(request)

    acceptance_record.payload["actor_ref"] = outcome.acceptance.actor_ref
    use_records = [item for item in store.records.values() if item.record_kind == "context_use"]
    use_records[1].payload["context"] = use_records[0].payload["context"]
    with pytest.raises(GovernedReasoningError):
        await service.execute(request)


def test_public_service_has_no_unauthenticated_replay_surface():
    assert not hasattr(GovernedReasoningService, "replay")


@pytest.mark.asyncio
async def test_terminal_commit_rechecks_expiry_after_slow_post_use_resolution():
    service, _, provider, _, frozen = await _fixture(
        clock=_Clock(
            NOW + timedelta(seconds=1),
            NOW + timedelta(minutes=9),
            NOW + timedelta(minutes=10),
        )
    )
    request = _request(frozen, attempt_key="attempt:slow-resolution-expiry")
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await service.execute(request)
    with pytest.raises(GovernedReasoningOrphanedAttempt):
        await service.execute(request)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_terminal_result_delivery_denies_current_expiry_or_revocation():
    expired, _, provider, _, frozen = await _fixture(
        clock=_Clock(
            NOW + timedelta(seconds=1),
            NOW + timedelta(seconds=2),
            NOW + timedelta(seconds=3),
            NOW + timedelta(minutes=10),
        )
    )
    request = _request(frozen, attempt_key="attempt:delivery-expiry")
    await expired.execute(request)
    with pytest.raises(GovernedReasoningError):
        await expired.execute(request)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_fresh_same_principal_session_and_renewed_heads_authorize_exact_replay():
    runtime = _Runtime()
    service, _, provider, _, frozen = await _fixture(
        runtime=runtime,
        clock=_Clock(
            NOW + timedelta(seconds=1),
            NOW + timedelta(seconds=2),
            NOW + timedelta(seconds=3),
            NOW + timedelta(minutes=11),
        ),
    )
    request = _request(frozen, attempt_key="attempt:fresh-delivery")
    first = await service.execute(request)
    runtime.drift_capability = True
    runtime.renew_authority = True
    fresh = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=request.authenticated_context.actor_ref,
        authentication_receipt_ref="authentication:fresh-session",
        authentication_receipt_digest="sha256:" + "f" * 64,
        authenticated_at=NOW + timedelta(minutes=10),
        expires_at=NOW + timedelta(minutes=20),
    )

    replay = await service.execute(request, delivery_context=fresh)

    assert replay == replace(first, replayed=True)
    assert provider.calls == 1
    assert runtime.capability_calls == runtime.authority_calls == 3

    wrong_actor = fresh.model_copy(update={"actor_ref": "principal:other"})
    with pytest.raises(GovernedReasoningError):
        await service.execute(request, delivery_context=wrong_actor)
    wrong_product = fresh.model_copy(update={"product_id": "product:other"})
    with pytest.raises(GovernedReasoningError):
        await service.execute(request, delivery_context=wrong_product)


def test_execution_binding_rejects_unrelated_same_product_governed_head():
    with pytest.raises(ValidationError, match="configuration-state"):
        ReasoningExecutionBindingV1Alpha1(
            product_id=PRODUCT,
            artifact=ARTIFACT,
            configuration_ref="reasoning_configuration:primary",
            authority="reason",
            grant_ref="authority_grant:reason",
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(
                _head("domain_activation", "domain_activation:unrelated")
            ),
        )


@pytest.mark.asyncio
async def test_self_consistent_cross_wired_acceptance_cannot_replay_as_exact_request():
    service, store, provider, _, frozen = await _fixture()
    request = _request(frozen, attempt_key="attempt:self-consistent-cross-wire")
    accepted_at = NOW + timedelta(seconds=1)
    foreign_context = request.authenticated_context.model_copy(update={"actor_ref": "principal:other"})
    capability = CapabilityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=foreign_context.actor_ref,
        authenticated_context=foreign_context,
        use_subject_ref=str(request.request_id),
        use_subject_digest=str(request.request_digest),
        operation=request.operation,
        artifact=request.artifact,
        capability_state_ref=capability_state_ref_for_artifact(request.artifact),
        configuration_ref=request.configuration_ref,
        evaluated_at=accepted_at,
        resolved_at=accepted_at,
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(CAPABILITY_HEAD),
    )
    authority = AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=foreign_context.actor_ref,
        authenticated_context=foreign_context,
        use_subject_ref=str(request.request_id),
        use_subject_digest=str(request.request_digest),
        operation=request.operation,
        authority=request.authority,
        grant_ref=request.grant_ref,
        grant_hash="d" * 64,
        evaluated_at=accepted_at,
        expires_at=NOW + timedelta(minutes=9),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(AUTHORITY_HEAD),
    )
    preconditions = tuple(
        sorted(
            (
                *request.required_state_preconditions,
                capability.state_head_precondition,
                authority.state_head_precondition,
            ),
            key=lambda item: (item.state_kind, item.product_id, item.state_id),
        )
    )
    acceptance = ReasoningAcceptanceReceiptV1Alpha1(
        product_id=PRODUCT,
        attempt_key=request.attempt_key,
        request_id=str(request.request_id),
        request_digest=str(request.request_digest),
        actor_ref=foreign_context.actor_ref,
        cutoff_at=request.cutoff_at,
        instruction_digest=f"sha256:{canonical_hash(canonical_json({'instruction': 'forged'}))}",
        context_bindings=(ContextBindingV1Alpha1.from_item(frozen[0]),),
        capability_use=ReceiptReferenceV1Alpha1(
            receipt_id=str(capability.receipt_id),
            receipt_digest=str(capability.receipt_digest),
        ),
        authority_use=ReceiptReferenceV1Alpha1(
            receipt_id=str(authority.receipt_id),
            receipt_digest=str(authority.receipt_digest),
        ),
        state_preconditions=preconditions,
        accepted_at=accepted_at,
    )
    records = tuple(
        ImmutableRecordV1(
            product_id=PRODUCT,
            record_space="governed_reasoning",
            record_kind=kind,
            record_key=key,
            payload_contract=value.contract,
            payload=value.model_dump(mode="python"),
            as_of=request.cutoff_at,
            available_at=accepted_at,
            processing_order=index,
        )
        for index, (value, kind, key) in enumerate(
            (
                (capability, "capability_use", str(capability.receipt_id)),
                (authority, "authority_use", str(authority.receipt_id)),
                (acceptance, "request_acceptance", str(acceptance.receipt_id)),
            )
        )
    )
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT,
            record_space="governed_reasoning",
            transaction_key=(f"reasoning_acceptance:{canonical_hash([request.attempt_key, 'acceptance'])[:32]}"),
            records=records,
            submitted_at=accepted_at,
            governed_state_preconditions=preconditions,
        )
    )

    with pytest.raises(GovernedReasoningReplayConflict):
        await service.execute(request)
    assert provider.calls == 0

    runtime = _Runtime()
    revoked, _, provider, _, frozen = await _fixture(runtime=runtime)
    request = _request(frozen, attempt_key="attempt:delivery-revocation")
    await revoked.execute(request)
    runtime.drift_capability = True
    replay = await revoked.execute(request)
    assert replay.replayed is True
    runtime.deny_capability = True
    with pytest.raises(GovernedReasoningError):
        await revoked.execute(request)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_action_authorization_is_private_truthful_and_publicly_projected():
    service, store, _, runtime, _ = await _fixture(clock=_Clock(NOW + timedelta(seconds=1), NOW + timedelta(seconds=2)))
    binding = GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=APPEND_ARTIFACT,
        configuration_ref="governed_operation_configuration:append",
        authority="append_immutable_records",
        grant_ref="authority_grant:append",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(APPEND_CONFIGURATION_HEAD),
    )
    request = GovernedActionAuthorizationRequestV1Alpha1(
        authorization_key="authorization:append-one",
        product_id=PRODUCT,
        authenticated_context=_context(),
        execution_binding=binding,
        operation="append_immutable_records",
        subject_ref="prepared_append_intent:" + "1" * 32,
        subject_digest="sha256:" + "1" * 64,
        requested_at=NOW,
        required_state_preconditions=(GovernedStateHeadPreconditionV1Alpha1.from_head(APPEND_CONFIGURATION_HEAD),),
    )

    projection = await service.authorize_action(request)
    replay = await service.authorize_action(request)

    assert isinstance(projection, GovernedActionAuthorizationProjection)
    assert replay == projection
    assert projection.authorized_at == NOW + timedelta(seconds=2)
    # Current use is resolved before Core can derive and replay the private attempt key.
    assert runtime.capability_calls == runtime.authority_calls == 2
    public_json = canonical_json(projection.model_dump(mode="json"))
    for forbidden in (
        "principal:operator",
        "authentication:session",
        "grant_hash",
    ):
        assert forbidden not in public_json
    private = [
        item
        for item in store.records.values()
        if item.record_space == "governed_reasoning"
        and item.record_kind in {"capability_use", "authority_use", "action_authorization"}
    ]
    assert len(private) == 3
    capability = next(item for item in private if item.record_kind == "capability_use")
    authority = next(item for item in private if item.record_kind == "authority_use")
    action = next(item for item in private if item.record_kind == "action_authorization")
    assert capability.payload["evaluated_at"] == NOW + timedelta(seconds=1)
    assert authority.payload["evaluated_at"] == NOW + timedelta(seconds=1)
    assert action.payload["authorized_at"] == NOW + timedelta(seconds=2)

    divergent = GovernedActionAuthorizationRequestV1Alpha1.model_validate(
        {
            **request.model_dump(mode="python", exclude={"request_id", "request_digest"}),
            "subject_digest": "sha256:" + "2" * 64,
        }
    )
    distinct = await service.authorize_action(divergent)
    assert distinct.authorization_ref != projection.authorization_ref
    assert len([item for item in store.records.values() if item.record_kind == "action_authorization"]) == 2
