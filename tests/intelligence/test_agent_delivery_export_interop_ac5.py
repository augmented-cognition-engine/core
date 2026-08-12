from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace.application.agent_composition_lifecycle import PreparedLifecycleDeliveryV1Alpha1
from ace.application.external_operations import (
    ExternalOperationError,
    GovernedAdministrativeExportService,
    GovernedDestinationDeliveryService,
    GovernedExternalEffectService,
    delivery_payload_digest,
    export_manifest_checksum,
)
from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.external_operations import (
    AdministrativeExportManifestV1Alpha1,
    DeliveryState,
    DestinationDefinitionV1Alpha1,
    DestinationDeliveryIntentV1Alpha1,
    DestinationDeliveryResultV1Alpha1,
    DestinationLifecycle,
    DestinationPolicyCoordinateV1Alpha1,
    DestinationPolicyKind,
    DestinationRevisionV1Alpha1,
    EffectState,
    ExternalEffectIntentV1Alpha1,
    ExternalEffectResultV1Alpha1,
    ExternalOperation,
    ExternalOperationAuthorityV1Alpha1,
    ExternalOperationCancellationV1Alpha1,
    LookupDisposition,
    exact_external_reference,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from ace.testing.reference_external_destination import ReferenceExternalDestinationAdapter

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parents[2] / "evaluations/fixtures/ac5_agent_delivery_export_interop_conformance_v1.json"


def _ref(key: str, contract: str = "example.contract/v1") -> ExactArtifactReferenceV1Alpha1:
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=key,
        artifact_digest="sha256:" + "b" * 64,
        artifact_contract=contract,
    )


def test_fixture_freezes_operation_separation_and_failure_matrix() -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["operations"] == [
        "prepared_internal_handoff",
        "destination_delivery",
        "administrative_export",
        "external_effect",
    ]
    assert len(fixture["destination_policy_kinds"]) == 6
    assert len(fixture["cases"]) == 24
    assert not any(fixture["invariants"].values())


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id="product:ac5",
        actor_ref="actor:operator",
        authentication_receipt_ref="authentication:ac5",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _destination() -> DestinationRevisionV1Alpha1:
    definition = DestinationDefinitionV1Alpha1(
        product_id="product:ac5",
        destination_key="reference-mailbox",
        adapter_contract="ace.core.external-destination-adapter/v1alpha1",
        protocol_refs=("protocol:digest-mailbox-v1",),
        capability_refs=("delivery", "effect"),
        recipient_binding_kind="opaque_recipient_ref",
    )
    policies = tuple(
        DestinationPolicyCoordinateV1Alpha1(
            kind=kind,
            policy_ref=f"policy:{kind.value}",
            state_id=f"destination_policy:{kind.value}",
            material_digest="sha256:" + f"{index + 1:x}" * 64,
        )
        for index, kind in enumerate(DestinationPolicyKind)
    )
    return DestinationRevisionV1Alpha1(
        definition=exact_external_reference(definition),
        sequence=1,
        lifecycle=DestinationLifecycle.ACTIVE,
        policies=policies,
        revised_at=NOW - timedelta(minutes=1),
    )


def _head(kind: str, state_id: str) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id="product:ac5",
        state_id=state_id,
        sequence=1,
        revision_id=f"revision:{kind}:{state_id}",
        commit_receipt_id=f"commit:{kind}:{state_id}",
        updated_at=NOW - timedelta(minutes=1),
    )


