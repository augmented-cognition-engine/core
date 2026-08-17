"""Shared builders for delegated headless governed-cognition acceptance tests.

Nothing here is production code. The builders seed exactly the pre-existing
governed material a real deployment would already hold: one registered SERVICE
principal, two human-delegated grants, and one active capability state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ace.application.agent_composition_runtime import TaskAuthenticationReceiptV1Alpha1
from ace.core.agent_composition import (
    AgentPrincipalV1Alpha1,
    AuthorityClass,
    ExactArtifactReferenceV1Alpha1,
    PrincipalKind,
    PrincipalLifecycle,
)
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import (
    AUTHORITY_GRANT_STATE_KIND,
    CAPABILITY_STATE_KIND,
    CapabilityArtifactIdentityV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.agent_governance import (
    AgentPrincipalLifecycleRevisionV1Alpha1,
    PrincipalLifecycleState,
)
from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionScopeV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
)
from core.engine.cognition.delegated_activation import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
    DelegatedCognitionActivationRequestV1Alpha1,
    DelegatedModelParticipantV1Alpha1,
    DelegatedServicePrincipalBindingV1Alpha1,
    delegated_scope_ref,
    derive_delegated_cognition_material,
)
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    ProposalSourceV1,
    ReviewActorV1,
)
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    GRANT_PAYLOAD_CONTRACT,
    CompositionAuthorityGrantMaterial,
    CompositionCapabilityStateMaterial,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
PRODUCT = "product:alpha"
DELEGATOR = "user:default"
SERVICE_ACTOR = "service:cognition-activator"
PRODUCER_ACTOR = "model:teacher"
POLICY_REF = "authority_policy:delegated-cognition-v1"
CONFIGURATION_REF = "cognition_activation_configuration:default"
REVIEW_GRANT_REF = "authority_grant:delegated-cognition-review"
ACTIVATION_GRANT_REF = "authority_grant:delegated-cognition-activation"
REPLAY_KEY = "delegated-activation:alpha-0001"
CAPTURE_REF = "capture:alpha-0001"
AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND = "agent_principal_lifecycle"

ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="governed_cognition_activation",
    contract="ace.core.cognition-activation/v1alpha1",
    implementation_id="host_delegated_cognition_adapter",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "b" * 64,
)
CAPABILITY_STATE_REF = capability_state_ref_for_artifact(ARTIFACT)


def service_principal(*, product_id: str = PRODUCT, principal_kind: PrincipalKind = PrincipalKind.SERVICE):
    return AgentPrincipalV1Alpha1(
        product_id=product_id,
        principal_key="delegated-cognition-activator",
        principal_kind=principal_kind,
        owner_ref=DELEGATOR,
        implementation_ref="implementation:delegated-cognition-activator@1.0.0",
        supported_protocol_versions=("ace.protocol.cognition-activation/v1alpha1",),
        lifecycle=PrincipalLifecycle.ACTIVE,
        lifecycle_revision=2,
    )


def governance_coordinate(principal: AgentPrincipalV1Alpha1) -> AgentGovernanceCoordinateV1Alpha1:
    return AgentGovernanceCoordinateV1Alpha1(
        product_id=principal.product_id,
        principal_key=principal.principal_key,
    )


def principal_binding(principal: AgentPrincipalV1Alpha1) -> DelegatedServicePrincipalBindingV1Alpha1:
    return DelegatedServicePrincipalBindingV1Alpha1.from_principal(
        principal,
        lifecycle_state_id=str(governance_coordinate(principal).governance_id),
    )


def principal_lifecycle(
    principal: AgentPrincipalV1Alpha1,
    *,
    state: PrincipalLifecycleState = PrincipalLifecycleState.ACTIVE,
    sequence: int = 2,
    prior_revision_id: str | None = "agent_principal_lifecycle_revision:seed",
    occurred_at: datetime = NOW,
) -> AgentPrincipalLifecycleRevisionV1Alpha1:
    return AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=governance_coordinate(principal),
        registration_snapshot=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(principal.principal_id),
            artifact_digest=str(principal.principal_digest),
            artifact_contract=principal.contract,
        ),
        registration_implementation_ref=principal.implementation_ref,
        registration_protocol_refs=tuple(sorted(principal.supported_protocol_versions)),
        state=state,
        sequence=sequence,
        prior_revision_id=prior_revision_id,
        approval_receipt_ref="approval:principal-lifecycle-activate",
        actor_ref=DELEGATOR,
        occurred_at=occurred_at,
    )


def grant_material(
    *,
    grant_ref: str,
    authority_class: AuthorityClass,
    operations: tuple[str, ...],
    scope_ref: str,
    principal_ref: str,
    product_id: str = PRODUCT,
    actor_ref: str = SERVICE_ACTOR,
    delegator_ref: str | None = DELEGATOR,
    policy_ref: str = POLICY_REF,
    lifecycle: str = "active",
    effective_at: datetime = NOW - timedelta(hours=1),
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    delegation_ceiling: tuple[AuthorityClass, ...] = (
        REVIEW_AUTHORITY_CLASS,
        ACTIVATION_AUTHORITY_CLASS,
    ),
) -> CompositionAuthorityGrantMaterial:
    material: dict[str, Any] = {
        "contract": GRANT_PAYLOAD_CONTRACT,
        "grant_ref": grant_ref,
        "product_id": product_id,
        "actor_ref": actor_ref,
        "participant_principal_ref": principal_ref,
        "delegator_ref": delegator_ref,
        "authority_class": authority_class,
        "operations": tuple(sorted(operations)),
        "scope_ref": scope_ref,
        "policy_ref": policy_ref,
        "lifecycle": lifecycle,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "revoked_at": revoked_at,
        "delegation_ceiling": delegation_ceiling,
    }
    provisional = CompositionAuthorityGrantMaterial(**material, grant_hash="0" * 64)
    grant_hash = canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"}))
    return CompositionAuthorityGrantMaterial(**material, grant_hash=grant_hash)


def capability_state(
    *,
    product_id: str = PRODUCT,
    artifact: CapabilityArtifactIdentityV1Alpha1 = ARTIFACT,
    lifecycle: str = "active",
    configuration_refs: tuple[str, ...] = (CONFIGURATION_REF,),
) -> CompositionCapabilityStateMaterial:
    return CompositionCapabilityStateMaterial(
        product_id=product_id,
        artifact=artifact,
        lifecycle=lifecycle,
        permitted_configuration_refs=configuration_refs,
    )


async def commit_state(
    store: Any,
    *,
    state_kind: str,
    state_id: str,
    payload_contract: str,
    payload: dict[str, Any],
    material_hash: str,
    revision_id: str,
    product_id: str = PRODUCT,
    sequence: int = 1,
    prior_revision_id: str | None = None,
    actor_ref: str = DELEGATOR,
    approval_actor_ref: str | None = None,
    resolved_grant: ResolvedAuthorityGrantV1 | None = None,
    committed_at: datetime = NOW,
) -> Any:
    subject = f"approval_subject:{state_kind}:{sequence}:{state_id}"
    revision = GovernedStateRevisionV1(
        state_kind=state_kind,
        product_id=product_id,
        state_id=state_id,
        sequence=sequence,
        revision_id=revision_id,
        material_hash=material_hash,
        prior_revision_id=prior_revision_id,
        approval_subject_ref=subject,
        payload_contract=payload_contract,
        payload=payload,
    )
    return await store.commit(
        GovernedStateCommitRequestV1(
            revision=revision,
            expected_head_revision_id=prior_revision_id,
            actor_ref=actor_ref,
            approval=ResolvedApprovalReceiptV1(
                receipt_ref=f"approval:{state_kind}:{sequence}:{canonical_hash(subject)[:16]}",
                product_id=product_id,
                subject_ref=subject,
                actor_ref=approval_actor_ref or actor_ref,
                receipt_hash=canonical_hash({"subject": subject, "sequence": sequence}),
                approved_at=committed_at,
            ),
            authority_grants=(resolved_grant,) if resolved_grant is not None else (),
            committed_at=committed_at,
        )
    )


def resolved_grant_for(grant: CompositionAuthorityGrantMaterial) -> ResolvedAuthorityGrantV1:
    return ResolvedAuthorityGrantV1(
        grant_ref=grant.grant_ref,
        product_id=grant.product_id,
        authority=grant.authority_class.value,
        grant_hash=grant.grant_hash,
        effective_at=grant.effective_at,
        expires_at=grant.expires_at,
    )


async def seed_principal(
    store: Any,
    principal: AgentPrincipalV1Alpha1,
    *,
    state: PrincipalLifecycleState = PrincipalLifecycleState.ACTIVE,
    product_id: str = PRODUCT,
) -> None:
    """Commit the suspended onboarding revision, then the requested state."""

    seed = principal_lifecycle(
        principal,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=1,
        prior_revision_id=None,
    )
    await commit_state(
        store,
        state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
        state_id=str(governance_coordinate(principal).governance_id),
        payload_contract=seed.contract,
        payload=seed.model_dump(mode="python"),
        material_hash=str(seed.lifecycle_revision_digest).removeprefix("sha256:"),
        revision_id=str(seed.lifecycle_revision_id),
        product_id=product_id,
        sequence=1,
    )
    current = principal_lifecycle(
        principal,
        state=state,
        sequence=2,
        prior_revision_id=str(seed.lifecycle_revision_id),
    )
    await commit_state(
        store,
        state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
        state_id=str(governance_coordinate(principal).governance_id),
        payload_contract=current.contract,
        payload=current.model_dump(mode="python"),
        material_hash=str(current.lifecycle_revision_digest).removeprefix("sha256:"),
        revision_id=str(current.lifecycle_revision_id),
        product_id=product_id,
        sequence=2,
        prior_revision_id=str(seed.lifecycle_revision_id),
    )


async def seed_grant(
    store: Any,
    grant: CompositionAuthorityGrantMaterial,
    *,
    sequence: int = 1,
    prior_revision_id: str | None = None,
    actor_ref: str = DELEGATOR,
    approval_actor_ref: str | None = None,
) -> str:
    material_hash = canonical_hash(grant.model_dump(mode="json"))
    revision_id = f"authority_grant_revision:{canonical_hash([grant.grant_ref, sequence])[:32]}"
    await commit_state(
        store,
        state_kind=AUTHORITY_GRANT_STATE_KIND,
        state_id=grant.grant_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=grant.model_dump(mode="python"),
        material_hash=material_hash,
        revision_id=revision_id,
        product_id=grant.product_id,
        sequence=sequence,
        prior_revision_id=prior_revision_id,
        actor_ref=actor_ref,
        approval_actor_ref=approval_actor_ref,
        resolved_grant=resolved_grant_for(grant),
    )
    return revision_id


async def seed_capability(
    store: Any,
    state: CompositionCapabilityStateMaterial,
    *,
    sequence: int = 1,
    prior_revision_id: str | None = None,
) -> None:
    payload = state.model_dump(mode="python")
    await commit_state(
        store,
        state_kind=CAPABILITY_STATE_KIND,
        state_id=capability_state_ref_for_artifact(state.artifact),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        payload=payload,
        material_hash=canonical_hash(state.model_dump(mode="json")),
        revision_id=f"capability_state_revision:{canonical_hash([state.artifact.artifact_digest, sequence])[:32]}",
        product_id=state.product_id,
        sequence=sequence,
        prior_revision_id=prior_revision_id,
    )


def build_proposal(
    *,
    product_id: str = PRODUCT,
    stable_key: str = "delegated_recipe",
    created_by_actor_id: str = PRODUCER_ACTOR,
    description: str = "Activate through a delegated headless service.",
    base_revision_id: str | None = None,
) -> CognitionProposalV1:
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(kind=OwnerKind.PRODUCT, namespace=product_id, provenance="task:teach"),
        stable_key=stable_key,
    )
    body = {
        "slug": stable_key,
        "name": stable_key.replace("_", " ").title(),
        "description": description,
        "domain_intelligences": ["testing"],
        "activation_signals": ["implement", "test", "delegate", "activation"],
        "archetype_affinity": {"executor": 1.0},
        "mode_affinity": {"reactive": 1.0},
        "recipe": {
            "phases": [
                {
                    "cognitive_function": "frame",
                    "instruments": [{"fallback_slug": "first-principles"}],
                    "min_depth": 1,
                    "output_schema": "framed_problem",
                }
            ]
        },
    }
    return CognitionProposalV1(
        target_identity=identity,
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id),
        intent="Preserve the accepted delegated framing.",
        sources=(
            ProposalSourceV1(
                source_id=CAPTURE_REF,
                source_kind="capture",
                content_hash=canonical_hash({"capture": CAPTURE_REF, "stable_key": stable_key}),
            ),
        ),
        base_revision_id=base_revision_id,
        body_schema_version=RECIPE_BODY_VERSION,
        draft_body=body,
        created_by=ReviewActorV1(actor_id=created_by_actor_id, actor_class=ActorClass.MODEL),
        created_at=NOW - timedelta(minutes=5),
    )


def model_participant() -> DelegatedModelParticipantV1Alpha1:
    return DelegatedModelParticipantV1Alpha1(
        participant_principal_ref="agent_principal:model-drafting-agent",
        participant_principal_digest="sha256:" + "c" * 64,
        definition_revision_ref="agent_definition_revision:drafting-v1",
        definition_revision_digest="sha256:" + "d" * 64,
        role_binding_ref="agent_binding_revision:drafting-v1",
        role_binding_digest="sha256:" + "e" * 64,
        run_ref="stage_run_receipt:drafting-0001",
    )


def build_request(
    proposal: CognitionProposalV1,
    principal: AgentPrincipalV1Alpha1,
    *,
    product_id: str = PRODUCT,
    expected_head_generation: int = 0,
    replay_key: str = REPLAY_KEY,
    policy_ref: str = POLICY_REF,
    review_grant_ref: str = REVIEW_GRANT_REF,
    activation_grant_ref: str = ACTIVATION_GRANT_REF,
    actor_ref: str = SERVICE_ACTOR,
    artifact: CapabilityArtifactIdentityV1Alpha1 = ARTIFACT,
    configuration_ref: str = CONFIGURATION_REF,
    participant: DelegatedModelParticipantV1Alpha1 | None = None,
    authenticated_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(minutes=30),
    overrides: dict[str, Any] | None = None,
) -> DelegatedCognitionActivationRequestV1Alpha1:
    binding = principal_binding(principal)
    _, revision, _ = derive_delegated_cognition_material(
        proposal,
        service_principal_ref=binding.principal_ref,
        expected_head_generation=expected_head_generation,
        replay_key=replay_key,
        reviewed_at=NOW,
    )
    expected_capability = capability_state(
        product_id=product_id,
        artifact=artifact,
        configuration_refs=(configuration_ref,),
    )
    capability_material_digest = f"sha256:{canonical_hash(expected_capability.model_dump(mode='json'))}"
    capability_head_ref = f"capability_state_revision:{canonical_hash([artifact.artifact_digest, 1])[:32]}"
    authentication = TaskAuthenticationReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        verification_policy_ref="jwt:ace-api-delegated-service:v1",
        authenticated_at=authenticated_at,
        expires_at=expires_at,
        credential_fingerprint=None,
    )
    fields: dict[str, Any] = {
        "product_id": product_id,
        "capture_ref": CAPTURE_REF,
        "capture_digest": f"sha256:{proposal.sources[0].content_hash}",
        "proposal_id": str(proposal.proposal_id),
        "proposal_hash": str(proposal.proposal_hash),
        "target_cognition_id": str(proposal.target_identity.cognition_id),
        "base_revision_id": proposal.base_revision_id,
        "expected_head_generation": expected_head_generation,
        "derived_revision_id": str(revision.revision_id),
        "derived_material_digest": f"sha256:{revision.material_hash}",
        "capability_artifact": artifact,
        "capability_artifact_ref": (f"capability_artifact:{canonical_hash(artifact.model_dump(mode='json'))[:32]}"),
        "capability_artifact_digest": artifact.artifact_digest,
        "capability_state_ref": capability_state_ref_for_artifact(artifact),
        "capability_state_digest": capability_material_digest,
        "capability_head_ref": capability_head_ref,
        "capability_head_digest": capability_material_digest,
        "configuration_ref": configuration_ref,
        "configuration_digest": f"sha256:{canonical_hash({'configuration_ref': configuration_ref})}",
        "policy_ref": policy_ref,
        "service_principal": binding,
        "review_grant_ref": review_grant_ref,
        "activation_grant_ref": activation_grant_ref,
        "authenticated_actor_ref": actor_ref,
        "authentication_receipt_ref": str(authentication.receipt_id),
        "authentication_receipt_digest": str(authentication.receipt_digest),
        "authenticated_at": authenticated_at,
        "authentication_expires_at": expires_at,
        "replay_key": replay_key,
        "model_participant": participant,
    }
    fields.update(overrides or {})
    fields["scope_ref"] = delegated_scope_ref(
        product_id=fields["product_id"],
        capture_ref=fields["capture_ref"],
        capture_digest=fields["capture_digest"],
        proposal_id=fields["proposal_id"],
        proposal_hash=fields["proposal_hash"],
        target_cognition_id=fields["target_cognition_id"],
        derived_revision_id=fields["derived_revision_id"],
        derived_material_digest=fields["derived_material_digest"],
        capability_artifact_ref=fields["capability_artifact_ref"],
        capability_artifact_digest=fields["capability_artifact_digest"],
        capability_state_ref=fields["capability_state_ref"],
        capability_state_digest=fields["capability_state_digest"],
        capability_head_ref=fields["capability_head_ref"],
        capability_head_digest=fields["capability_head_digest"],
        configuration_ref=fields["configuration_ref"],
        configuration_digest=fields["configuration_digest"],
        policy_ref=fields["policy_ref"],
        service_principal_ref=fields["service_principal"].principal_ref,
    )
    if overrides is not None and "scope_ref" in overrides:
        fields["scope_ref"] = overrides["scope_ref"]
    return DelegatedCognitionActivationRequestV1Alpha1(**fields)


async def seed_delegated_world(
    store: Any,
    *,
    request: DelegatedCognitionActivationRequestV1Alpha1,
    principal: AgentPrincipalV1Alpha1,
    principal_state: PrincipalLifecycleState = PrincipalLifecycleState.ACTIVE,
    review_grant: CompositionAuthorityGrantMaterial | None = None,
    activation_grant: CompositionAuthorityGrantMaterial | None = None,
    capability: CompositionCapabilityStateMaterial | None = None,
) -> None:
    """Commit the pre-existing principal, both grants, and the capability state."""

    await seed_principal(store, principal, state=principal_state, product_id=principal.product_id)
    await seed_grant(
        store,
        review_grant
        or grant_material(
            grant_ref=request.review_grant_ref,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operations=(REVIEW_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            product_id=request.product_id,
            actor_ref=request.authenticated_actor_ref,
            policy_ref=request.policy_ref,
        ),
    )
    await seed_grant(
        store,
        activation_grant
        or grant_material(
            grant_ref=request.activation_grant_ref,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            product_id=request.product_id,
            actor_ref=request.authenticated_actor_ref,
            policy_ref=request.policy_ref,
        ),
    )
    await seed_capability(store, capability or capability_state(product_id=request.product_id))
