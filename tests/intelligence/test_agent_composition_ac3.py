from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.agent_composition_lifecycle import (
    LIFECYCLE_STAGE_PROFILES,
    BoundLifecycleExecutionOwner,
    LifecycleCompositionError,
    LifecycleOwnerFailure,
    LifecycleParticipantCompositionBridge,
    LifecycleServiceOutcomeV1Alpha1,
    LifecycleStageRequestV1Alpha1,
    PreparedLifecycleDeliveryOwner,
    SentinelObservationProjectionV1Alpha1,
    UnsupportedLifecycleStage,
)
from ace.core.agent_composition import (
    ExactArtifactReferenceV1Alpha1,
    HandoffState,
    ParticipantKind,
    RunState,
)
from ace.core.contracts import canonical_hash
from ace.core.reasoning import GOVERNED_OPERATION_CONFIGURATION_STATE_KIND
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1, capability_state_ref_for_artifact
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.agent_composition import LifecycleStage
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.agent_composition_lifecycle_runtime import (
    LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT,
    GovernedLifecycleCompositionAuthorityPort,
    LifecycleCompositionConfigurationMaterial,
)
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    GRANT_PAYLOAD_CONTRACT,
    BoundedReasoningArtifactRegistry,
    CompositionAuthorityGrantMaterial,
    CompositionCapabilityStateMaterial,
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)

NOW = datetime(2026, 8, 12, 13, 0, tzinfo=UTC)
PRODUCT = "product:ac3"
ACTOR = "principal:lifecycle-operator"
SCOPE_REF = "scope:lifecycle-workspace"
POLICY_REF = "policy:lifecycle-composition-v1"


class InMemoryGovernedStateStore:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions: dict[tuple[str, str], GovernedStateRevisionV1] = {}
        self.receipts = {}

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
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, str(receipt.receipt_id))] = receipt
        self.heads[(revision.state_kind, revision.product_id, revision.state_id)] = head
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))


def _ref(name: str, contract: str | None = None) -> ExactArtifactReferenceV1Alpha1:
    digest = canonical_hash({"name": name, "contract": contract or f"ace.test.{name}/v1alpha1"})
    return ExactArtifactReferenceV1Alpha1(
        artifact_id=f"{name}:{digest[:32]}",
        artifact_digest=f"sha256:{digest}",
        artifact_contract=contract or f"ace.test.{name}/v1alpha1",
    )


def _coordinates(stage: LifecycleStage):
    profile = LIFECYCLE_STAGE_PROFILES[stage]
    slug = stage.value
    principal_ref = profile.participant_refs[0]
    grant_ref = f"authority_grant:lifecycle-{slug}"
    configuration_ref = f"governed_operation_configuration:lifecycle-{slug}"
    artifact = CapabilityArtifactIdentityV1Alpha1(
        capability=f"lifecycle_{slug}",
        contract="ace.host.lifecycle-service/v1alpha1",
        implementation_id=f"lifecycle_{slug}_compatibility_owner",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + canonical_hash({"stage": slug}),
    )
    return profile, principal_ref, grant_ref, configuration_ref, artifact


def _approval(subject: str, sequence: int) -> ResolvedApprovalReceiptV1:
    return ResolvedApprovalReceiptV1(
        receipt_ref=f"approval:ac3-{sequence}-{canonical_hash(subject)[:8]}",
        product_id=PRODUCT,
        subject_ref=subject,
        actor_ref=ACTOR,
        receipt_hash=canonical_hash({"subject": subject, "sequence": sequence}),
        approved_at=NOW + timedelta(seconds=sequence),
    )


async def _commit(
    store: InMemoryGovernedStateStore,
    *,
    state_kind: str,
    state_id: str,
    payload_contract: str,
    payload: dict,
    sequence: int = 1,
    prior_revision_id: str | None = None,
    resolved_grant: ResolvedAuthorityGrantV1 | None = None,
) -> None:
    revision_id = f"{state_kind}_revision:{canonical_hash([state_id, sequence])[:24]}"
    subject = f"approval_subject:{canonical_hash([state_kind, state_id, sequence])[:24]}"
    revision = GovernedStateRevisionV1(
        state_kind=state_kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=revision_id,
        material_hash=canonical_hash({"state_kind": state_kind, "state_id": state_id, "sequence": sequence}),
        prior_revision_id=prior_revision_id,
        approval_subject_ref=subject,
        payload_contract=payload_contract,
        payload=payload,
    )
    await store.commit(
        GovernedStateCommitRequestV1(
            revision=revision,
            expected_head_revision_id=prior_revision_id,
            actor_ref=ACTOR,
            approval=_approval(subject, sequence),
            authority_grants=(resolved_grant,) if resolved_grant is not None else (),
            committed_at=NOW + timedelta(seconds=sequence + 1),
        )
    )