class _Authority:
    def __init__(self, adapter: ReferenceExternalDestinationAdapter, store: InMemoryImmutableRecordStore) -> None:
        self.adapter = adapter
        self.store = store
        self.calls: list[ExternalOperation] = []
        self.substitute: ExternalOperation | None = None
        self.revoked = False

    async def resolve(
        self,
        *,
        authenticated_context,
        operation,
        use_subject,
        destination_revision,
        recipient_ref,
        evaluated_at,
    ) -> ExternalOperationAuthorityV1Alpha1:
        self.calls.append(operation)
        if self.revoked:
            raise RuntimeError("revoked")
        actual = self.substitute or operation
        artifact = self.adapter.artifact_identity
        cap_id = capability_state_ref_for_artifact(artifact)
        grant_id = f"grant:{actual.value}"
        config_id = f"configuration:{actual.value}"
        cap_head, grant_head, config_head = (
            _head("capability_state", cap_id),
            _head("authority_grant", grant_id),
            _head("external_operation_configuration", config_id),
        )
        for head in (cap_head, grant_head, config_head):
            self.store.set_governed_state_head(head)
        capability = CapabilityUseReceiptV1Alpha1(
            product_id=authenticated_context.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject_ref=use_subject.artifact_id,
            use_subject_digest=use_subject.artifact_digest,
            operation=actual.value,
            artifact=artifact,
            capability_state_ref=cap_id,
            configuration_ref=config_id,
            evaluated_at=evaluated_at,
            resolved_at=evaluated_at,
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(cap_head),
        )
        authority = AuthorityUseReceiptV1Alpha1(
            product_id=authenticated_context.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject_ref=use_subject.artifact_id,
            use_subject_digest=use_subject.artifact_digest,
            operation=actual.value,
            authority=actual.value,
            grant_ref=grant_id,
            grant_hash="c" * 64,
            evaluated_at=evaluated_at,
            expires_at=authenticated_context.expires_at,
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(grant_head),
        )
        return ExternalOperationAuthorityV1Alpha1(
            operation=actual,
            product_id=authenticated_context.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject=use_subject,
            destination_revision=(exact_external_reference(destination_revision) if destination_revision else None),
            capability_use=capability,
            authority_use=authority,
            current_heads=tuple(
                GovernedStateHeadPreconditionV1Alpha1.from_head(head) for head in (cap_head, grant_head, config_head)
            ),
            evaluated_at=evaluated_at,
        )


def _stack():
    store = InMemoryImmutableRecordStore()
    adapter = ReferenceExternalDestinationAdapter(clock=lambda: NOW)
    authority = _Authority(adapter, store)
    destination = _destination()
    return store, adapter, authority, destination


def _prepared() -> PreparedLifecycleDeliveryV1Alpha1:
    return PreparedLifecycleDeliveryV1Alpha1(
        product_id="product:ac5",
        source_manifest=_ref("stage_manifest:ac3", "ace.core.stage-run-manifest/v1alpha1"),
        artifacts=(_ref("artifact:brief"),),
        target_ref="ac5_delivery_gate:required",
        prepared_at=NOW,
    )


def _delivery_intent(prepared, destination) -> DestinationDeliveryIntentV1Alpha1:
    return DestinationDeliveryIntentV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        prepared_handoff=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(prepared.package_id),
            artifact_digest=str(prepared.package_digest),
            artifact_contract=prepared.contract,
        ),
        destination_revision=exact_external_reference(destination),
        recipient_ref="recipient:opaque",
        payload_artifacts=prepared.artifacts,
        payload_digest=delivery_payload_digest(prepared.artifacts),
        idempotency_key="delivery:stable-key",
        retry_policy_ref="retry:lookup-first",
        cancellation_ref="cancel:delivery",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )


async def test_prepared_to_authorized_delivery_ack_and_duplicate_replay() -> None:
    store, adapter, authority, destination = _stack()
    prepared = _prepared()
    assert prepared.external_send_occurred is False
    assert not adapter.deliveries
    service = GovernedDestinationDeliveryService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    intent = _delivery_intent(prepared, destination)
    outcome = await service.deliver(prepared=prepared, intent=intent)
    assert outcome.result.state is DeliveryState.ACKNOWLEDGED
    assert outcome.result.acknowledgment is not None
    assert outcome.result.acknowledgment.truth_proven is False
    assert outcome.result.acknowledgment.downstream_execution_proven is False
    assert authority.calls == [ExternalOperation.DELIVERY, ExternalOperation.DELIVERY]
    assert prepared.external_send_occurred is False
    replay = await service.deliver(prepared=prepared, intent=intent)
    assert replay.replayed is True
    assert len(adapter.deliveries) == 1


