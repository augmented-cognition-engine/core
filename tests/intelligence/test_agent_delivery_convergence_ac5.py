from __future__ import annotations

import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

from ace.application.agent_composition_runtime import (
    CompositionAuthorityResolutionReceiptV1Alpha1,
    ReasoningCompositionRuntimeAuthorityBundle,
    exact_reference,
)
from ace.application.agent_governance_runtime import (
    GovernedAgentPreExecutionError,
    GovernedAgentPreExecutionResolver,
)
from ace.application.external_agent import ExternalAgentHandshakeService
from ace.core.agent_composition import (
    AuthorityClass,
    AuthorityCoordinateV1Alpha1,
    CompositionBudgetV1Alpha1,
    CompositionNodeKind,
    CompositionNodeV1Alpha1,
    CompositionParticipantV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    ParticipantKind,
    StageRunManifestV1Alpha1,
    TaskCompositionPlanV1Alpha1,
)
from ace.core.reasoning import ReasoningExecutionBindingV1Alpha1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.agent_composition import LifecycleStage
from ace.intelligence.contracts.agent_governance import PrincipalLifecycleState
from ace.intelligence.contracts.external_agent import (
    ExternalAgentHandshakeDisposition,
    ExternalAgentProtocolIdentityV1Alpha1,
)


def _ac4_module():
    path = Path(__file__).with_name("test_agent_onboarding_governance_ac4.py")
    spec = importlib.util.spec_from_file_location("ac4_convergence_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _head(kind: str, product: str, state_id: str) -> GovernedStateHeadPreconditionV1Alpha1:
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=kind,
        product_id=product,
        state_id=state_id,
        sequence=1,
        revision_id=f"revision:{kind}",
        commit_receipt_id=f"commit:{kind}",
    )


class _AC2PreExecutionPort:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve_pre_execution(self, *, authenticated_context, manifest, evaluated_at):
        self.calls += 1
        artifact = CapabilityArtifactIdentityV1Alpha1(
            capability="structured_reasoning",
            contract="ace.core.reasoning-provider/v1alpha1",
            implementation_id="convergence_reasoning",
            implementation_version="1.0.0",
            artifact_digest="sha256:" + "1" * 64,
        )
        capability_head = _head("capability_state", manifest.product_id, capability_state_ref_for_artifact(artifact))
        grant_head = _head("authority_grant", manifest.product_id, manifest.authority[0].grant_ref)
        configuration_head = _head("reasoning_configuration", manifest.product_id, "configuration:ac5")
        binding = ReasoningExecutionBindingV1Alpha1(
            product_id=manifest.product_id,
            artifact=artifact,
            configuration_ref="configuration:ac5",
            authority=manifest.authority[0].authority_class.value,
            grant_ref=manifest.authority[0].grant_ref,
            state_head_precondition=configuration_head,
        )
        capability = CapabilityUseReceiptV1Alpha1(
            product_id=manifest.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject_ref=str(manifest.manifest_id),
            use_subject_digest=str(manifest.manifest_digest),
            operation="structured_reasoning",
            artifact=artifact,
            capability_state_ref=capability_state_ref_for_artifact(artifact),
            configuration_ref="configuration:ac5",
            evaluated_at=evaluated_at,
            resolved_at=evaluated_at,
            state_head_precondition=capability_head,
        )
        authority = AuthorityUseReceiptV1Alpha1(
            product_id=manifest.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject_ref=str(manifest.manifest_id),
            use_subject_digest=str(manifest.manifest_digest),
            operation="structured_reasoning",
            authority=manifest.authority[0].authority_class.value,
            grant_ref=manifest.authority[0].grant_ref,
            grant_hash="2" * 64,
            evaluated_at=evaluated_at,
            expires_at=authenticated_context.expires_at,
            state_head_precondition=grant_head,
        )
        heads = tuple(sorted((capability_head, grant_head, configuration_head), key=lambda item: item.state_kind))
        receipt = CompositionAuthorityResolutionReceiptV1Alpha1(
            phase="pre_execution",
            product_id=manifest.product_id,
            actor_ref=authenticated_context.actor_ref,
            participant_principal_ref=manifest.authority[0].principal_ref,
            use_subject=exact_reference(manifest),
            authentication_receipt_ref=authenticated_context.authentication_receipt_ref,
            execution_binding=exact_reference(binding),
            capability_use=exact_reference(capability),
            authority_use=(exact_reference(authority),),
            authority_coordinates=manifest.authority,
            current_heads=heads,
            evaluated_at=evaluated_at,
        )
        return ReasoningCompositionRuntimeAuthorityBundle(
            authenticated_context=authenticated_context,
            execution_binding=binding,
            capability_use=capability,
            authority_use=(authority,),
            authority_coordinates=manifest.authority,
            current_heads=heads,
            resolution_receipt=receipt,
        )