async def _seed(
    store: InMemoryGovernedStateStore,
    stage: LifecycleStage,
    *,
    grant_hash: str | None = None,
    grant_sequence: int = 1,
    lifecycle: str = "active",
) -> tuple[str, str, CapabilityArtifactIdentityV1Alpha1]:
    profile, principal_ref, grant_ref, configuration_ref, artifact = _coordinates(stage)
    grant_hash = grant_hash or canonical_hash({"grant": stage.value, "sequence": grant_sequence})
    grant = CompositionAuthorityGrantMaterial(
        grant_ref=grant_ref,
        product_id=PRODUCT,
        actor_ref=ACTOR,
        participant_principal_ref=principal_ref,
        authority_class=profile.authority_class,
        operations=(profile.operation,),
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        grant_hash=grant_hash,
        lifecycle=lifecycle,
        effective_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        revoked_at=NOW + timedelta(seconds=8) if lifecycle == "revoked" else None,
    )
    resolved = ResolvedAuthorityGrantV1(
        grant_ref=grant_ref,
        product_id=PRODUCT,
        authority=profile.authority_class.value,
        grant_hash=grant_hash,
        state="active" if lifecycle == "active" else lifecycle,
        effective_at=grant.effective_at,
        expires_at=grant.expires_at,
    )
    prior = None
    if grant_sequence > 1:
        prior = store.heads[("authority_grant", PRODUCT, grant_ref)].revision_id
    await _commit(
        store,
        state_kind="authority_grant",
        state_id=grant_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=grant.model_dump(mode="python"),
        sequence=grant_sequence,
        prior_revision_id=prior,
        resolved_grant=resolved,
    )
    if grant_sequence > 1:
        return grant_ref, configuration_ref, artifact
    capability = CompositionCapabilityStateMaterial(
        product_id=PRODUCT,
        artifact=artifact,
        lifecycle="active",
        permitted_configuration_refs=(configuration_ref,),
    )
    configuration = LifecycleCompositionConfigurationMaterial(
        product_id=PRODUCT,
        configuration_ref=configuration_ref,
        profile_ref=profile.coordinate_ref,
        stage=stage,
        operation=profile.operation,
        artifact=artifact,
        authority=profile.authority_class.value,
        grant_ref=grant_ref,
        lifecycle="active",
    )
    await _commit(
        store,
        state_kind="capability_state",
        state_id=capability_state_ref_for_artifact(artifact),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        payload=capability.model_dump(mode="python"),
    )
    await _commit(
        store,
        state_kind=GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
        state_id=configuration_ref,
        payload_contract=LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT,
        payload=configuration.model_dump(mode="python"),
    )
    return grant_ref, configuration_ref, artifact


async def _environment(
    stage: LifecycleStage,
    *,
    token_authorities: tuple[str, ...] | None = None,
):
    governed = InMemoryGovernedStateStore()
    grant_ref, configuration_ref, artifact = await _seed(governed, stage)
    records = InMemoryImmutableRecordStore(governed_state_heads=governed.heads)
    auth = await persist_task_authentication_receipt(
        claims={"sub": ACTOR, "product": PRODUCT, "exp": (NOW + timedelta(minutes=30)).timestamp()},
        verified_at=NOW,
        store=records,
        verification_policy_ref="jwt_verification_policy:v1",
    )
    runtime = GovernedStateRuntimeUseResolver(governed_state=governed)
    port = GovernedLifecycleCompositionAuthorityPort(
        records=records,
        runtime_use=runtime,
        registry=BoundedReasoningArtifactRegistry((artifact,)),
        configuration_refs={stage: configuration_ref},
        token_authorities=token_authorities,
    )
    return governed, records, auth, grant_ref, LifecycleParticipantCompositionBridge(authority=port)