async def test_delivery_export_and_effect_authority_do_not_substitute() -> None:
    store, adapter, authority, destination = _stack()
    prepared = _prepared()
    intent = _delivery_intent(prepared, destination)
    authority.substitute = ExternalOperation.ADMIN_EXPORT
    service = GovernedDestinationDeliveryService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    with pytest.raises(ExternalOperationError, match="delivery authority"):
        await service.deliver(prepared=prepared, intent=intent)
    assert not adapter.deliveries


async def test_administrative_export_has_redaction_checksum_and_no_send_or_runtime_authority() -> None:
    store, adapter, authority, _ = _stack()
    included = (_ref("artifact:portable"),)
    checksum = export_manifest_checksum(
        included=included,
        omitted_refs=("artifact:omitted",),
        redacted_refs=("artifact:redacted",),
        retention_policy_ref="retention:bounded",
        erasure_dependency_refs=("erasure:subject-1",),
        data_class_policy_ref="data-class:portable",
    )
    manifest = AdministrativeExportManifestV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        included=included,
        omitted_refs=("artifact:omitted",),
        redacted_refs=("artifact:redacted",),
        retention_policy_ref="retention:bounded",
        erasure_dependency_refs=("erasure:subject-1",),
        data_class_policy_ref="data-class:portable",
        checksum=checksum,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    service = GovernedAdministrativeExportService(store=store, authority=authority, adapter=adapter, clock=lambda: NOW)
    receipt = await service.export(manifest)
    assert receipt.artifact_checksum == checksum
    assert receipt.delivery_authority is False
    assert receipt.runtime_authority is False
    assert receipt.external_send_occurred is False
    assert authority.calls == [ExternalOperation.ADMIN_EXPORT]
    assert not adapter.deliveries and not adapter.effects


async def test_external_effect_requires_separate_preparation_and_pre_effect_authority() -> None:
    store, adapter, authority, destination = _stack()
    intent = ExternalEffectIntentV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        destination_revision=exact_external_reference(destination),
        recipient_ref="recipient:opaque",
        effect_type="opaque_consequential_operation",
        parameters_digest="sha256:" + "d" * 64,
        idempotency_key="effect:stable-key",
        retry_policy_ref="retry:lookup-first",
        cancellation_ref="cancel:effect",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    service = GovernedExternalEffectService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    outcome = await service.execute(intent=intent)
    assert outcome.result.state is EffectState.SUCCEEDED
    assert authority.calls == [ExternalOperation.EXTERNAL_EFFECT, ExternalOperation.EXTERNAL_EFFECT]
    replay = await service.execute(intent=intent)
    assert replay.replayed is True
    assert len(adapter.effects) == 1


async def test_unknown_effect_forbids_blind_retry_and_requires_lookup() -> None:
    store, adapter, authority, destination = _stack()
    intent = ExternalEffectIntentV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        destination_revision=exact_external_reference(destination),
        recipient_ref="recipient:opaque",
        effect_type="opaque_consequential_operation",
        parameters_digest="sha256:" + "e" * 64,
        idempotency_key="effect:unknown-key",
        retry_policy_ref="retry:lookup-first",
        cancellation_ref="cancel:effect",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    with pytest.raises(ValidationError, match="requires lookup"):
        ExternalEffectResultV1Alpha1(
            attempt=_ref("attempt:unknown", "ace.core.external-effect-attempt/v1alpha1"),
            state=EffectState.UNKNOWN,
            failure_code="unknown",
            retry_after_lookup=False,
            completed_at=NOW,
        )
    service = GovernedExternalEffectService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    outcome = await service.execute(intent=intent)
    lookup = await service.reconcile_unknown(intent=intent, attempt=outcome.attempt)
    assert lookup.disposition is LookupDisposition.FOUND
    assert lookup.permits_retry is False


