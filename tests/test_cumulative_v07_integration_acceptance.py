from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ace.application.agent_memory_recall import (
    CompositionContextManifestBridge,
    ContextPlannerService,
    StaticRetrievalStateOwner,
)
from ace.application.domain_activation_plan import (
    DomainActivationPlanAdmissionService,
    activation_commit_reference,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.testing.watch_brief import exercise_watch_brief_restart
from tests.agent_memory.am3 import test_authorized_recall as am3
from tests.intelligence import test_composition_policy_admission_ac7 as ac7
from tests.intelligence import test_domain_activation_plan_admission as activation

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_cumulative_builder_activation_composition_and_memory_path() -> None:
    """Prove the cumulative 0.7 lanes compose without minting implicit authority."""

    # Connect -> Map -> Watch -> Brief, including restart, is the packaged 0.7D
    # reference journey. Activation must bind its exact immutable coordinates.
    watch = await exercise_watch_brief_restart()
    pack, conformance, spec = activation._activation_material()
    handoff = activation.prepare_activation_onboarding_handoff(
        session=watch.briefing.session.revision,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    created_at = datetime(2026, 8, 12, 12, tzinfo=UTC)
    plan = activation._plan(
        spec=spec,
        action=activation.ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created_at,
        handoff=handoff,
    )
    revision = activation._revision(
        plan=plan,
        revision=1,
        occurred_at=created_at + timedelta(minutes=1),
    )
    activation_store = activation._MemoryStore()
    activated = await DomainActivationPlanAdmissionService(
        store=activation_store,
        authority=activation._Authority(),
    ).admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        session=watch.briefing.session.revision,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
        committed_at=revision.occurred_at + timedelta(seconds=1),
    )
    reloaded_activation = await DomainActivationPlanAdmissionService(
        store=activation_store,
        authority=activation._Authority(),
    ).reload(product_id=spec.product_id, activation_key=spec.activation_key)
    activation_lineage = activation_commit_reference(reloaded_activation)

    assert reloaded_activation == activated
    assert activation_lineage.live_authority is False
    assert activation_lineage.authority_stage == "historical_reference"
    assert handoff.first_briefing_preview_id == watch.briefing.brief.brief_id

    # AC7 admits a measured composition policy separately. Its runtime result is
    # advisory and cannot make a participant eligible or grant authority.
    service, governed, records, protocol, comparison, proposal, heads = await ac7._environment()
    packet = ac7._packet(
        action=ac7.CompositionPolicyAction.ADMIT,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=ac7.BASE + timedelta(minutes=3),
        nonce="cumulative-v07-admit",
    )
    admitted_policy = await service.admit(
        plan=packet[0],
        request=packet[1],
        review=packet[2],
        admitted_at=ac7.BASE + timedelta(minutes=3, seconds=3),
    )
    runtime = await service.resolve_runtime(
        product_id=ac7.PRODUCT,
        policy_id=ac7.POLICY,
        scope_ref=ac7.SCOPE,
        actor_ref="principal:cumulative-runtime",
        principal_ref="agent_principal:cumulative-runtime",
        use_subject_ref=activation_lineage.revision_id,
        use_subject_digest=activation_lineage.revision_digest,
        current_authority_and_configuration_heads=heads,
        request_nonce="cumulative-v07-runtime",
        resolved_at=ac7.BASE + timedelta(minutes=4),
        expires_at=ac7.BASE + timedelta(minutes=4, seconds=10),
    )
    reopened_policy = await ac7.CompositionPolicyAdmissionService(
        governed_store=governed,
        audit_store=records,
        authority=ac7.PresentAuthority(),
    ).reopen(product_id=ac7.PRODUCT, policy_id=ac7.POLICY)

    assert reopened_policy == admitted_policy
    assert admitted_policy.live_authority is False
    assert runtime.grants_authority is False
    assert runtime.makes_participant_eligible is False

    # AM3 performs separately authorized recall and produces a Context Manifest.
    # The composition bridge consumes only its exact opaque references after a
    # fresh runtime check bound to the already-admitted policy coordinates.
    memory_store, _, _, projection = await am3._seed(second=False)
    memory_policy = am3._policy()
    snapshot = am3._snapshot(memory_policy, projection)
    recall = am3._recall(task="task:cumulative-v07")
    planner = ContextPlannerService(
        store=memory_store,
        authorization=am3._Authority(),
        state_owner=StaticRetrievalStateOwner(snapshot),
        instruction_resolver=am3._Instructions(),
        clock=lambda: am3.NOW + timedelta(minutes=2),
    )
    planned = await planner.plan(am3._planner_request(recall, memory_policy, snapshot))
    reopened_manifest = await ContextPlannerService(
        store=memory_store,
        authorization=am3._Authority(),
        state_owner=StaticRetrievalStateOwner(snapshot),
        instruction_resolver=am3._Instructions(),
        clock=lambda: am3.NOW + timedelta(minutes=2),
    ).reopen_manifest(
        request=recall,
        manifest_ref=str(planned.manifest.artifact_id),
        expected_snapshot=snapshot,
    )

    class BoundRuntimeAuthority:
        async def resolve_planning(self, **kwargs):
            assert reopened_policy.revision.revision_id == admitted_policy.revision.revision_id
            assert runtime.grants_authority is False
            assert activation_lineage.live_authority is False
            return SimpleNamespace(
                resolution_receipt=SimpleNamespace(
                    phase="planning",
                    product_id=kwargs["authenticated_context"].product_id,
                    participant_principal_ref=kwargs["participant_principal_ref"],
                    use_subject=kwargs["use_subject"],
                    evaluated_at=kwargs["evaluated_at"],
                    current_heads=(
                        admitted_policy.revision.revision_id,
                        activation_lineage.revision_id,
                    ),
                )
            )

    resolved_context = await CompositionContextManifestBridge(
        runtime_authority=BoundRuntimeAuthority(),
        clock=lambda: am3.NOW + timedelta(minutes=2),
    ).resolve(
        planned=planned,
        authenticated_context=recall.authenticated_context,
        authority_class="derive_propose",
        grant_ref="grant:cumulative-composition",
        scope_ref="scope:cumulative-composition",
        policy_ref=admitted_policy.revision.revision_id,
    )

    assert reopened_manifest == planned.manifest
    assert resolved_context.context_manifest.artifact_id == planned.manifest.artifact_id
    assert resolved_context.context_selection_receipt.artifact_id == planned.recall.artifact_id
    assert activation_lineage.live_authority is admitted_policy.live_authority is False
    assert GovernedStateHeadPreconditionV1Alpha1.from_head(admitted_policy.head).revision_id