def _request(stage: LifecycleStage, *, input_contract: str | None = None) -> LifecycleStageRequestV1Alpha1:
    profile = LIFECYCLE_STAGE_PROFILES[stage]
    return LifecycleStageRequestV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        session_ref="workspace:ac3",
        task_ref=f"task:{stage.value}",
        case_ref="case:bounded" if stage is LifecycleStage.INVESTIGATE else None,
        stage=stage,
        objective=f"Run the bounded {stage.value} compatibility owner.",
        input_artifacts=(
            _ref(f"{stage.value}-input", input_contract or profile.accepted_input_contracts[0]),
        ),
        context_manifest=_ref("context-manifest", "ace.intelligence.context-manifest/v1alpha1"),
        context_selection_receipt=_ref(
            "context-selection", "ace.intelligence.context-selection-receipt/v1alpha1"
        ),
        instruction_resolution=_ref(
            "instruction-resolution", "ace.intelligence.instruction-resolution-receipt/v1alpha1"
        ),
        instruction_layer_refs=(
            _ref("instruction-layer", "ace.intelligence.instruction-contribution/v1alpha1"),
        ),
        source_scope_refs=(SCOPE_REF,),
        created_at=NOW + timedelta(seconds=4),
        expires_at=NOW + timedelta(minutes=20),
    )


def _owner(stage: LifecycleStage, *, state: RunState = RunState.COMPLETE, output_contract: str | None = None):
    profile = LIFECYCLE_STAGE_PROFILES[stage]

    async def execute(_manifest):
        outputs = ()
        if state is not RunState.BLOCKED:
            outputs = (_ref(f"{stage.value}-output", output_contract or profile.output_contracts[0]),)
        return LifecycleServiceOutcomeV1Alpha1(
            stage=stage,
            participant_ref=profile.participant_refs[0],
            state=state,
            output_artifacts=outputs,
            owner_receipts=(_ref(f"{stage.value}-owner-receipt"),),
            issue_codes=(f"ace.lifecycle.{stage.value}.{state.value}",) if state is not RunState.COMPLETE else (),
            occurred_at=NOW + timedelta(seconds=7),
            duration_ms=10,
        )

    return BoundLifecycleExecutionOwner(
        stage=stage,
        participant_ref=profile.participant_refs[0],
        participant_kind=profile.participant_kind,
        executor=execute,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage",
    [
        LifecycleStage.ACQUIRE,
        LifecycleStage.DETECT,
        LifecycleStage.INVESTIGATE,
        LifecycleStage.ACT,
        LifecycleStage.VERIFY,
        LifecycleStage.OBSERVE,
    ],
)
async def test_existing_lifecycle_owners_emit_canonical_stage_evidence(stage: LifecycleStage) -> None:
    _, _, auth, grant_ref, bridge = await _environment(stage)
    owner = _owner(stage)
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    completed = await bridge.execute(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        owner=owner,
        now=NOW + timedelta(seconds=6),
    )
    profile = LIFECYCLE_STAGE_PROFILES[stage]
    participant = completed.plan.participants[0]
    assert completed.plan.stage_id == stage.value
    assert participant.participant_kind is profile.participant_kind
    assert participant.definition_revision is None
    assert participant.role_binding is None
    assert completed.manifest.execution_binding.artifact_contract == (
        "ace.core.governed-operation-binding/v1alpha1"
    )
    assert completed.run_receipt.state is RunState.COMPLETE
    assert completed.run_receipt.usage.external_effects == 0
    assert completed.handoff_receipt.state is HandoffState.PREPARED
    assert completed.handoff_receipt.external_send_occurred is False
    assert completed.projection()["agent_definition_promoted"] is False


@pytest.mark.asyncio
async def test_deliver_is_only_an_inert_prepared_handoff_for_ac5() -> None:
    stage = LifecycleStage.DELIVER
    _, _, auth, grant_ref, bridge = await _environment(stage)
    owner = PreparedLifecycleDeliveryOwner(clock=lambda: NOW + timedelta(seconds=7))
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    completed = await bridge.execute(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        owner=owner,
        now=NOW + timedelta(seconds=6),
    )
    assert completed.run_receipt.output_artifacts[0].artifact_contract == (
        "ace.application.prepared-lifecycle-delivery/v1alpha1"
    )
    assert completed.handoff_contract.target_stage_id == "ac5_delivery_authority_gate"
    assert completed.handoff_receipt.target_ref == "ac5_delivery_gate:required"
    assert completed.handoff_receipt.external_send_occurred is False
    assert completed.run_receipt.authority_exercised[0].authority_class.value == "derive_propose"


