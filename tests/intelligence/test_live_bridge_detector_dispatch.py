from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ace.application import (
    DomainActivationAdmissionService,
    LiveIntelligenceBridgeService,
)
from ace.application.live_source_ingress import LIVE_SOURCE_RECORD_SPACE
from ace.core.reasoning import (
    GovernedActionAuthorizationProjection,
    GovernedOperationBindingV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.core.records import ImmutableRecordV1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.live_bridge import LiveDerivationRequestV1Alpha1
from ace.intelligence.contracts.resources import IntelligenceResourceMode
from ace.testing import InMemoryImmutableRecordStore
from tests.intelligence.test_categorical_transition_detection import (
    AS_OF,
    DETECTOR_ID,
    PRODUCT_ID,
    _binding,
    _categorical_rule,
    _snapshot,
)
from tests.intelligence.test_domain_activation_admission import _Authority, _MemoryStore

pytestmark = pytest.mark.unit

NUMERIC_DETECTOR_ID = "material_measure_change"
NUMERIC_RULE = {
    "detector_id": NUMERIC_DETECTOR_ID,
    "entity_type_id": "subject",
    "attribute_id": "measure",
    "metric": "percent_change",
    "threshold": 5.0,
    "shift_type": "material_measure_change",
    "signal_type": "measure_attention",
}


class _Authorizer:
    def __init__(self) -> None:
        self.issued: dict[tuple[str, str, str], GovernedActionAuthorizationProjection] = {}

    async def authorize_action(self, request):
        projection = GovernedActionAuthorizationProjection(
            authorization_ref=ReceiptReferenceV1Alpha1(
                receipt_id=f"governed_action_authorization:{request.authorization_key}",
                receipt_digest="sha256:" + "d" * 64,
            ),
            authorized_at=request.requested_at,
            state_preconditions=request.required_state_preconditions,
        )
        self.issued[(request.operation, request.subject_ref, request.subject_digest)] = projection
        return projection

    async def verify_action_reference(
        self,
        *,
        product_id,
        operation,
        subject_ref,
        subject_digest,
        expected,
    ):
        projection = self.issued.get((operation, subject_ref, subject_digest))
        if projection is None or projection.authorization_ref != expected:
            raise RuntimeError("no exact authorization on record")
        return projection


async def _committed_environment(prepared_binding):
    activation_store = _MemoryStore()
    committed = await DomainActivationAdmissionService(
        store=activation_store,
        authority=_Authority(),
    ).admit(
        prepared_binding.revision,
        expected_head_revision_id=None,
        committed_at=prepared_binding.revision.occurred_at + timedelta(seconds=1),
    )
    activation_head = next(iter(activation_store.heads.values()))
    return committed, activation_head


def _operation_binding(head_updated_at: datetime):
    append_head = GovernedStateHeadV1(
        state_kind="governed_operation_configuration",
        product_id=PRODUCT_ID,
        state_id="governed_operation_configuration:p2b-append",
        sequence=1,
        revision_id="governed_operation_configuration_revision:1",
        commit_receipt_id="governed_state_commit:p2b-append-1",
        updated_at=head_updated_at,
    )
    binding = GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT_ID,
        artifact=CapabilityArtifactIdentityV1Alpha1(
            capability="append_immutable_records",
            contract="ace.core.immutable-record-appender/v1alpha1",
            implementation_id="p2b_dispatch_append_fixture",
            implementation_version="0.1.0",
            artifact_digest="sha256:" + "b" * 64,
        ),
        configuration_ref=append_head.state_id,
        authority="append_immutable_records",
        grant_ref="authority_grant:p2b-append",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(append_head),
    )
    return binding, append_head


def _seed_snapshot(store: InMemoryImmutableRecordStore, snapshot) -> None:
    record = ImmutableRecordV1(
        product_id=snapshot.product_id,
        record_space=LIVE_SOURCE_RECORD_SPACE,
        record_kind="entity_snapshot",
        record_key=str(snapshot.resource_id),
        payload_contract=str(snapshot.contract),
        payload=snapshot.model_dump(mode="python"),
        as_of=snapshot.as_of,
        available_at=snapshot.projected_at,
        processing_order=0,
    )
    store.records[str(record.storage_id)] = record