async def test_exact_ac4_replacement_enters_only_a_fresh_plan_and_ac2_pre_execution() -> None:
    ac4 = _ac4_module()
    stack = await ac4._active_stack(ac4.PrincipalKind.MODEL_AGENT)
    compatibility, conformance, dry_run = ac4._evidence(stack)
    activation, _ = await stack["service"].activate(
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        compatibility=compatibility,
        conformance=conformance,
        dry_run=dry_run,
        actor_ref="human:admin",
        admin_grant_ref="grant:admin",
        activated_at=ac4.NOW + timedelta(minutes=5),
    )
    legacy = ExactArtifactReferenceV1Alpha1(
        artifact_id="compatibility_participant:ac3-model",
        artifact_digest="sha256:" + "3" * 64,
        artifact_contract="ace.application.lifecycle-participant-reference/v1alpha1",
    )
    replacement, _ = await stack["service"].replace_compatibility_participant(
        compatibility_participant=legacy,
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        activation=activation,
        replaced_at=ac4.NOW + timedelta(minutes=6),
    )
    coordinate = AuthorityCoordinateV1Alpha1(
        product_id=ac4.PRODUCT,
        principal_ref=stack["registration"].artifact_id,
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        grant_ref="grant:derive",
        scope_ref="scope:bounded-record",
        policy_ref="policy:bounded-record",
        expires_at=ac4.NOW + timedelta(hours=1),
    )
    participant = CompositionParticipantV1Alpha1(
        composition_participant_id="governed_participant:new-plan",
        participant_kind=ParticipantKind.MODEL_AGENT,
        participant_ref=stack["registration"].artifact_id,
        definition_revision=replacement.definition,
        role_binding=replacement.binding,
        authority=(coordinate,),
    )
    created_at = ac4.NOW + timedelta(minutes=7)
    plan = TaskCompositionPlanV1Alpha1(
        product_id=ac4.PRODUCT,
        actor_ref="human:operator",
        session_ref="session:ac5",
        task_ref="task:ac5",
        objective="Run one newly governed participant.",
        stage_id=LifecycleStage.DELIBERATE.value,
        classifier_revision_ref="classifier:ac5",
        routing_revision_ref="routing:ac5",
        policy_revision_ref="policy:ac5",
        composer_revision_ref="composer:ac5",
        participants=(participant,),
        nodes=(
            CompositionNodeV1Alpha1(
                node_id="node:governed",
                node_kind=CompositionNodeKind.EXECUTION,
                composition_participant_id=participant.composition_participant_id,
                output_contracts=("example.output/v1",),
            ),
        ),
        orchestration_pattern="sequential",
        expected_output_contracts=("example.output/v1",),
        aggregate_budget=CompositionBudgetV1Alpha1(max_items=1, max_calls=1, max_tokens=128),
        context_request_ref="context:ac5",
        failure_policy_ref="failure:closed",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=20),
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=ac4.PRODUCT,
        actor_ref="human:operator",
        authentication_receipt_ref="authentication:ac5",
        authentication_receipt_digest="sha256:" + "4" * 64,
        authenticated_at=created_at - timedelta(minutes=1),
        expires_at=created_at + timedelta(minutes=30),
    )
    runtime = _AC2PreExecutionPort()
    # The manifest binding is replaced with the exact host binding produced by the fake AC2 port below.
    artifact = CapabilityArtifactIdentityV1Alpha1(
        capability="structured_reasoning",
        contract="ace.core.reasoning-provider/v1alpha1",
        implementation_id="convergence_reasoning",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "1" * 64,
    )
    config_head = _head("reasoning_configuration", ac4.PRODUCT, "configuration:ac5")
    execution_binding = ReasoningExecutionBindingV1Alpha1(
        product_id=ac4.PRODUCT,
        artifact=artifact,
        configuration_ref="configuration:ac5",
        authority=AuthorityClass.DERIVE_PROPOSE.value,
        grant_ref="grant:derive",
        state_head_precondition=config_head,
    )
    manifest = StageRunManifestV1Alpha1(
        plan=exact_reference(plan),
        product_id=ac4.PRODUCT,
        stage_id=LifecycleStage.DELIBERATE.value,
        node_id="node:governed",
        composition_participant_id=participant.composition_participant_id,
        definition_revision=replacement.definition,
        role_binding=replacement.binding,
        task_ref="task:ac5",
        invocation_key="invocation:ac5",
        instruction_resolution=ExactArtifactReferenceV1Alpha1(
            artifact_id="instruction:ac5",
            artifact_digest="sha256:" + "5" * 64,
            artifact_contract="ace.intelligence.instruction-resolution-receipt/v1alpha1",
        ),
        instruction_layer_refs=(
            ExactArtifactReferenceV1Alpha1(
                artifact_id="instruction-layer:ac5",
                artifact_digest="sha256:" + "6" * 64,
                artifact_contract="ace.intelligence.instruction-contribution/v1alpha1",
            ),
        ),
        context_manifest=ExactArtifactReferenceV1Alpha1(
            artifact_id="context-manifest:ac5",
            artifact_digest="sha256:" + "7" * 64,
            artifact_contract="ace.core.context-manifest/v1alpha1",
        ),
        authority=(coordinate,),
        execution_binding=exact_reference(execution_binding),
        output_contracts=("example.output/v1",),
        budget=CompositionBudgetV1Alpha1(max_items=1, max_calls=1, max_tokens=128),
        cancellation_ref="cancel:ac5",
        retry_ref="retry:ac5",
        idempotency_key="idempotency:ac5",
        degraded_policy_ref="degraded:ac5",
        escalation_policy_ref="escalation:ac5",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=20),
    )
    resolver = GovernedAgentPreExecutionResolver(governance_service=stack["service"], runtime_authority=runtime)
    admission, bundle = await resolver.resolve(
        authenticated_context=context,
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        plan=plan,
        manifest=manifest,
        activation=activation,
        replacement=replacement,
        evaluated_at=created_at + timedelta(seconds=1),
    )
    assert runtime.calls == 1
    assert len(admission.governance_heads) == 5
    assert admission.new_plan == exact_reference(plan)
    assert admission.historical_compatibility_participant == legacy
    assert admission.rewrites_history is False
    assert admission.carries_authority_forward is False
    assert admission.reusable_authority is False
    assert bundle.resolution_receipt.phase == "pre_execution"

    stale_plan = plan.model_copy(update={"created_at": replacement.replaced_at - timedelta(seconds=1)})
    with pytest.raises(GovernedAgentPreExecutionError, match="failed exact revalidation"):
        await resolver.resolve(
            authenticated_context=context,
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            plan=stale_plan,
            manifest=manifest,
            activation=activation,
            replacement=replacement,
            evaluated_at=created_at + timedelta(seconds=2),
        )


