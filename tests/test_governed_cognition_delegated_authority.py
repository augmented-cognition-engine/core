"""Slice 7 delegated governed-cognition authority matrix.

Every case here resolves current authority only from pre-existing governed
state.  Nothing in this module can issue, mint, widen, renew, or transfer a
grant, and no case reaches a cognition revision, head, or activation write.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ace.core.agent_composition import (
    AgentPrincipalV1Alpha1,
    AuthorityClass,
    PrincipalKind,
    PrincipalLifecycle,
)
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
)
from ace.intelligence.contracts.agent_governance import PrincipalLifecycleState
from core.engine.cognition.delegated_activation import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    CONSEQUENCE_CLASS,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
    DelegatedCognitionActivationRequestV1Alpha1,
    DelegatedCognitionAuthorityError,
    DelegatedDenyCode,
    delegated_scope_ref,
    require_distinct_producer,
)
from core.engine.core.agent_composition_runtime import GovernedStateRuntimeUseResolver
from core.engine.core.cognition_delegated_authority import (
    PERMITTED_DELEGATION_CEILING,
    DelegatedCognitionAuthority,
)
from tests.delegated_cognition_support import (
    ACTIVATION_GRANT_REF,
    ARTIFACT,
    CONFIGURATION_REF,
    NOW,
    PRODUCT,
    REVIEW_GRANT_REF,
    SERVICE_ACTOR,
    build_proposal,
    build_request,
    capability_state,
    grant_material,
    model_participant,
    principal_binding,
    seed_capability,
    seed_delegated_world,
    seed_grant,
    service_principal,
)


class InMemoryGovernedStateStore:
    """JSON-shaped in-memory mirror of the durable governed-state adapter."""

    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions: dict[tuple[str, str], GovernedStateRevisionV1] = {}
        self.receipts: dict[tuple[str, str], object] = {}

    async def commit(self, request: GovernedStateCommitRequestV1):
        receipt = request.receipt()
        revision = request.revision
        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        self.revisions[(revision.product_id, revision.revision_id)] = type(revision).model_validate_json(
            revision.model_dump_json()
        )
        self.receipts[(revision.product_id, str(receipt.receipt_id))] = type(receipt).model_validate_json(
            receipt.model_dump_json()
        )
        self.heads[(revision.state_kind, revision.product_id, revision.state_id)] = head
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))


def _authority(store: InMemoryGovernedStateStore) -> DelegatedCognitionAuthority:
    return DelegatedCognitionAuthority(runtime_use=GovernedStateRuntimeUseResolver(governed_state=store))


async def _resolve(
    store: InMemoryGovernedStateStore,
    request: DelegatedCognitionActivationRequestV1Alpha1,
    principal: AgentPrincipalV1Alpha1,
    *,
    operation: str = ACTIVATION_OPERATION,
    evaluated_at=NOW,
):
    return await _authority(store).resolve(
        request,
        principal=principal,
        operation=operation,
        evaluated_at=evaluated_at,
    )


async def _world(**seed_kwargs):
    store = InMemoryGovernedStateStore()
    principal = seed_kwargs.pop("principal", None) or service_principal()
    proposal = seed_kwargs.pop("proposal", None) or build_proposal()
    request = seed_kwargs.pop("request", None) or build_request(proposal, principal)
    await seed_delegated_world(store, request=request, principal=principal, **seed_kwargs)
    return store, request, principal, proposal


def _denies(code: DelegatedDenyCode):
    return pytest.raises(DelegatedCognitionAuthorityError, match=code.value)


# --------------------------------------------------------------------------
# The accepting case and its exact evidence shape.
# --------------------------------------------------------------------------


async def test_active_delegated_service_resolves_both_grants_and_capability() -> None:
    store, request, principal, _ = await _world()

    resolved = await _resolve(store, request, principal)

    assert resolved.review_evidence.authority_class is REVIEW_AUTHORITY_CLASS
    assert resolved.review_evidence.operation == REVIEW_OPERATION
    assert resolved.activation_evidence.authority_class is ACTIVATION_AUTHORITY_CLASS
    assert resolved.activation_evidence.operation == ACTIVATION_OPERATION
    # Both grants share one content-derived scope and one policy.
    assert resolved.review_evidence.scope_ref == resolved.activation_evidence.scope_ref == request.scope_ref
    assert resolved.review_evidence.policy_ref == resolved.activation_evidence.policy_ref == request.policy_ref
    assert resolved.review_evidence.grant_ref != resolved.activation_evidence.grant_ref
    # `load_grant` and `resolve_authority_use` observed the same governed head.
    assert resolved.review_use.state_head_precondition.state_id == REVIEW_GRANT_REF
    assert resolved.activation_use.state_head_precondition.state_id == ACTIVATION_GRANT_REF
    assert resolved.review_use.grant_hash == resolved.review_evidence.grant_hash
    # Four heads participate in the activation commit boundary.
    kinds = sorted(item.state_kind for item in resolved.preconditions)
    assert kinds == ["agent_principal_lifecycle", "authority_grant", "authority_grant", "capability_state"]
    # Historical evidence is never bearer authority.
    assert resolved.review_use.reusable_authority is False
    assert resolved.capability_use.reusable_authority is False


async def test_request_envelope_forbids_extra_fields_and_binds_content_identity() -> None:
    _, request, _, _ = await _world()

    with pytest.raises(ValueError):
        DelegatedCognitionActivationRequestV1Alpha1.model_validate(
            {**request.model_dump(mode="json"), "escalate": True}
        )
    assert request.consequence_class == CONSEQUENCE_CLASS
    assert request.requested_disposition == "approve"


async def test_altered_request_field_breaks_its_content_derived_identity() -> None:
    _, request, _, _ = await _world()
    tampered = request.model_dump(mode="json")
    tampered["expected_head_generation"] = 5

    with pytest.raises(ValueError):
        DelegatedCognitionActivationRequestV1Alpha1.model_validate(tampered)


# --------------------------------------------------------------------------
# Principal identity: SERVICE only, active, registered, product-scoped.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [PrincipalKind.MODEL_AGENT, PrincipalKind.EXTERNAL_AGENT],
)
async def test_raw_model_or_external_principal_is_denied(kind) -> None:
    principal = service_principal(principal_kind=kind)
    proposal = build_proposal()
    request = build_request(proposal, principal)
    store, request, principal, _ = await _world(principal=principal, proposal=proposal, request=request)

    with _denies(DelegatedDenyCode.PRINCIPAL_NOT_SERVICE):
        await _resolve(store, request, principal)


async def test_missing_principal_head_is_denied() -> None:
    store, request, principal, _ = await _world()
    store.heads.pop(("agent_principal_lifecycle", PRODUCT, request.service_principal.lifecycle_state_id))

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, principal)


@pytest.mark.parametrize(
    "state",
    [PrincipalLifecycleState.SUSPENDED, PrincipalLifecycleState.REVOKED, PrincipalLifecycleState.RETIRED],
)
async def test_inactive_principal_is_denied(state) -> None:
    store, request, principal, _ = await _world(principal_state=state)

    with _denies(DelegatedDenyCode.PRINCIPAL_INACTIVE):
        await _resolve(store, request, principal)


async def test_wrong_principal_snapshot_is_denied() -> None:
    store, request, principal, _ = await _world()
    impostor = principal.model_copy(update={"principal_id": None, "principal_digest": None, "owner_ref": "user:other"})
    impostor = AgentPrincipalV1Alpha1.model_validate(impostor.model_dump(mode="python"))

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, impostor)


async def test_retired_registration_lifecycle_flag_is_denied() -> None:
    store, request, principal, _ = await _world()
    stale = AgentPrincipalV1Alpha1.model_validate(
        {
            **principal.model_dump(mode="python"),
            "lifecycle": PrincipalLifecycle.RETIRED,
            "principal_id": None,
            "principal_digest": None,
        }
    )

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, stale)


async def test_cross_product_principal_is_denied() -> None:
    principal = service_principal(product_id="product:beta")
    proposal = build_proposal()
    request = build_request(proposal, service_principal())
    store, _, _, _ = await _world()

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, principal)


# --------------------------------------------------------------------------
# Grants: exact, pre-existing, delegated, never self-minted.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("grant_ref_field", ["review_grant_ref", "activation_grant_ref"])
async def test_missing_grant_head_is_denied(grant_ref_field) -> None:
    store, request, principal, _ = await _world()
    store.heads.pop(("authority_grant", PRODUCT, getattr(request, grant_ref_field)))

    with _denies(DelegatedDenyCode.GRANT_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_revoked_grant_is_denied() -> None:
    store, request, principal, proposal = await _world()
    await seed_grant(
        store,
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            lifecycle="revoked",
            revoked_at=NOW - timedelta(minutes=1),
        ),
        sequence=2,
        prior_revision_id=store.heads[("authority_grant", PRODUCT, ACTIVATION_GRANT_REF)].revision_id,
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_expired_grant_is_denied() -> None:
    store, request, principal, _ = await _world(
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=build_request(build_proposal(), service_principal()).scope_ref,
            principal_ref=str(service_principal().principal_id),
            effective_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(minutes=5),
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_grant_that_is_not_yet_effective_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            effective_at=NOW + timedelta(hours=1),
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_wrong_scope_grant_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref="delegated_cognition_scope:" + "0" * 32,
            principal_ref=request.service_principal.principal_ref,
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_wrong_policy_grant_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        review_grant=grant_material(
            grant_ref=REVIEW_GRANT_REF,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operations=(REVIEW_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            policy_ref="authority_policy:some-other-policy",
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_wrong_authority_class_grant_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=AuthorityClass.DECIDE_APPROVE,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_wrong_operation_grant_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=("activate_some_other_thing",),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_grant_with_extra_operations_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION, "activate_anything_else"),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_grant_for_another_principal_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref="agent_principal:some-other-service",
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_grant_for_another_actor_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            actor_ref="service:some-other-runner",
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_undelegated_grant_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            delegator_ref=None,
            delegation_ceiling=(),
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_SELF_ISSUED):
        await _resolve(store, request, principal)


async def test_beneficiary_self_delegated_grant_is_denied() -> None:
    principal = service_principal()
    request = build_request(build_proposal(), principal)
    store, request, principal, _ = await _world(
        principal=principal,
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            delegator_ref=str(principal.principal_id),
        ),
    )

    with _denies(DelegatedDenyCode.GRANT_SELF_ISSUED):
        await _resolve(store, request, principal)


async def test_beneficiary_committed_grant_is_denied() -> None:
    """The beneficiary cannot self-mint, self-renew, self-transfer, or self-widen."""

    store = InMemoryGovernedStateStore()
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    await seed_delegated_world(store, request=request, principal=principal)
    await seed_grant(
        store,
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
        ),
        sequence=2,
        prior_revision_id=store.heads[("authority_grant", PRODUCT, ACTIVATION_GRANT_REF)].revision_id,
        # The renewal is committed by the beneficiary's own authenticated actor.
        actor_ref=SERVICE_ACTOR,
    )

    with _denies(DelegatedDenyCode.GRANT_SELF_ISSUED):
        await _resolve(store, request, principal)


async def test_core_refuses_a_grant_commit_whose_approval_actor_differs() -> None:
    """Commit and approval actor are already one identity at the Core boundary.

    This is why ``require_delegated_lineage`` can compare the durable commit
    actor to the declared delegator and reject anything else.
    """

    store = InMemoryGovernedStateStore()
    principal = service_principal()
    request = build_request(build_proposal(), principal)
    await seed_delegated_world(store, request=request, principal=principal)

    with pytest.raises(ValueError, match="approval actor must equal the committing actor"):
        await seed_grant(
            store,
            grant_material(
                grant_ref=REVIEW_GRANT_REF,
                authority_class=REVIEW_AUTHORITY_CLASS,
                operations=(REVIEW_OPERATION,),
                scope_ref=request.scope_ref,
                principal_ref=request.service_principal.principal_ref,
            ),
            sequence=2,
            prior_revision_id=store.heads[("authority_grant", PRODUCT, REVIEW_GRANT_REF)].revision_id,
            approval_actor_ref="user:not-the-delegator",
        )


async def test_external_effect_delegation_ceiling_is_denied() -> None:
    request = build_request(build_proposal(), service_principal())
    store, request, principal, _ = await _world(
        request=request,
        activation_grant=grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            delegation_ceiling=(
                ACTIVATION_AUTHORITY_CLASS,
                AuthorityClass.EXECUTE_EXTERNAL,
            ),
        ),
    )

    with _denies(DelegatedDenyCode.CONSEQUENCE_FORBIDDEN):
        await _resolve(store, request, principal)


def test_permitted_delegation_ceiling_excludes_every_external_consequence() -> None:
    forbidden = {
        AuthorityClass.EXECUTE_EXTERNAL,
        AuthorityClass.DELIVER_EXPORT,
        AuthorityClass.ADMINISTER_LIFECYCLE,
        AuthorityClass.INTELLIGENCE_BUILD,
    }
    assert not (PERMITTED_DELEGATION_CEILING & forbidden)


async def test_tampered_grant_payload_loses_its_commit_receipt_binding() -> None:
    store, request, principal, _ = await _world()
    head = store.heads[("authority_grant", PRODUCT, ACTIVATION_GRANT_REF)]
    stored = store.revisions[(PRODUCT, head.revision_id)]
    payload = dict(stored.payload)
    payload["grant_hash"] = "1" * 64
    store.revisions[(PRODUCT, head.revision_id)] = GovernedStateRevisionV1.model_validate(
        {**stored.model_dump(mode="python"), "payload": payload}
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_revoked_grant_payload_cannot_be_changed_to_active_under_stale_hash() -> None:
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    revoked = grant_material(
        grant_ref=ACTIVATION_GRANT_REF,
        authority_class=ACTIVATION_AUTHORITY_CLASS,
        operations=(ACTIVATION_OPERATION,),
        scope_ref=request.scope_ref,
        principal_ref=request.service_principal.principal_ref,
        lifecycle="revoked",
        revoked_at=NOW - timedelta(minutes=1),
    )
    store, _, _, _ = await _world(
        principal=principal,
        proposal=proposal,
        request=request,
        activation_grant=revoked,
    )
    head = store.heads[("authority_grant", PRODUCT, ACTIVATION_GRANT_REF)]
    stored = store.revisions[(PRODUCT, head.revision_id)]
    payload = {**stored.payload, "lifecycle": "active", "revoked_at": None}
    store.revisions[(PRODUCT, head.revision_id)] = GovernedStateRevisionV1.model_validate(
        {**stored.model_dump(mode="python"), "payload": payload}
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_false_grant_self_hash_is_denied_even_when_admitted_receipts_copy_it() -> None:
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    valid = grant_material(
        grant_ref=ACTIVATION_GRANT_REF,
        authority_class=ACTIVATION_AUTHORITY_CLASS,
        operations=(ACTIVATION_OPERATION,),
        scope_ref=request.scope_ref,
        principal_ref=request.service_principal.principal_ref,
    )
    false_hash = type(valid).model_validate({**valid.model_dump(mode="python"), "grant_hash": "8" * 64})
    store, _, _, _ = await _world(
        principal=principal,
        proposal=proposal,
        request=request,
        activation_grant=false_hash,
    )

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, request, principal)


async def test_suspended_principal_payload_cannot_be_changed_to_active_under_stale_hash() -> None:
    store, request, principal, _ = await _world(
        principal_state=PrincipalLifecycleState.SUSPENDED,
    )
    key = ("agent_principal_lifecycle", PRODUCT, request.service_principal.lifecycle_state_id)
    head = store.heads[key]
    stored = store.revisions[(PRODUCT, head.revision_id)]
    payload = {**stored.payload, "state": PrincipalLifecycleState.ACTIVE.value}
    store.revisions[(PRODUCT, head.revision_id)] = GovernedStateRevisionV1.model_validate(
        {**stored.model_dump(mode="python"), "payload": payload}
    )

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_principal_lifecycle_stored_digest_must_match_derived_material() -> None:
    store, request, principal, _ = await _world()
    key = ("agent_principal_lifecycle", PRODUCT, request.service_principal.lifecycle_state_id)
    head = store.heads[key]
    stored = store.revisions[(PRODUCT, head.revision_id)]
    payload = {**stored.payload, "lifecycle_revision_digest": "sha256:" + "8" * 64}
    store.revisions[(PRODUCT, head.revision_id)] = GovernedStateRevisionV1.model_validate(
        {**stored.model_dump(mode="python"), "payload": payload}
    )

    with _denies(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE):
        await _resolve(store, request, principal)


# --------------------------------------------------------------------------
# Capability state and configuration.
# --------------------------------------------------------------------------


async def test_missing_capability_state_is_denied() -> None:
    store, request, principal, _ = await _world()
    store.heads.pop(("capability_state", PRODUCT, request.capability_state_ref))

    with _denies(DelegatedDenyCode.CAPABILITY_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_suspended_capability_state_is_denied() -> None:
    store, request, principal, _ = await _world(capability=capability_state(lifecycle="suspended"))

    with _denies(DelegatedDenyCode.CAPABILITY_UNAVAILABLE):
        await _resolve(store, request, principal)


@pytest.mark.parametrize("tamper", ("configuration", "lifecycle", "artifact"))
async def test_capability_payload_tamper_loses_its_admitted_material_hash(tamper) -> None:
    store, request, principal, _ = await _world()
    head = store.heads[("capability_state", PRODUCT, request.capability_state_ref)]
    stored = store.revisions[(PRODUCT, head.revision_id)]
    payload = dict(stored.payload)
    if tamper == "configuration":
        payload["permitted_configuration_refs"] = (
            CONFIGURATION_REF,
            "cognition_activation_configuration:injected",
        )
    elif tamper == "lifecycle":
        payload["lifecycle"] = "suspended"
    else:
        artifact = dict(payload["artifact"])
        artifact["artifact_digest"] = "sha256:" + "9" * 64
        payload["artifact"] = artifact
    store.revisions[(PRODUCT, head.revision_id)] = GovernedStateRevisionV1.model_validate(
        {**stored.model_dump(mode="python"), "payload": payload}
    )

    with _denies(DelegatedDenyCode.CAPABILITY_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_unpermitted_configuration_is_denied() -> None:
    store, request, principal, _ = await _world(
        capability=capability_state(configuration_refs=("cognition_activation_configuration:other",))
    )

    with _denies(DelegatedDenyCode.CAPABILITY_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_active_capability_rotation_is_stale_even_when_material_remains_valid() -> None:
    store, request, principal, _ = await _world()
    current = store.heads[("capability_state", PRODUCT, request.capability_state_ref)]
    await seed_capability(
        store,
        capability_state(),
        sequence=2,
        prior_revision_id=current.revision_id,
    )

    with _denies(DelegatedDenyCode.CAPABILITY_UNAVAILABLE):
        await _resolve(store, request, principal)


async def test_alternate_valid_capability_and_configuration_do_not_reuse_base_grants() -> None:
    store, base, principal, proposal = await _world()
    alternate_artifact = type(ARTIFACT).model_validate(
        {
            **ARTIFACT.model_dump(mode="python"),
            "implementation_version": "1.1.0",
            "artifact_digest": "sha256:" + "a" * 64,
        }
    )
    alternate = build_request(
        proposal,
        principal,
        artifact=alternate_artifact,
        configuration_ref="cognition_activation_configuration:alternate",
    )
    assert alternate.scope_ref != base.scope_ref

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, alternate, principal)


async def test_configuration_swap_with_stale_digest_is_rejected_by_the_envelope() -> None:
    proposal = build_proposal()
    principal = service_principal()
    with pytest.raises(ValueError, match="configuration_digest"):
        build_request(
            proposal,
            principal,
            overrides={"configuration_ref": "cognition_activation_configuration:alternate"},
        )


async def test_alternate_valid_configuration_gets_a_distinct_exact_scope() -> None:
    proposal = build_proposal()
    principal = service_principal()
    base = build_request(proposal, principal, configuration_ref=CONFIGURATION_REF)
    alternate = build_request(
        proposal,
        principal,
        configuration_ref="cognition_activation_configuration:alternate",
    )
    assert alternate.configuration_digest != base.configuration_digest
    assert alternate.scope_ref != base.scope_ref


async def test_request_rejects_a_capability_state_ref_that_is_not_artifact_derived() -> None:
    proposal = build_proposal()
    principal = service_principal()
    with pytest.raises(ValueError):
        build_request(
            proposal,
            principal,
            overrides={"capability_state_ref": "capability_state:" + "9" * 32},
        )


# --------------------------------------------------------------------------
# Scope, window, and participant attribution.
# --------------------------------------------------------------------------


async def test_forged_scope_ref_is_rejected_by_the_envelope() -> None:
    with pytest.raises(ValueError):
        build_request(
            build_proposal(),
            service_principal(),
            overrides={"scope_ref": "delegated_cognition_scope:" + "a" * 32},
        )


async def test_scope_identity_changes_with_any_bound_material() -> None:
    base = build_request(build_proposal(), service_principal())
    other = build_request(build_proposal(stable_key="other_recipe"), service_principal())
    assert base.scope_ref != other.scope_ref
    assert base.scope_ref == delegated_scope_ref(
        product_id=base.product_id,
        capture_ref=base.capture_ref,
        capture_digest=base.capture_digest,
        proposal_id=base.proposal_id,
        proposal_hash=base.proposal_hash,
        target_cognition_id=base.target_cognition_id,
        derived_revision_id=base.derived_revision_id,
        derived_material_digest=base.derived_material_digest,
        capability_artifact_ref=base.capability_artifact_ref,
        capability_artifact_digest=base.capability_artifact_digest,
        capability_state_ref=base.capability_state_ref,
        capability_state_digest=base.capability_state_digest,
        capability_head_ref=base.capability_head_ref,
        capability_head_digest=base.capability_head_digest,
        configuration_ref=base.configuration_ref,
        configuration_digest=base.configuration_digest,
        policy_ref=base.policy_ref,
        service_principal_ref=base.service_principal.principal_ref,
    )


async def test_altered_capture_reference_no_longer_matches_the_pre_existing_grants() -> None:
    """The grants are pre-authorized for one exact capture, not for the service."""

    store, request, principal, proposal = await _world()
    forged = build_request(
        proposal,
        principal,
        overrides={
            "capture_ref": "capture:some-other-capture",
            "capture_digest": "sha256:" + "7" * 64,
        },
    )
    assert forged.scope_ref != request.scope_ref

    with _denies(DelegatedDenyCode.GRANT_MISMATCH):
        await _resolve(store, forged, principal)


async def test_consequence_class_cannot_be_widened_in_the_envelope() -> None:
    _, request, _, _ = await _world()
    with pytest.raises(ValueError):
        DelegatedCognitionActivationRequestV1Alpha1.model_validate(
            {
                **request.model_dump(mode="json"),
                "consequence_class": "external_effect_permitted",
                "request_id": None,
                "request_digest": None,
            }
        )
    with pytest.raises(ValueError):
        DelegatedCognitionActivationRequestV1Alpha1.model_validate(
            {
                **request.model_dump(mode="json"),
                "requested_disposition": "reject",
                "request_id": None,
                "request_digest": None,
            }
        )


async def test_expired_authentication_window_routes_back_to_human() -> None:
    store, request, principal, _ = await _world()

    with _denies(DelegatedDenyCode.HUMAN_REVIEW_REQUIRED):
        await _resolve(store, request, principal, evaluated_at=NOW + timedelta(hours=2))


async def test_model_participant_is_attribution_without_authority() -> None:
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal, participant=model_participant())
    store, request, principal, _ = await _world(principal=principal, proposal=proposal, request=request)

    resolved = await _resolve(store, request, principal)

    assert request.model_participant is not None
    assert request.model_participant.grants_authority is False
    # The participant never appears as an authority holder in the resolved bundle.
    assert resolved.review_evidence.delegator_ref != request.model_participant.participant_principal_ref
    assert resolved.activation_evidence.delegator_ref != request.model_participant.participant_principal_ref
    assert resolved.review_use.actor_ref == request.authenticated_actor_ref


def test_participant_cannot_impersonate_the_reviewing_service() -> None:
    principal = service_principal()
    binding = principal_binding(principal)
    forged = model_participant().model_copy(
        update={"participant_principal_ref": binding.principal_ref},
    )
    with pytest.raises(ValueError):
        build_request(build_proposal(), principal, participant=forged)


def test_delegated_service_self_review_is_denied() -> None:
    principal = service_principal()
    binding = principal_binding(principal)
    with pytest.raises(DelegatedCognitionAuthorityError, match=DelegatedDenyCode.SELF_REVIEW_FORBIDDEN.value):
        require_distinct_producer(
            producer_actor_id=binding.principal_ref,
            service_principal_ref=binding.principal_ref,
            authenticated_actor_ref=SERVICE_ACTOR,
            model_participant=None,
        )
    with pytest.raises(DelegatedCognitionAuthorityError, match=DelegatedDenyCode.SELF_REVIEW_FORBIDDEN.value):
        require_distinct_producer(
            producer_actor_id=SERVICE_ACTOR,
            service_principal_ref=binding.principal_ref,
            authenticated_actor_ref=SERVICE_ACTOR,
            model_participant=None,
        )


def test_distinct_producer_is_accepted() -> None:
    binding = principal_binding(service_principal())
    require_distinct_producer(
        producer_actor_id="model:teacher",
        service_principal_ref=binding.principal_ref,
        authenticated_actor_ref=SERVICE_ACTOR,
        model_participant=model_participant(),
    )