async def _bridge_environment():
    prepared = _binding(
        categorical_rules=[_categorical_rule()],
        numeric_rules=[NUMERIC_RULE],
    )
    committed, activation_head = await _committed_environment(prepared)
    operation_binding, append_head = _operation_binding(prepared.revision.occurred_at)
    store = InMemoryImmutableRecordStore()
    store.set_governed_state_head(activation_head)
    store.set_governed_state_head(append_head)

    class _ActivationReload:
        async def reload(self, *, product_id, activation_key):
            if (
                product_id == prepared.revision.spec.product_id
                and activation_key == prepared.revision.spec.activation_key
            ):
                return committed
            return None

    bridge = LiveIntelligenceBridgeService(
        activation_service=_ActivationReload(),
        pack=prepared.pack,
        store=store,
        authorizer=_Authorizer(),
        operation_binding=operation_binding,
    )
    return prepared, store, bridge


def _derivation_request(prepared, *, detector_id, baseline, current, key):
    return LiveDerivationRequestV1Alpha1(
        derivation_key=key,
        product_id=PRODUCT_ID,
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT_ID,
            actor_ref="principal:live-operator",
            authentication_receipt_ref="authentication:p2b-dispatch",
            authentication_receipt_digest="sha256:" + "e" * 64,
            authenticated_at=AS_OF - timedelta(minutes=5),
            expires_at=AS_OF + timedelta(hours=1),
        ),
        activation_revision=prepared.reference,
        pack=prepared.revision.spec.pack,
        detector_id=detector_id,
        baseline=resource_reference(baseline),
        current=resource_reference(current),
        detected_at=AS_OF,
        attention_evaluated_at=AS_OF,
        requested_at=AS_OF + timedelta(seconds=1),
    )


@pytest.mark.asyncio
async def test_live_bridge_derives_and_replays_a_categorical_detector() -> None:
    prepared, store, bridge = await _bridge_environment()
    baseline = _snapshot(
        prepared,
        "draft",
        as_of=AS_OF - timedelta(days=1),
        mode=IntelligenceResourceMode.LIVE,
    )
    current = _snapshot(prepared, "active", as_of=AS_OF, mode=IntelligenceResourceMode.LIVE)
    _seed_snapshot(store, baseline)
    _seed_snapshot(store, current)

    request = _derivation_request(
        prepared,
        detector_id=DETECTOR_ID,
        baseline=baseline,
        current=current,
        key="live-derivation:p2b:categorical",
    )
    admission = await bridge.derive(request)

    assert admission.replayed is False
    assert admission.shift.mode is IntelligenceResourceMode.LIVE
    delta = admission.shift.delta.parsed_value()
    assert delta["detector_id"] == DETECTOR_ID
    assert delta["from_value"] == "draft"
    assert delta["to_value"] == "active"
    assert admission.signal.signal_type_ref == "stage_attention"
    assert admission.derivation_receipt.detector_id == DETECTOR_ID

    replay = await bridge.derive(request)
    assert replay.replayed is True
    assert replay.shift == admission.shift
    assert replay.signal == admission.signal
    assert replay.derivation_receipt == admission.derivation_receipt


@pytest.mark.asyncio
async def test_live_bridge_still_derives_a_numeric_detector_through_dispatch() -> None:
    prepared, store, bridge = await _bridge_environment()
    baseline = _snapshot(
        prepared,
        "draft",
        as_of=AS_OF - timedelta(days=1),
        attributes_override={"stage": "draft", "cohort": "primary", "measure": 100.0},
        mode=IntelligenceResourceMode.LIVE,
    )
    current = _snapshot(
        prepared,
        "draft",
        as_of=AS_OF,
        attributes_override={"stage": "draft", "cohort": "primary", "measure": 90.0},
        mode=IntelligenceResourceMode.LIVE,
    )
    _seed_snapshot(store, baseline)
    _seed_snapshot(store, current)

    request = _derivation_request(
        prepared,
        detector_id=NUMERIC_DETECTOR_ID,
        baseline=baseline,
        current=current,
        key="live-derivation:p2b:numeric",
    )
    admission = await bridge.derive(request)

    assert admission.replayed is False
    delta = admission.shift.delta.parsed_value()
    assert delta["detector_id"] == NUMERIC_DETECTOR_ID
    assert delta["metric"] == "percent_change"
    assert admission.signal.signal_type_ref == "measure_attention"