def test_ground_decide_and_broader_stages_are_explicitly_unsupported() -> None:
    bridge = LifecycleParticipantCompositionBridge(authority=object())
    for stage in (LifecycleStage.GROUND, LifecycleStage.DECIDE, LifecycleStage.ACTIVATE):
        with pytest.raises(UnsupportedLifecycleStage, match="unsupported"):
            bridge.profile_for(stage)


@pytest.mark.asyncio
async def test_stage_input_owner_and_output_widening_fail_closed() -> None:
    stage = LifecycleStage.DETECT
    _, _, auth, grant_ref, bridge = await _environment(stage)
    owner = _owner(stage)
    with pytest.raises(LifecycleCompositionError, match="compatible exact input"):
        await bridge.prepare(
            request=_request(stage, input_contract="ace.unknown.input/v1alpha1"),
            authenticated_context=auth.runtime_context(),
            owner=owner,
            grant_ref=grant_ref,
            scope_ref=SCOPE_REF,
            policy_ref=POLICY_REF,
            now=NOW + timedelta(seconds=5),
        )
    wrong_owner = BoundLifecycleExecutionOwner(
        stage=stage,
        participant_ref="service:hidden-self-promoted-agent",
        participant_kind=ParticipantKind.MODEL_AGENT,
        executor=owner.execute,
    )
    with pytest.raises(LifecycleCompositionError, match="compatibility profile"):
        await bridge.prepare(
            request=_request(stage),
            authenticated_context=auth.runtime_context(),
            owner=wrong_owner,
            grant_ref=grant_ref,
            scope_ref=SCOPE_REF,
            policy_ref=POLICY_REF,
            now=NOW + timedelta(seconds=5),
        )
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    widened = _owner(stage, output_contract="ace.external.unbounded-output/v1alpha1")
    with pytest.raises(LifecycleCompositionError, match="widened"):
        await bridge.execute(
            prepared=prepared,
            authenticated_context=auth.runtime_context(),
            owner=widened,
            now=NOW + timedelta(seconds=6),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "handoff_state"),
    [
        (RunState.BLOCKED, HandoffState.FAILED),
        (RunState.DEGRADED, HandoffState.PARTIAL),
        (RunState.ABSTAINED, HandoffState.PARTIAL),
        (RunState.CANCELLED, HandoffState.CANCELLED),
    ],
)
async def test_degraded_and_unsupported_owner_results_remain_explicit(
    state: RunState, handoff_state: HandoffState
) -> None:
    stage = LifecycleStage.INVESTIGATE
    _, _, auth, grant_ref, bridge = await _environment(stage)
    owner = _owner(stage, state=state)
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    completed = await bridge.execute(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        owner=owner,
        now=NOW + timedelta(seconds=6),
    )
    assert completed.run_receipt.state is state
    assert completed.handoff_receipt.state is handoff_state
    assert completed.handoff_receipt.external_send_occurred is False


@pytest.mark.asyncio
async def test_existing_owner_exception_translates_to_a_typed_failed_exit() -> None:
    stage = LifecycleStage.VERIFY
    _, _, auth, grant_ref, bridge = await _environment(stage)
    profile = LIFECYCLE_STAGE_PROFILES[stage]

    async def fail(_manifest):
        raise LifecycleOwnerFailure(
            state=RunState.FAILED,
            issue_codes=("ace.lifecycle.verify.existing-owner-failure",),
            owner_receipts=(_ref("verify-failure-receipt"),),
            occurred_at=NOW + timedelta(seconds=7),
        )

    owner = BoundLifecycleExecutionOwner(
        stage=stage,
        participant_ref=profile.participant_refs[0],
        participant_kind=profile.participant_kind,
        executor=fail,
    )
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    completed = await bridge.execute(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        owner=owner,
        now=NOW + timedelta(seconds=6),
    )
    assert completed.run_receipt.state is RunState.FAILED
    assert completed.handoff_receipt.state is HandoffState.FAILED
    assert completed.run_receipt.issue_codes == ("ace.lifecycle.verify.existing-owner-failure",)


