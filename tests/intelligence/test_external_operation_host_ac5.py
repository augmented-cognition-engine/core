from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.external_operations import (
    DestinationDefinitionV1Alpha1,
    DestinationLifecycle,
    DestinationPolicyCoordinateV1Alpha1,
    DestinationPolicyKind,
    DestinationRevisionV1Alpha1,
    ExternalOperation,
    exact_external_reference,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from core.engine.core.external_operations import (
    DESTINATION_POLICY_PAYLOAD_CONTRACT,
    DESTINATION_POLICY_STATE_KIND,
    DESTINATION_REVISION_PAYLOAD_CONTRACT,
    DESTINATION_REVISION_STATE_KIND,
    EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT,
    EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND,
    DestinationPolicyStateMaterial,
    DestinationRevisionStateMaterial,
    ExternalOperationConfigurationMaterial,
    GovernedExternalOperationAuthorityError,
    GovernedExternalOperationAuthorityResolver,
)

NOW = datetime(2026, 8, 12, 18, tzinfo=UTC)
PRODUCT = "product:host-ac5"
ACTOR = "actor:host-ac5"
RECIPIENT = "recipient:host-ac5"


def _head(kind: str, state_id: str) -> GovernedStateHeadPreconditionV1Alpha1:
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=1,
        revision_id=f"revision:{kind}:{state_id}",
        commit_receipt_id=f"commit:{kind}:{state_id}",
    )


def _destination() -> DestinationRevisionV1Alpha1:
    definition = DestinationDefinitionV1Alpha1(
        product_id=PRODUCT,
        destination_key="host-reference",
        adapter_contract="ace.core.external-destination-adapter/v1alpha1",
        protocol_refs=("protocol:host-v1",),
        capability_refs=("delivery", "effect"),
        recipient_binding_kind="opaque_recipient_ref",
    )
    return DestinationRevisionV1Alpha1(
        definition=exact_external_reference(definition),
        sequence=1,
        lifecycle=DestinationLifecycle.ACTIVE,
        policies=tuple(
            DestinationPolicyCoordinateV1Alpha1(
                kind=kind,
                policy_ref=f"policy:{kind.value}",
                state_id=f"destination_policy:{kind.value}",
                material_digest="sha256:" + f"{index + 1:x}" * 64,
            )
            for index, kind in enumerate(DestinationPolicyKind)
        ),
        revised_at=NOW - timedelta(minutes=1),
    )


class _RuntimeUse:
    def __init__(self, artifact, binding, destination) -> None:
        self.artifact = artifact
        self.binding = binding
        self.destination = destination
        self.materials = {}
        self._put(
            EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND,
            binding.configuration_ref,
            EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT,
            binding.model_dump(mode="python"),
        )
        self._put(
            DESTINATION_REVISION_STATE_KIND,
            str(destination.revision_id),
            DESTINATION_REVISION_PAYLOAD_CONTRACT,
            DestinationRevisionStateMaterial(
                product_id=PRODUCT,
                destination_revision=destination,
                lifecycle=DestinationLifecycle.ACTIVE,
            ).model_dump(mode="python"),
        )
        for coordinate in destination.policies:
            self._put(
                DESTINATION_POLICY_STATE_KIND,
                coordinate.state_id,
                DESTINATION_POLICY_PAYLOAD_CONTRACT,
                DestinationPolicyStateMaterial(
                    product_id=PRODUCT,
                    destination_revision_id=str(destination.revision_id),
                    kind=coordinate.kind,
                    policy_ref=coordinate.policy_ref,
                    material_digest=coordinate.material_digest,
                    lifecycle="active",
                    tenant_ref=PRODUCT,
                    principal_ref=ACTOR,
                    recipient_ref=RECIPIENT,
                    effective_at=NOW - timedelta(minutes=1),
                    expires_at=NOW + timedelta(hours=1),
                ).model_dump(mode="python"),
            )
        self._put("capability_state", capability_state_ref_for_artifact(artifact), "capability", {})
        self._put("authority_grant", binding.grant_ref, "grant", {})

    def _put(self, kind, state_id, contract, payload) -> None:
        self.materials[(kind, state_id)] = SimpleNamespace(
            revision=SimpleNamespace(payload_contract=contract, payload=payload),
            head=_head(kind, state_id),
        )

    async def _load(self, *, state_kind, product_id, state_id):
        if product_id != PRODUCT or (state_kind, state_id) not in self.materials:
            raise RuntimeError("missing")
        return self.materials[(state_kind, state_id)]

    async def resolve_capability_use(
        self,
        *,
        context,
        use_subject_ref,
        use_subject_digest,
        operation,
        artifact,
        capability_state_ref,
        configuration_ref,
        evaluated_at,
    ):
        return CapabilityUseReceiptV1Alpha1(
            product_id=PRODUCT,
            actor_ref=ACTOR,
            authenticated_context=context,
            use_subject_ref=use_subject_ref,
            use_subject_digest=use_subject_digest,
            operation=operation,
            artifact=artifact,
            capability_state_ref=capability_state_ref,
            configuration_ref=configuration_ref,
            evaluated_at=evaluated_at,
            resolved_at=evaluated_at,
            state_head_precondition=_head("capability_state", capability_state_ref),
        )

    async def resolve_authority_use(
        self,
        *,
        context,
        use_subject_ref,
        use_subject_digest,
        operation,
        authority,
        grant_ref,
        evaluated_at,
    ):
        return AuthorityUseReceiptV1Alpha1(
            product_id=PRODUCT,
            actor_ref=ACTOR,
            authenticated_context=context,
            use_subject_ref=use_subject_ref,
            use_subject_digest=use_subject_digest,
            operation=operation,
            authority=authority,
            grant_ref=grant_ref,
            grant_hash="9" * 64,
            evaluated_at=evaluated_at,
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=_head("authority_grant", grant_ref),
        )


