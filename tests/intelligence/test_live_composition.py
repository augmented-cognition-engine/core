"""Host composition gate: core.engine wires LIVE cognition through bounded adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.live_intelligence_bridge import (
    LiveBriefSynthesisService,
    LiveIntelligenceBridgeService,
)
from ace.application.live_source_ingress import LiveSourceIngressService
from ace.core.reasoning import ReasoningExecutionBindingV1Alpha1
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.testing import InMemoryImmutableRecordStore
from core.engine.core.live_cognition import (
    BoundedSourceAdapterRegistry,
    LiveCompositionError,
    build_live_brief_synthesis_service,
    build_live_intelligence_bridge_service,
    build_live_source_ingress_service,
)
from tests.intelligence.test_categorical_transition_detection import PRODUCT_ID
from tests.intelligence.test_live_bridge_detector_dispatch import (
    _Authorizer,
    _bridge_environment,
    _operation_binding,
)

pytestmark = pytest.mark.unit


def _artifact(implementation_id: str = "market_feed_adapter") -> CapabilityArtifactIdentityV1Alpha1:
    return CapabilityArtifactIdentityV1Alpha1(
        capability="acquire_live_source",
        contract="ace.intelligence.source-adapter/v1alpha1",
        implementation_id=implementation_id,
        implementation_version="0.1.0",
        artifact_digest="sha256:" + "a" * 64,
    )


class _Adapter:
    def __init__(self, artifact: CapabilityArtifactIdentityV1Alpha1) -> None:
        self.artifact_identity = artifact

    async def capture(self, request):  # pragma: no cover - never dispatched here
        raise AssertionError("composition tests never acquire")


def test_registry_resolves_only_the_exact_registered_artifact() -> None:
    adapter = _Adapter(_artifact())
    registry = BoundedSourceAdapterRegistry(adapters=(adapter,))
    assert registry.resolve_source_adapter(artifact=_artifact()) is adapter
    assert registry.resolve_source_adapter(artifact=_artifact("other_adapter")) is None


def test_registry_rejects_duplicate_and_identity_free_registration() -> None:
    registry = BoundedSourceAdapterRegistry(adapters=(_Adapter(_artifact()),))
    with pytest.raises(LiveCompositionError):
        registry.register(_Adapter(_artifact()))

    class _NoIdentity:
        async def capture(self, request): ...

    with pytest.raises(LiveCompositionError):
        BoundedSourceAdapterRegistry(adapters=(_NoIdentity(),))


def test_ingress_factory_composes_the_public_service_from_explicit_ports() -> None:
    class _Port: ...

    activation, definitions, runtime_use = _Port(), _Port(), _Port()
    registry = BoundedSourceAdapterRegistry(adapters=(_Adapter(_artifact()),))
    store = InMemoryImmutableRecordStore()
    service = build_live_source_ingress_service(
        activation_service=activation,
        source_definitions=definitions,
        runtime_use=runtime_use,
        adapters=registry,
        store=store,
    )
    assert isinstance(service, LiveSourceIngressService)
    assert service.activation_service is activation
    assert service.source_definitions is definitions
    assert service.runtime_use is runtime_use
    assert service.adapters is registry
    assert service.store is store


@pytest.mark.asyncio
async def test_bridge_and_brief_factories_compose_governed_services() -> None:
    prepared, store, _ = await _bridge_environment()
    operation_binding, _ = _operation_binding(prepared.revision.occurred_at)

    class _ActivationReload:
        async def reload(self, *, product_id, activation_key):
            return None

    activation = _ActivationReload()
    bridge = build_live_intelligence_bridge_service(
        activation_service=activation,
        pack=prepared.pack,
        store=store,
        authorizer=_Authorizer(),
        operation_binding=operation_binding,
    )
    assert isinstance(bridge, LiveIntelligenceBridgeService)
    assert bridge.pack == prepared.pack
    assert bridge.store is store

    head = GovernedStateHeadV1(
        state_kind="reasoning_configuration",
        product_id=PRODUCT_ID,
        state_id="reasoning_configuration:live",
        sequence=1,
        revision_id="reasoning_configuration_revision:1",
        commit_receipt_id="governed_state_commit:live-reasoning-1",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC) - timedelta(days=1),
    )
    execution_binding = ReasoningExecutionBindingV1Alpha1(
        product_id=PRODUCT_ID,
        artifact=CapabilityArtifactIdentityV1Alpha1(
            capability="structured_reasoning",
            contract="ace.core.reasoning-provider/v1alpha1",
            implementation_id="live_reasoning_fixture",
            implementation_version="0.1.0",
            artifact_digest="sha256:" + "c" * 64,
        ),
        configuration_ref="reasoning_configuration:live",
        authority="reason",
        grant_ref="authority_grant:live-reasoning",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(head),
    )
    synthesis = build_live_brief_synthesis_service(
        activation_service=activation,
        pack=prepared.pack,
        store=store,
        reasoning=object(),
        execution_binding=execution_binding,
        append_binding=operation_binding,
    )
    assert isinstance(synthesis, LiveBriefSynthesisService)
    assert synthesis.pack == prepared.pack
    assert synthesis.execution_binding == execution_binding
    assert synthesis.append_binding == operation_binding