@pytest.mark.asyncio
async def test_provider_route_is_observed_only_and_external_effect_claims_are_rejected() -> None:
    stage = LifecycleStage.INVESTIGATE
    _, _, auth, grant_ref, bridge = await _environment(stage)
    profile = LIFECYCLE_STAGE_PROFILES[stage]
    route = _ref("provider-route", "ace.core.provider-route/v1alpha1")

    async def execute(_manifest):
        return LifecycleServiceOutcomeV1Alpha1(
            stage=stage,
            participant_ref=profile.participant_refs[0],
            state=RunState.COMPLETE,
            output_artifacts=(_ref("brief", profile.output_contracts[0]),),
            actual_route=route,
            occurred_at=NOW + timedelta(seconds=7),
        )

    owner = BoundLifecycleExecutionOwner(
        stage=stage,
        participant_ref=profile.participant_refs[0],
        participant_kind=profile.participant_kind,
        executor=execute,
    )
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    assert "provider-route" not in prepared.manifest.model_dump_json()
    completed = await bridge.execute(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        owner=owner,
        now=NOW + timedelta(seconds=6),
    )
    assert completed.run_receipt.actual_route == route
    with pytest.raises(ValueError, match="external_effect_occurred"):
        LifecycleServiceOutcomeV1Alpha1(
            stage=stage,
            participant_ref=profile.participant_refs[0],
            state=RunState.FAILED,
            external_effect_occurred=True,
            occurred_at=NOW,
        )


@pytest.mark.asyncio
async def test_current_grant_rotation_between_plan_and_run_is_rejected() -> None:
    stage = LifecycleStage.ACT
    governed, _, auth, grant_ref, bridge = await _environment(stage)
    owner = _owner(stage)
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    await _seed(governed, stage, grant_hash="f" * 64, grant_sequence=2)
    with pytest.raises(LifecycleCompositionError, match="rotated"):
        await bridge.execute(
            prepared=prepared,
            authenticated_context=auth.runtime_context(),
            owner=owner,
            now=NOW + timedelta(seconds=9),
        )


@pytest.mark.asyncio
async def test_missing_configuration_and_token_label_only_authority_fail_closed() -> None:
    stage = LifecycleStage.OBSERVE
    _, _, auth, grant_ref, bridge = await _environment(stage, token_authorities=("observe_read",))
    with pytest.raises(GovernedCompositionAuthorityError, match="attenuation"):
        await bridge.prepare(
            request=_request(stage),
            authenticated_context=auth.runtime_context(),
            owner=_owner(stage),
            grant_ref=grant_ref,
            scope_ref=SCOPE_REF,
            policy_ref=POLICY_REF,
            now=NOW + timedelta(seconds=5),
        )
    governed, _, auth, grant_ref, bridge = await _environment(stage)
    profile = LIFECYCLE_STAGE_PROFILES[stage]
    _, _, _, configuration_ref, _ = _coordinates(stage)
    governed.heads.pop((GOVERNED_OPERATION_CONFIGURATION_STATE_KIND, PRODUCT, configuration_ref))
    with pytest.raises(GovernedCompositionAuthorityError, match="missing current"):
        await bridge.prepare(
            request=_request(stage),
            authenticated_context=auth.runtime_context(),
            owner=_owner(profile.stage),
            grant_ref=grant_ref,
            scope_ref=SCOPE_REF,
            policy_ref=POLICY_REF,
            now=NOW + timedelta(seconds=5),
        )


@pytest.mark.asyncio
async def test_restart_requires_fresh_authentication_and_produces_new_plan_identity() -> None:
    stage = LifecycleStage.ACQUIRE
    _, records, auth, grant_ref, bridge = await _environment(stage)
    owner = _owner(stage)
    request = _request(stage)
    with pytest.raises(LifecycleCompositionError, match="authenticated window"):
        await bridge.prepare(
            request=request,
            authenticated_context=auth.runtime_context(),
            owner=owner,
            grant_ref=grant_ref,
            scope_ref=SCOPE_REF,
            policy_ref=POLICY_REF,
            now=NOW + timedelta(minutes=31),
        )
    fresh = await persist_task_authentication_receipt(
        claims={"sub": ACTOR, "product": PRODUCT, "exp": (NOW + timedelta(hours=2)).timestamp()},
        verified_at=NOW + timedelta(minutes=31),
        store=records,
        verification_policy_ref="jwt_verification_policy:v1",
    )
    restarted_request = request.model_copy(
        update={
            "created_at": NOW + timedelta(minutes=31),
            "expires_at": NOW + timedelta(hours=2),
            "request_id": None,
            "request_digest": None,
        }
    )
    restarted_request = LifecycleStageRequestV1Alpha1.model_validate(
        restarted_request.model_dump(mode="python")
    )
    restarted = await bridge.prepare(
        request=restarted_request,
        authenticated_context=fresh.runtime_context(),
        owner=owner,
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(minutes=31, seconds=1),
    )
    assert restarted.planning_authority.authenticated_context.authentication_receipt_ref == fresh.receipt_id
    assert restarted.plan.composition_plan_id is not None
    assert restarted.request.request_id != request.request_id