async def test_external_agent_handshake_proves_compatibility_but_never_authority() -> None:
    ac4 = _ac4_module()
    stack = await ac4._active_stack(ac4.PrincipalKind.MODEL_AGENT)
    protocol = ExternalAgentProtocolIdentityV1Alpha1(
        protocol_ref=stack["principal"].supported_protocol_versions[0],
        participant_identity_contract=stack["principal"].contract,
        capability_contract_refs=("example.output/v1",),
    )
    service = ExternalAgentHandshakeService(governance_service=stack["service"])
    compatible = await service.handshake(
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        protocol=protocol,
        offered_protocol_ref=protocol.protocol_ref,
        offered_capability_refs=("example.output/v1",),
        checked_at=ac4.NOW + timedelta(minutes=5),
    )
    assert compatible.disposition is ExternalAgentHandshakeDisposition.COMPATIBLE
    assert compatible.installation_grants_authority is False
    assert compatible.handshake_grants_execution is False
    assert compatible.handshake_grants_delivery is False
    assert compatible.conformance_grants_authority is False
    assert compatible.reusable_authority is False
    unsupported = await service.handshake(
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        protocol=protocol,
        offered_protocol_ref="ace.agent.unsupported/v9",
        offered_capability_refs=("example.output/v1",),
        checked_at=ac4.NOW + timedelta(minutes=6),
    )
    assert unsupported.disposition is ExternalAgentHandshakeDisposition.UNSUPPORTED_PROTOCOL

    suspended = ac4.AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        registration_implementation_ref=stack["principal"].implementation_ref,
        registration_protocol_refs=stack["principal"].supported_protocol_versions,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=3,
        prior_revision_id=str(stack["principal_active"].lifecycle_revision_id),
        approval_receipt_ref="approval:principal:suspend",
        actor_ref="human:admin",
        occurred_at=ac4.NOW + timedelta(minutes=7),
    )
    await stack["service"].admit_principal_lifecycle(
        suspended,
        registration=stack["principal"],
        admin_grant_ref="grant:admin",
        committed_at=ac4.NOW + timedelta(minutes=7),
    )
    ineligible = await service.handshake(
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        protocol=protocol,
        offered_protocol_ref=protocol.protocol_ref,
        offered_capability_refs=("example.output/v1",),
        checked_at=ac4.NOW + timedelta(minutes=8),
    )
    assert ineligible.disposition is ExternalAgentHandshakeDisposition.INELIGIBLE_PARTICIPANT
