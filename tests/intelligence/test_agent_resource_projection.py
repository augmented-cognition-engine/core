from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application import AgentResourceProjectionReader
from ace.core import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    AgentPrincipalLifecycleRevisionV1Alpha1,
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    PrincipalLifecycleState,
)
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader
from tests.intelligence.test_agent_onboarding_governance_ac4 import (
    NOW,
    PRODUCT,
    _active_stack,
    _evidence,
)

pytestmark = pytest.mark.unit


def _query(*, subject_refs: tuple[str, ...] = ()) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:agent-analyst",
            authentication_receipt_ref="authentication_receipt:agent-projection",
            authentication_receipt_digest="sha256:" + "e" * 64,
            authenticated_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.AGENT,),
        subject_refs=subject_refs,
        as_of=NOW + timedelta(minutes=20),
        available_at=NOW + timedelta(minutes=20),
        page_size=20,
    )


async def _activated_stack():
    stack = await _active_stack()
    compatibility, conformance, dry_run = _evidence(stack)
    activation, _ = await stack["service"].activate(
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        compatibility=compatibility,
        conformance=conformance,
        dry_run=dry_run,
        actor_ref="human:admin",
        admin_grant_ref="grant:admin",
        activated_at=NOW + timedelta(minutes=5),
    )
    return stack, activation


@pytest.mark.asyncio
async def test_exact_activation_projects_one_non_authoritative_agent_resource() -> None:
    stack, activation = await _activated_stack()

    batch = await AgentResourceProjectionReader(store=stack["audit"]).read(
        query=_query(subject_refs=(stack["governance"].principal_key,)),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert len(batch.records) == 1
    agent = batch.records[0]
    assert agent.reference.resource_kind is IntelligenceResourceKind.AGENT
    assert agent.reference.resource_id == stack["governance"].governance_id
    assert agent.reference.revision == 1
    assert agent.availability is IntelligenceResourceAvailability.AVAILABLE
    assert agent.supersedes is None
    assert agent.payload is not None
    payload = agent.payload.parsed_value()
    assert payload["activation_receipt_id"] == activation.receipt_id
    assert payload["activation_eligibility_only"] is True
    assert payload["reusable_authority"] is False
    assert payload["current_lifecycle"]["health"]["state"] == "healthy"
    assert "grant:derive" not in agent.payload.value_json
    assert "lifecycle_authority" not in agent.payload.value_json

    restarted = await AgentResourceProjectionReader(store=stack["audit"]).read(
        query=_query(),
        after=None,
        limit=20,
    )
    assert restarted == batch
    host_composed = await intelligence_resource_projection_reader(stack["audit"]).read(
        query=_query(subject_refs=(stack["governance"].principal_key,)),
        after=None,
        limit=20,
    )
    assert host_composed == batch


@pytest.mark.asyncio
async def test_lifecycle_drift_creates_an_exact_degraded_revision() -> None:
    stack, _ = await _activated_stack()
    suspended = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        registration_implementation_ref=stack["principal"].implementation_ref,
        registration_protocol_refs=stack["principal"].supported_protocol_versions,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=3,
        prior_revision_id=str(stack["principal_active"].lifecycle_revision_id),
        approval_receipt_ref="approval:principal:suspend",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].admit_principal_lifecycle(
        suspended,
        registration=stack["principal"],
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=6),
    )

    batch = await AgentResourceProjectionReader(store=stack["audit"]).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.records) == 1
    current = batch.records[0]
    assert current.availability is IntelligenceResourceAvailability.DEGRADED
    assert current.reference.revision == 2
    assert current.supersedes is not None
    assert current.supersedes.revision == 1
    assert current.supersedes.resource_digest != current.reference.resource_digest
    assert current.degraded_reason_refs == (
        "degraded_reason:agent-activation-stale",
        "degraded_reason:agent-principal-suspended",
    )


@pytest.mark.asyncio
async def test_revoked_principal_tombstones_agent_without_payload() -> None:
    stack, _ = await _activated_stack()
    revoked = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        registration_implementation_ref=stack["principal"].implementation_ref,
        registration_protocol_refs=stack["principal"].supported_protocol_versions,
        state=PrincipalLifecycleState.REVOKED,
        sequence=3,
        prior_revision_id=str(stack["principal_active"].lifecycle_revision_id),
        approval_receipt_ref="approval:principal:revoke",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].admit_principal_lifecycle(
        revoked,
        registration=stack["principal"],
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=6),
    )

    batch = await AgentResourceProjectionReader(store=stack["audit"]).read(
        query=_query(),
        after=None,
        limit=20,
    )

    assert len(batch.records) == 1
    assert batch.records[0].availability is IntelligenceResourceAvailability.TOMBSTONED
    assert batch.records[0].payload is None


@pytest.mark.asyncio
async def test_unactivated_or_incomplete_governance_never_looks_like_a_live_agent() -> None:
    unactivated = await _active_stack()
    empty = await AgentResourceProjectionReader(store=unactivated["audit"]).read(
        query=_query(),
        after=None,
        limit=20,
    )
    assert empty.records == ()
    assert empty.state is IntelligenceResourcePageState.COMPLETE

    activated, _ = await _activated_stack()
    lifecycle_storage_id = next(
        key
        for key, record in activated["audit"].records.items()
        if record.record_kind == "lifecycle_revision" and record.record_key == activated["health"].health_revision_id
    )
    del activated["audit"].records[lifecycle_storage_id]
    degraded = await AgentResourceProjectionReader(store=activated["audit"]).read(
        query=_query(),
        after=None,
        limit=20,
    )
    assert degraded.records == ()
    assert degraded.state is IntelligenceResourcePageState.DEGRADED
    assert degraded.degraded_reason_refs == (
        f"degraded_reason:invalid-agent-activation-chain:{activated['governance'].governance_id}",
    )