@pytest.mark.asyncio
async def test_watch_proposal_preview_and_historical_activation_stay_inert_coordinates() -> None:
    stage = LifecycleStage.INVESTIGATE
    _, _, auth, grant_ref, bridge = await _environment(stage)
    request = _request(stage).model_copy(
        update={
            "trigger_artifacts": (
                _ref("watch-proposal", "ace.application.intelligence-model-proposal/v1alpha1"),
                _ref("first-brief-preview", "ace.application.first-briefing-preview/v1alpha1"),
                _ref(
                    "activation-history",
                    "ace.application.domain-activation-commit-reference/v1alpha2",
                ),
            ),
            "request_id": None,
            "request_digest": None,
        }
    )
    request = LifecycleStageRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
    prepared = await bridge.prepare(
        request=request,
        authenticated_context=auth.runtime_context(),
        owner=_owner(stage),
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    contracts = {item.artifact_contract for item in prepared.plan.trigger_artifacts}
    assert "ace.application.first-briefing-preview/v1alpha1" in contracts
    assert "ace.application.domain-activation-commit-reference/v1alpha2" in contracts
    assert prepared.plan.activation_lineage is None
    assert all(item.authority_class.value != "deliver_export" for item in prepared.manifest.authority)


def test_stage_maturity_and_ownership_inventory_is_bounded_and_explicit() -> None:
    assert set(LIFECYCLE_STAGE_PROFILES) == {
        LifecycleStage.ACQUIRE,
        LifecycleStage.DETECT,
        LifecycleStage.INVESTIGATE,
        LifecycleStage.ACT,
        LifecycleStage.VERIFY,
        LifecycleStage.DELIVER,
        LifecycleStage.OBSERVE,
    }
    assert LIFECYCLE_STAGE_PROFILES[LifecycleStage.ACT].maturity.startswith("experimental")
    assert LIFECYCLE_STAGE_PROFILES[LifecycleStage.DELIVER].next_stage_id == "ac5_delivery_authority_gate"
    assert LIFECYCLE_STAGE_PROFILES[LifecycleStage.DETECT].coordinate_ref.startswith(
        "lifecycle_stage_profile:"
    )
    assert all(
        profile.participant_kind in {ParticipantKind.ADAPTER, ParticipantKind.DETERMINISTIC_SERVICE}
        for profile in LIFECYCLE_STAGE_PROFILES.values()
    )


def test_legacy_sentinel_projection_is_exact_inert_and_non_authoritative() -> None:
    projection = SentinelObservationProjectionV1Alpha1(
        product_id=PRODUCT,
        sentinel_owner_ref="core.engine.sentinel.SentinelScheduler",
        source_record=_ref("sentinel-source"),
        trigger_receipt=_ref("sentinel-trigger"),
        disposition="observed",
        observed_at=NOW,
    )
    replay = SentinelObservationProjectionV1Alpha1.model_validate(projection.model_dump(mode="python"))
    assert replay == projection
    assert replay.execution_authority is False
    assert replay.external_effect_occurred is False


@pytest.mark.asyncio
async def test_ac3_does_not_invent_ac4_governance_or_registration_coordinates() -> None:
    stage = LifecycleStage.DETECT
    _, _, auth, grant_ref, bridge = await _environment(stage)
    prepared = await bridge.prepare(
        request=_request(stage),
        authenticated_context=auth.runtime_context(),
        owner=_owner(stage),
        grant_ref=grant_ref,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        now=NOW + timedelta(seconds=5),
    )
    participant = prepared.plan.participants[0]
    assert participant.participant_ref == "ace.intelligence.detection.numeric_delta"
    assert not participant.participant_ref.startswith("governance_id:")
    assert participant.definition_revision is None
    assert participant.role_binding is None
    assert prepared.manifest.authority[0].principal_ref == participant.participant_ref
