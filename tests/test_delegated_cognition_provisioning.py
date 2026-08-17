"""Contract tests for the bounded human-admin provisioning operation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from ace.application.agent_governance import AgentGovernanceService
from ace.application.delegated_cognition_provisioning import (
    DelegatedCognitionProvisioningError,
    DelegatedCognitionProvisioningRequestV1Alpha1,
    DelegatedCognitionProvisioningService,
    delegated_cognition_service_token_claims,
)
from ace.core.agent_composition import AuthorityClass, PrincipalKind
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from core.engine.core.agent_composition_runtime import CompositionAuthorityGrantMaterial
from tests.delegated_cognition_support import (
    ACTIVATION_GRANT_REF,
    DELEGATOR,
    NOW,
    PRODUCT,
    REVIEW_GRANT_REF,
    SERVICE_ACTOR,
    build_proposal,
    build_request,
    service_principal,
)
from tests.intelligence.test_agent_onboarding_governance_ac4 import (
    ExactAuthority,
    MemoryAuditStore,
    MemoryGovernedStore,
)


def _request(**changes) -> DelegatedCognitionProvisioningRequestV1Alpha1:
    principal = changes.pop("principal", service_principal())
    activation = build_request(build_proposal(), principal)
    fields = {
        "product_id": PRODUCT,
        "principal": principal,
        "service_actor_ref": SERVICE_ACTOR,
        "scope_ref": activation.scope_ref,
        "policy_ref": activation.policy_ref,
        "review_grant_ref": REVIEW_GRANT_REF,
        "activation_grant_ref": ACTIVATION_GRANT_REF,
        "admin_actor_ref": DELEGATOR,
        "admin_grant_ref": "authority_grant:admin",
        "suspended_approval_receipt_ref": "approval:provision:suspended",
        "active_approval_receipt_ref": "approval:provision:active",
        "review_grant_approval_receipt_ref": "approval:provision:review",
        "activation_grant_approval_receipt_ref": "approval:provision:activation",
        "provisioned_at": NOW,
    }
    fields.update(changes)
    return DelegatedCognitionProvisioningRequestV1Alpha1(**fields)


def _service():
    governed = MemoryGovernedStore()
    audit = MemoryAuditStore(governed)
    authority = ExactAuthority()
    governance = AgentGovernanceService(
        governed_store=governed,
        audit_store=audit,
        authority=authority,
    )
    return DelegatedCognitionProvisioningService(governance=governance), governed, audit, authority


async def test_human_admin_provisions_exact_service_and_durable_receipt() -> None:
    service, governed, _, _ = _service()
    request = _request()

    receipt = await service.provision(request)
    reloaded = await service.load_receipt(product_id=PRODUCT, receipt_id=str(receipt.receipt_id))

    assert reloaded == receipt
    assert receipt.request_ref == request.request_id
    assert receipt.principal_ref == request.principal.principal_id
    assert receipt.authority_classes == (
        AuthorityClass.DECIDE_APPROVE,
        AuthorityClass.MUTATE_INTERNAL,
    )
    assert receipt.reusable_authority is receipt.renewable is receipt.transferable is False
    assert receipt.external_effect_authority is False
    assert delegated_cognition_service_token_claims(receipt) == {
        "sub": SERVICE_ACTOR,
        "product": PRODUCT,
        "authorities": [],
        "local_owner": False,
        "principal_kind": "service",
        "agent_principal": request.principal.principal_id,
    }
    for grant_ref, expected in (
        (REVIEW_GRANT_REF, (AuthorityClass.DECIDE_APPROVE, ("review_governed_cognition_capture",))),
        (ACTIVATION_GRANT_REF, (AuthorityClass.MUTATE_INTERNAL, ("activate_governed_cognition_revision",))),
    ):
        head = await governed.load_head(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=PRODUCT,
            state_id=grant_ref,
        )
        revision = await governed.load_revision(head.revision_id, product_id=PRODUCT)
        grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload, strict=False)
        assert (grant.authority_class, grant.operations) == expected
        assert grant.actor_ref == SERVICE_ACTOR
        assert grant.participant_principal_ref == request.principal.principal_id
        assert grant.delegator_ref == DELEGATOR
        assert grant.expires_at is None

    # Exact process retry is verification, not renewal or widening.
    assert await service.provision(request) == receipt


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"admin_actor_ref": SERVICE_ACTOR}, "human administrator"),
        ({"service_actor_ref": DELEGATOR}, "cannot provision or administer itself"),
        ({"activation_grant_ref": REVIEW_GRANT_REF}, "distinct grants"),
        ({"product_id": "product:other"}, "exact product scope"),
    ],
)
def test_contract_rejects_self_provisioning_and_scope_widening(changes, message) -> None:
    with pytest.raises(ValidationError, match=message):
        _request(**changes)


def test_contract_rejects_non_service_registration() -> None:
    with pytest.raises(ValidationError, match="only a SERVICE"):
        _request(principal=service_principal(principal_kind=PrincipalKind.MODEL_AGENT))


async def test_existing_identity_cannot_be_transferred_or_reprovisioned() -> None:
    service, _, _, _ = _service()
    original = _request()
    await service.provision(original)
    changed = _request(
        provisioned_at=NOW + timedelta(seconds=1),
        scope_ref="delegated_cognition_scope:" + "f" * 32,
    )

    with pytest.raises(DelegatedCognitionProvisioningError, match="renewal, replacement, and transfer"):
        await service.provision(changed)


async def test_admin_authority_revocation_fails_before_new_provisioning() -> None:
    service, _, _, authority = _service()
    authority.revoked.add("authority_grant:admin")

    with pytest.raises(DelegatedCognitionProvisioningError):
        await service.provision(_request())