class _IndeterminateThenSuccessAdapter(ReferenceExternalDestinationAdapter):
    def __init__(self, *, clock):
        super().__init__(clock=clock)
        self.delivery_calls = 0
        self.effect_calls = 0

    async def send_delivery(self, *, intent, attempt):
        self.delivery_calls += 1
        if self.delivery_calls == 1:
            return DestinationDeliveryResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=DeliveryState.UNKNOWN,
                failure_code="provider_result_indeterminate",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        return await super().send_delivery(intent=intent, attempt=attempt)

    async def execute_effect(self, *, intent, attempt):
        self.effect_calls += 1
        if self.effect_calls == 1:
            return ExternalEffectResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=EffectState.UNKNOWN,
                failure_code="provider_result_indeterminate",
                retry_after_lookup=True,
                completed_at=self._now(),
            )
        return await super().execute_effect(intent=intent, attempt=attempt)


async def test_delivery_retry_requires_durable_conclusive_not_found_lookup() -> None:
    store = InMemoryImmutableRecordStore()
    adapter = _IndeterminateThenSuccessAdapter(clock=lambda: NOW)
    authority = _Authority(adapter, store)
    destination = _destination()
    prepared = _prepared()
    intent = _delivery_intent(prepared, destination)
    service = GovernedDestinationDeliveryService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )

    first = await service.deliver(prepared=prepared, intent=intent)
    assert first.result.state is DeliveryState.UNKNOWN
    with pytest.raises(ExternalOperationError, match="conclusive not-found lookup evidence"):
        await service.deliver(prepared=prepared, intent=intent, attempt_number=2)
    assert adapter.delivery_calls == 1

    lookup = await service.reconcile_unknown(intent=intent, attempt=first.attempt)
    assert lookup.disposition is LookupDisposition.NOT_FOUND
    assert lookup.permits_retry is True
    retry = await service.deliver(prepared=prepared, intent=intent, attempt_number=2)
    assert retry.result.state is DeliveryState.ACKNOWLEDGED
    assert adapter.delivery_calls == 2


async def test_effect_retry_requires_durable_conclusive_not_found_lookup() -> None:
    store = InMemoryImmutableRecordStore()
    adapter = _IndeterminateThenSuccessAdapter(clock=lambda: NOW)
    authority = _Authority(adapter, store)
    destination = _destination()
    intent = ExternalEffectIntentV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        destination_revision=exact_external_reference(destination),
        recipient_ref="recipient:opaque",
        effect_type="opaque_consequential_operation",
        parameters_digest="sha256:" + "e" * 64,
        idempotency_key="effect:retry-after-lookup",
        retry_policy_ref="retry:lookup-first",
        cancellation_ref="cancel:effect",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    service = GovernedExternalEffectService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )

    first = await service.execute(intent=intent)
    assert first.result.state is EffectState.UNKNOWN
    with pytest.raises(ExternalOperationError, match="conclusive not-found lookup evidence"):
        await service.execute(intent=intent, attempt_number=2)
    assert adapter.effect_calls == 1

    lookup = await service.reconcile_unknown(intent=intent, attempt=first.attempt)
    assert lookup.disposition is LookupDisposition.NOT_FOUND
    assert lookup.permits_retry is True
    retry = await service.execute(intent=intent, attempt_number=2)
    assert retry.result.state is EffectState.SUCCEEDED
    assert adapter.effect_calls == 2


async def test_revoked_current_authority_fails_before_adapter_send() -> None:
    store, adapter, authority, destination = _stack()
    authority.revoked = True
    service = GovernedDestinationDeliveryService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    with pytest.raises(ExternalOperationError, match="failed closed"):
        await service.deliver(prepared=_prepared(), intent=_delivery_intent(_prepared(), destination))
    assert not adapter.deliveries