def _stack():
    artifact = CapabilityArtifactIdentityV1Alpha1(
        capability="governed_external_operations",
        contract="ace.core.external-destination-adapter/v1alpha1",
        implementation_id="host_reference",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "8" * 64,
    )
    destination = _destination()
    binding = ExternalOperationConfigurationMaterial(
        product_id=PRODUCT,
        operation=ExternalOperation.DELIVERY,
        configuration_ref="configuration:delivery",
        artifact=artifact,
        grant_ref="grant:delivery",
        destination_revision_id=str(destination.revision_id),
        policy_state_ids=tuple(item.state_id for item in destination.policies),
        lifecycle="active",
    )
    runtime = _RuntimeUse(artifact, binding, destination)
    resolver = GovernedExternalOperationAuthorityResolver(runtime_use=runtime, bindings=(binding,))
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication:host-ac5",
        authentication_receipt_digest="sha256:" + "7" * 64,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    return runtime, resolver, context, destination


async def test_host_resolver_binds_destination_and_all_six_current_policy_heads() -> None:
    _, resolver, context, destination = _stack()
    subject = ExactArtifactReferenceV1Alpha1(
        artifact_id="destination_delivery_intent:host",
        artifact_digest="sha256:" + "6" * 64,
        artifact_contract="ace.core.destination-delivery-intent/v1alpha1",
    )
    receipt = await resolver.resolve(
        authenticated_context=context,
        operation=ExternalOperation.DELIVERY,
        use_subject=subject,
        destination_revision=destination,
        recipient_ref=RECIPIENT,
        evaluated_at=NOW,
    )
    assert receipt.operation is ExternalOperation.DELIVERY
    assert receipt.destination_revision == exact_external_reference(destination)
    assert len(receipt.current_heads) == 10
    assert {item.state_kind for item in receipt.current_heads} >= {
        DESTINATION_REVISION_STATE_KIND,
        DESTINATION_POLICY_STATE_KIND,
        "capability_state",
        "authority_grant",
        EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND,
    }
    assert receipt.reusable_authority is False


@pytest.mark.parametrize("policy_kind", list(DestinationPolicyKind))
async def test_each_stale_or_revoked_destination_policy_fails_closed(policy_kind) -> None:
    runtime, resolver, context, destination = _stack()
    coordinate = next(item for item in destination.policies if item.kind is policy_kind)
    material = runtime.materials[(DESTINATION_POLICY_STATE_KIND, coordinate.state_id)]
    material.revision.payload = {
        **material.revision.payload,
        "lifecycle": "revoked",
    }
    with pytest.raises(GovernedExternalOperationAuthorityError, match="policy failed"):
        await resolver.resolve(
            authenticated_context=context,
            operation=ExternalOperation.DELIVERY,
            use_subject=ExactArtifactReferenceV1Alpha1(
                artifact_id="destination_delivery_intent:host",
                artifact_digest="sha256:" + "6" * 64,
                artifact_contract="ace.core.destination-delivery-intent/v1alpha1",
            ),
            destination_revision=destination,
            recipient_ref=RECIPIENT,
            evaluated_at=NOW,
        )


async def test_foreign_recipient_and_operation_fail_closed() -> None:
    _, resolver, context, destination = _stack()
    subject = ExactArtifactReferenceV1Alpha1(
        artifact_id="destination_delivery_intent:host",
        artifact_digest="sha256:" + "6" * 64,
        artifact_contract="ace.core.destination-delivery-intent/v1alpha1",
    )
    with pytest.raises(GovernedExternalOperationAuthorityError, match="policy failed"):
        await resolver.resolve(
            authenticated_context=context,
            operation=ExternalOperation.DELIVERY,
            use_subject=subject,
            destination_revision=destination,
            recipient_ref="recipient:foreign",
            evaluated_at=NOW,
        )
    with pytest.raises(GovernedExternalOperationAuthorityError, match="configuration"):
        await resolver.resolve(
            authenticated_context=context,
            operation=ExternalOperation.EXTERNAL_EFFECT,
            use_subject=subject,
            destination_revision=destination,
            recipient_ref=RECIPIENT,
            evaluated_at=NOW,
        )
