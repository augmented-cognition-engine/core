from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ace.core import (
    CapabilityArtifactIdentityV1Alpha1,
    GovernedActionExecutionService,
    GovernedActionReviewService,
    GovernedOperationBindingV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
)
from core.engine.core.action_execution import (
    ActionCompositionError,
    BoundedActionAdapterRegistry,
    build_governed_action_execution_service,
    build_governed_action_review_service,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:action-composition"
ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="bounded_action_execution",
    contract="ace.core.action-adapter/v1alpha1",
    implementation_id="fixture_adapter",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "a" * 64,
)


class _Adapter:
    artifact_identity = ARTIFACT

    async def prepare(self, intent):  # pragma: no cover - composition only
        raise AssertionError(intent)

    async def execute(self, plan, authorization):  # pragma: no cover - composition only
        raise AssertionError((plan, authorization))


def _binding(artifact: CapabilityArtifactIdentityV1Alpha1 = ARTIFACT) -> GovernedOperationBindingV1Alpha1:
    return GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=artifact,
        configuration_ref="governed_operation_configuration:action",
        authority="execute_action",
        grant_ref="authority_grant:action",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="governed_operation_configuration",
            product_id=PRODUCT,
            state_id="governed_operation_configuration:action",
            sequence=1,
            revision_id="revision:configuration:1",
            commit_receipt_id="governed_state_commit:configuration:1",
        ),
    )


def test_registry_resolves_only_the_complete_exact_artifact_identity() -> None:
    adapter = _Adapter()
    registry = BoundedActionAdapterRegistry((adapter,))

    assert registry.resolve(ARTIFACT) is adapter
    changed = CapabilityArtifactIdentityV1Alpha1.model_validate(
        {**ARTIFACT.model_dump(mode="python"), "implementation_version": "1.0.1"}
    )
    assert registry.resolve(changed) is None


def test_registry_rejects_duplicates_and_non_action_contracts() -> None:
    registry = BoundedActionAdapterRegistry((_Adapter(),))
    with pytest.raises(ActionCompositionError, match="already registered"):
        registry.register(_Adapter())

    class _WrongAdapter(_Adapter):
        artifact_identity = CapabilityArtifactIdentityV1Alpha1.model_validate(
            {
                **ARTIFACT.model_dump(mode="python"),
                "capability": "source_capture",
                "contract": "ace.core.source-adapter/v1alpha1",
            }
        )

    with pytest.raises(ActionCompositionError, match="bounded Core contract"):
        BoundedActionAdapterRegistry((_WrongAdapter(),))


def test_host_composition_requires_the_exact_explicitly_registered_adapter() -> None:
    service = build_governed_action_execution_service(
        store=object(),  # type: ignore[arg-type]
        authorizer=object(),  # type: ignore[arg-type]
        operation_binding=_binding(),
        adapters=BoundedActionAdapterRegistry((_Adapter(),)),
        clock=lambda: datetime.now(UTC),
    )
    assert isinstance(service, GovernedActionExecutionService)

    with pytest.raises(ActionCompositionError, match="not registered"):
        build_governed_action_execution_service(
            store=object(),  # type: ignore[arg-type]
            authorizer=object(),  # type: ignore[arg-type]
            operation_binding=_binding(),
            adapters=BoundedActionAdapterRegistry(),
            clock=lambda: datetime.now(UTC),
        )


def test_review_composition_wraps_the_same_store_and_exact_executor() -> None:
    store = object()
    executor = build_governed_action_execution_service(
        store=store,  # type: ignore[arg-type]
        authorizer=object(),  # type: ignore[arg-type]
        operation_binding=_binding(),
        adapters=BoundedActionAdapterRegistry((_Adapter(),)),
        clock=lambda: datetime.now(UTC),
    )

    service = build_governed_action_review_service(
        store=store,  # type: ignore[arg-type]
        executor=executor,
        clock=lambda: datetime.now(UTC),
    )

    assert isinstance(service, GovernedActionReviewService)