async def test_destination_drift_and_cancellation_fail_before_send() -> None:
    store, adapter, authority, destination = _stack()
    prepared = _prepared()
    drifted = DestinationRevisionV1Alpha1(
        **destination.model_dump(
            mode="python",
            exclude={"sequence", "prior_revision_id", "revised_at", "revision_id", "revision_digest"},
        ),
        sequence=2,
        prior_revision_id=str(destination.revision_id),
        revised_at=NOW,
    )
    service = GovernedDestinationDeliveryService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    with pytest.raises(ExternalOperationError, match="destination"):
        await service.deliver(prepared=prepared, intent=_delivery_intent(prepared, drifted))
    intent = _delivery_intent(prepared, destination)
    cancellation = ExternalOperationCancellationV1Alpha1(
        operation=ExternalOperation.DELIVERY,
        subject=exact_external_reference(intent),
        cancellation_ref=intent.cancellation_ref,
        actor_ref="actor:operator",
        cancelled_at=NOW,
    )
    with pytest.raises(ExternalOperationError, match="cancellation"):
        await service.deliver(prepared=prepared, intent=intent, cancellation=cancellation)
    assert not adapter.deliveries


class _Crash(BaseException):
    pass


class _CrashAfterEffectAdapter(ReferenceExternalDestinationAdapter):
    async def execute_effect(self, *, intent, attempt):
        result = ExternalEffectResultV1Alpha1(
            attempt=exact_external_reference(attempt),
            state=EffectState.SUCCEEDED,
            result_digest_value=intent.parameters_digest,
            completed_at=self._now(),
        )
        self.effects[intent.idempotency_key] = result
        raise _Crash("simulated process loss after effect and before terminal persistence")


async def test_restart_lookup_recovers_attempt_without_duplicate_effect() -> None:
    store = InMemoryImmutableRecordStore()
    adapter = _CrashAfterEffectAdapter(clock=lambda: NOW)
    authority = _Authority(adapter, store)
    destination = _destination()
    intent = ExternalEffectIntentV1Alpha1(
        product_id="product:ac5",
        authenticated_context=_context(),
        destination_revision=exact_external_reference(destination),
        recipient_ref="recipient:opaque",
        effect_type="opaque_consequential_operation",
        parameters_digest="sha256:" + "f" * 64,
        idempotency_key="effect:restart-key",
        retry_policy_ref="retry:lookup-first",
        cancellation_ref="cancel:effect",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    first = GovernedExternalEffectService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    with pytest.raises(_Crash):
        await first.execute(intent=intent)
    assert len(adapter.effects) == 1
    reopened = GovernedExternalEffectService(
        store=store, authority=authority, adapter=adapter, destination=destination, clock=lambda: NOW
    )
    recovered = await reopened.execute(intent=intent)
    assert recovered.recovered_by_lookup is True
    assert recovered.result.state is EffectState.SUCCEEDED
    assert len(adapter.effects) == 1


def test_terminal_state_contracts_cover_timeout_rejection_partial_duplicate_and_unknown() -> None:
    attempt = _ref("delivery_attempt:states", "ace.core.destination-delivery-attempt/v1alpha1")
    from ace.core.external_operations import DestinationDeliveryResultV1Alpha1

    states = {
        DeliveryState.TIMED_OUT: "timed_out",
        DeliveryState.REJECTED: "rejected",
        DeliveryState.PARTIAL: "partial",
        DeliveryState.CANCELLED: "cancelled",
    }
    for state, failure in states.items():
        result = DestinationDeliveryResultV1Alpha1(
            attempt=attempt,
            state=state,
            failure_code=failure,
            completed_at=NOW,
        )
        assert result.state is state
    duplicate = DestinationDeliveryResultV1Alpha1(
        attempt=attempt,
        state=DeliveryState.DUPLICATE,
        completed_at=NOW,
    )
    assert duplicate.state is DeliveryState.DUPLICATE
    unknown = DestinationDeliveryResultV1Alpha1(
        attempt=attempt,
        state=DeliveryState.UNKNOWN,
        failure_code="indeterminate",
        retry_after_lookup=True,
        completed_at=NOW,
    )
    assert unknown.retry_after_lookup is True
