from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_core import to_jsonable_python

from ace.application.agent_composition_runtime import TaskAuthenticationReceiptV1Alpha1
from ace.application.briefing_agent_contracts import FIRST_BRIEFING_PREVIEW_VERSION
from ace.application.intelligence_agent_contracts import (
    INTELLIGENCE_MODEL_DISPOSITION_VERSION,
    INTELLIGENCE_MODEL_PROPOSAL_VERSION,
)
from ace.core.agent_composition import AuthorityClass, ExactArtifactReferenceV1Alpha1, HandoffState, RunState
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1, capability_state_ref_for_artifact
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    CONFIGURATION_PAYLOAD_CONTRACT,
    GRANT_PAYLOAD_CONTRACT,
    BoundedReasoningArtifactRegistry,
    CompositionAuthorityGrantMaterial,
    CompositionCapabilityStateMaterial,
    GovernedCompositionAuthorityError,
    GovernedReasoningCompositionAuthorityPort,
    GovernedStateRuntimeUseResolver,
    ReasoningCompositionConfigurationMaterial,
    persist_task_authentication_receipt,
)
from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.agent_composition_bridge import (
    GovernedCompositionBridgeError,
    LegacyCompositionAuthorityPolicy,
    LegacyOrchestrationCompositionBridge,
)
from core.engine.orchestration.patterns.base import PatternResult

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PRODUCT = "product:ac2"
ACTOR = "principal:operator"
PRINCIPAL = "agent_principal:legacy-orchestrator-adapter"
GRANT_REF = "authority_grant:structured-reasoning"
CONFIG_REF = "reasoning_configuration:task-composition"
SCOPE_REF = "scope:workspace-ac2"
POLICY_REF = "policy:composition-authority-v1"

ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="structured_reasoning",
    contract="ace.core.reasoning-provider/v1alpha1",
    implementation_id="host_reasoning_adapter",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "a" * 64,
)


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


class JsonRoundTripGovernedStateStore(InMemoryGovernedStateStore):
    """Mirror the JSON-shaped values returned by the durable SurrealDB adapter."""

    async def commit(self, request: GovernedStateCommitRequestV1):
        receipt = await super().commit(request)
        self.heads = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.heads.items()
        }
        self.revisions = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.revisions.items()
        }
        self.receipts = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.receipts.items()
        }
        return receipt


def _approval(subject: str, sequence: int) -> ResolvedApprovalReceiptV1:
    return ResolvedApprovalReceiptV1(
        receipt_ref=f"approval:ac2-{sequence}",
        product_id=PRODUCT,
        subject_ref=subject,
        actor_ref=ACTOR,
        receipt_hash=f"{sequence:064x}",
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
    revision_id = f"{state_kind}_revision:{sequence}"
    subject = f"approval_subject:{state_kind}-{sequence}"
    revision = GovernedStateRevisionV1(
        state_kind=state_kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=revision_id,
        material_hash=canonical_hash(to_jsonable_python(payload)),
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


async def _seed(store: InMemoryGovernedStateStore, *, sequence: int = 1) -> None:
    grant_fields = dict(
        grant_ref=GRANT_REF,
        product_id=PRODUCT,
        actor_ref=ACTOR,
        participant_principal_ref=PRINCIPAL,
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        operations=("structured_reasoning",),
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        lifecycle="active",
        # A later sequence is a genuine re-issue with different content, not
        # an arbitrary caller-supplied hash label.
        effective_at=NOW - timedelta(minutes=sequence),
        expires_at=NOW + timedelta(hours=1),
    )
    provisional = CompositionAuthorityGrantMaterial(**grant_fields, grant_hash="0" * 64)
    grant_hash = canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"}))
    grant = CompositionAuthorityGrantMaterial(**grant_fields, grant_hash=grant_hash)
    assert grant.grant_hash == canonical_hash(grant.model_dump(mode="json", exclude={"grant_hash"}))
    resolved = ResolvedAuthorityGrantV1(
        grant_ref=GRANT_REF,
        product_id=PRODUCT,
        authority="derive_propose",
        grant_hash=grant_hash,
        effective_at=grant.effective_at,
        expires_at=grant.expires_at,
    )
    prior = f"authority_grant_revision:{sequence - 1}" if sequence > 1 else None
    await _commit(
        store,
        state_kind="authority_grant",
        state_id=GRANT_REF,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=grant.model_dump(mode="python"),
        sequence=sequence,
        prior_revision_id=prior,
        resolved_grant=resolved,
    )
    if sequence > 1:
        return
    capability = CompositionCapabilityStateMaterial(
        product_id=PRODUCT,
        artifact=ARTIFACT,
        lifecycle="active",
        permitted_configuration_refs=(CONFIG_REF,),
    )
    configuration = ReasoningCompositionConfigurationMaterial(
        product_id=PRODUCT,
        configuration_ref=CONFIG_REF,
        artifact=ARTIFACT,
        authority=AuthorityClass.DERIVE_PROPOSE,
        grant_ref=GRANT_REF,
        lifecycle="active",
    )
    await _commit(
        store,
        state_kind="capability_state",
        state_id=capability_state_ref_for_artifact(ARTIFACT),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        payload=capability.model_dump(mode="python"),
    )
    await _commit(
        store,
        state_kind="reasoning_configuration",
        state_id=CONFIG_REF,
        payload_contract=CONFIGURATION_PAYLOAD_CONTRACT,
        payload=configuration.model_dump(mode="python"),
    )


def _policy() -> LegacyCompositionAuthorityPolicy:
    return LegacyCompositionAuthorityPolicy(
        participant_principal_ref=PRINCIPAL,
        authority_class="derive_propose",
        operation="structured_reasoning",
        grant_ref=GRANT_REF,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        classifier_revision_ref="classifier:legacy-v1",
        routing_revision_ref="routing:legacy-v1",
        composition_policy_revision_ref="composition_policy:ac2-v1",
        composer_revision_ref="cognitive_composer:legacy-v1",
        context_policy_ref="context_policy:i3-bridge-v1",
        failure_policy_ref="failure_policy:honest-partial-v1",
    )


async def _environment(*, token_authorities: tuple[str, ...] | None = None):
    governed = InMemoryGovernedStateStore()
    await _seed(governed)
    records = InMemoryImmutableRecordStore(governed_state_heads=governed.heads)
    auth = await persist_task_authentication_receipt(
        claims={"sub": ACTOR, "product": PRODUCT, "exp": (NOW + timedelta(minutes=30)).timestamp()},
        verified_at=NOW,
        store=records,
        verification_policy_ref="jwt_verification_policy:v1",
    )
    runtime = GovernedStateRuntimeUseResolver(governed_state=governed)
    port = GovernedReasoningCompositionAuthorityPort(
        governed_state=governed,
        records=records,
        runtime_use=runtime,
        registry=BoundedReasoningArtifactRegistry((ARTIFACT,)),
        configuration_ref=CONFIG_REF,
        token_authorities=token_authorities,
    )
    return governed, records, auth, LegacyOrchestrationCompositionBridge(authority=port, policy=_policy())


async def _prepare_one(bridge, auth, *, task_ref: str = "task:one"):
    return await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref=task_ref,
        session_ref="workspace:ac2",
        objective="Analyze safely.",
        classification={"archetype": "analyst"},
        snapshot={},
        pattern_name="independent",
        agent_configs=[AgentConfig(role="analyst")],
        now=NOW + timedelta(seconds=5),
    )


@pytest.mark.asyncio
async def test_authentication_adapter_requires_exact_verified_claims_and_persists_no_credential() -> None:
    records = InMemoryImmutableRecordStore()
    with pytest.raises(GovernedCompositionAuthorityError, match="expiry"):
        await persist_task_authentication_receipt(
            claims={"sub": ACTOR, "product": PRODUCT, "authorities": ["derive_propose"]},
            verified_at=NOW,
            store=records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
    assert not records.records
    receipt = await persist_task_authentication_receipt(
        claims={"sub": ACTOR, "product": PRODUCT, "exp": (NOW + timedelta(minutes=5)).timestamp()},
        verified_at=NOW,
        store=records,
        verification_policy_ref="jwt_verification_policy:v1",
    )
    payload = next(iter(records.records.values())).model_dump_json()
    assert "bearer" not in payload.lower()
    assert receipt.runtime_context().authentication_receipt_ref == receipt.receipt_id


@pytest.mark.asyncio
async def test_token_authority_labels_only_attenuate_and_cannot_create_a_grant() -> None:
    _, _, auth, bridge = await _environment(token_authorities=("observe_read",))
    with pytest.raises(GovernedCompositionAuthorityError, match="attenuation"):
        await bridge.prepare(
            authenticated_context=auth.runtime_context(),
            task_ref="task:attenuated",
            session_ref="workspace:ac2",
            objective="Analyze the evidence.",
            classification={"archetype": "analyst"},
            snapshot={},
            pattern_name="independent",
            agent_configs=[AgentConfig(role="analyst")],
            now=NOW + timedelta(seconds=5),
        )


@pytest.mark.asyncio
async def test_runtime_authority_resolver_accepts_durable_json_round_trip() -> None:
    governed = JsonRoundTripGovernedStateStore()
    await _seed(governed)
    records = InMemoryImmutableRecordStore(governed_state_heads=governed.heads)
    authentication = await persist_task_authentication_receipt(
        claims={"sub": ACTOR, "product": PRODUCT, "exp": (NOW + timedelta(minutes=30)).timestamp()},
        verified_at=NOW,
        store=records,
        verification_policy_ref="jwt_verification_policy:v1",
    )
    runtime = GovernedStateRuntimeUseResolver(governed_state=governed)
    context = authentication.runtime_context()

    grant, _ = await runtime.load_grant(
        context=context,
        participant_principal_ref=PRINCIPAL,
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        operation="structured_reasoning",
        grant_ref=GRANT_REF,
        scope_ref=SCOPE_REF,
        policy_ref=POLICY_REF,
        evaluated_at=NOW,
    )
    use = await runtime.resolve_authority_use(
        context=context,
        use_subject_ref="subject:durable-json-round-trip",
        use_subject_digest="sha256:" + "d" * 64,
        operation="structured_reasoning",
        authority=AuthorityClass.DERIVE_PROPOSE.value,
        grant_ref=GRANT_REF,
        evaluated_at=NOW,
    )

    assert grant.grant_ref == GRANT_REF
    assert use.grant_ref == GRANT_REF


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("legacy_pattern", "canonical_pattern"),
    [
        ("independent", "solo"),
        ("pipeline", "pipeline"),
        ("fanout", "fanout_join"),
        ("adversarial", "adversarial"),
        ("human_gate", "human_gate"),
    ],
)
async def test_bridge_emits_deterministic_plan_manifests_receipts_join_and_typed_handoff(
    legacy_pattern: str,
    canonical_pattern: str,
) -> None:
    _, _, auth, bridge = await _environment()
    configs = [AgentConfig(role="analyst"), AgentConfig(role="critic")]
    prepared = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref=f"task:{legacy_pattern}",
        session_ref="workspace:ac2",
        objective="Analyze then synthesize.",
        classification={"archetype": "analyst", "cognitive_composition": {"recipe": "analysis"}},
        snapshot={"_marker_map": {"[I-1]": "insight:1"}},
        pattern_name=legacy_pattern,
        agent_configs=configs,
        now=NOW + timedelta(seconds=5),
    )
    replay = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref=f"task:{legacy_pattern}",
        session_ref="workspace:ac2",
        objective="Analyze then synthesize.",
        classification={"archetype": "analyst", "cognitive_composition": {"recipe": "analysis"}},
        snapshot={"_marker_map": {"[I-1]": "insight:1"}},
        pattern_name=legacy_pattern,
        agent_configs=configs,
        now=NOW + timedelta(seconds=5),
    )
    assert replay.plan == prepared.plan
    assert prepared.plan.orchestration_pattern == canonical_pattern
    adapter_participants = [item for item in prepared.plan.participants if item.participant_kind.value == "adapter"]
    assert len(adapter_participants) == 2
    if canonical_pattern == "human_gate":
        assert any(item.participant_kind.value == "human" for item in prepared.plan.participants)
    execution = await bridge.authorize_execution(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        now=NOW + timedelta(seconds=6),
    )
    completed = bridge.complete(
        prepared=prepared,
        execution_authority=execution,
        pattern_result=PatternResult(
            run_id="run_ac2",
            pattern_name=legacy_pattern,
            status="completed",
            output="synthesis",
            agent_results=[
                AgentResult(agent_id="execution:1", status="completed", output="analysis"),
                AgentResult(agent_id="execution:2", status="completed", output="critique"),
            ],
        ),
        snapshot={},
        actual_route=None,
        now=NOW + timedelta(seconds=7),
    )
    assert all(item.state == RunState.COMPLETE for item in completed.run_receipts)
    assert completed.join_evidence.artifact_contract == "ace.bridge.i2-join-evidence/v1alpha1"
    assert completed.handoff_receipt.state == HandoffState.PREPARED
    assert completed.handoff_receipt.external_send_occurred is False
    assert completed.projection()["legacy_ownership"]["i3_intelligence_use"].startswith("selection")


@pytest.mark.asyncio
async def test_missing_timeout_abstention_partial_and_tainted_join_are_honest() -> None:
    _, _, auth, bridge = await _environment()
    prepared = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref="task:degraded",
        session_ref="workspace:ac2",
        objective="Compare independent contributions.",
        classification={"archetype": "analyst"},
        snapshot={},
        pattern_name="fanout",
        agent_configs=[AgentConfig(role="one"), AgentConfig(role="two"), AgentConfig(role="three")],
        now=NOW + timedelta(seconds=5),
    )
    execution = await bridge.authorize_execution(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        now=NOW + timedelta(seconds=6),
    )
    completed = bridge.complete(
        prepared=prepared,
        execution_authority=execution,
        pattern_result=PatternResult(
            run_id="run_degraded",
            pattern_name="fanout",
            status="completed",
            output="partial synthesis",
            agent_results=[
                AgentResult(agent_id="one", status="completed", output="usable"),
                AgentResult(agent_id="two", status="timeout"),
                # Third contributor is deliberately missing.
            ],
        ),
        snapshot={"phase_traces": [{"phase_name": "critic", "tainted": True}]},
        actual_route=None,
        now=NOW + timedelta(seconds=7),
    )
    assert [item.state for item in completed.run_receipts] == [RunState.COMPLETE, RunState.DEGRADED, RunState.FAILED]
    assert completed.run_receipts[1].issue_codes == ("ace.composition.contributor.timeout",)
    assert completed.run_receipts[2].issue_codes == ("ace.composition.contributor.missing",)
    assert completed.handoff_receipt.state == HandoffState.PARTIAL


@pytest.mark.asyncio
async def test_grant_rotation_between_plan_and_run_fails_closed_and_retry_requires_fresh_auth() -> None:
    governed, _, auth, bridge = await _environment()
    prepared = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref="task:rotation",
        session_ref="workspace:ac2",
        objective="Analyze safely.",
        classification={"archetype": "analyst"},
        snapshot={},
        pattern_name="independent",
        agent_configs=[AgentConfig(role="analyst")],
        now=NOW + timedelta(seconds=5),
    )
    await _seed(governed, sequence=2)
    with pytest.raises(GovernedCompositionBridgeError, match="rotated"):
        await bridge.authorize_execution(
            prepared=prepared,
            authenticated_context=auth.runtime_context(),
            now=NOW + timedelta(seconds=8),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("participant_principal_ref", "agent_principal:foreign", "mismatched"),
        ("scope_ref", "scope:foreign", "mismatched"),
        ("policy_ref", "policy:foreign", "mismatched"),
    ],
)
async def test_actor_principal_scope_and_policy_mismatch_fail_closed(field: str, value: str, message: str) -> None:
    governed, records, auth, _ = await _environment()
    runtime = GovernedStateRuntimeUseResolver(governed_state=governed)
    port = GovernedReasoningCompositionAuthorityPort(
        governed_state=governed,
        records=records,
        runtime_use=runtime,
        registry=BoundedReasoningArtifactRegistry((ARTIFACT,)),
        configuration_ref=CONFIG_REF,
    )
    bridge = LegacyOrchestrationCompositionBridge(authority=port, policy=replace(_policy(), **{field: value}))
    with pytest.raises(GovernedCompositionAuthorityError, match=message):
        await _prepare_one(bridge, auth, task_ref=f"task:mismatch-{field}")


@pytest.mark.asyncio
async def test_missing_foreign_stale_and_revoked_governed_lineage_fail_closed() -> None:
    governed, _, auth, bridge = await _environment()
    grant_key = ("authority_grant", PRODUCT, GRANT_REF)
    original_head = governed.heads.pop(grant_key)
    with pytest.raises(GovernedCompositionAuthorityError, match="missing current authority_grant head"):
        await _prepare_one(bridge, auth, task_ref="task:missing-head")
    governed.heads[grant_key] = original_head.model_copy(update={"product_id": "product:foreign"})
    with pytest.raises(GovernedCompositionAuthorityError, match="failed exact validation|cross-wired"):
        await _prepare_one(bridge, auth, task_ref="task:foreign-head")
    governed.heads[grant_key] = original_head.model_copy(update={"sequence": original_head.sequence + 1})
    with pytest.raises(GovernedCompositionAuthorityError, match="cross-wired"):
        await _prepare_one(bridge, auth, task_ref="task:stale-head")
    governed.heads[grant_key] = original_head
    revision = governed.revisions[(PRODUCT, original_head.revision_id)]
    revoked_fields = {
        **revision.payload,
        "lifecycle": "revoked",
        "revoked_at": NOW,
    }
    revoked_fields.pop("grant_hash")
    provisional = CompositionAuthorityGrantMaterial(**revoked_fields, grant_hash="0" * 64)
    revoked = CompositionAuthorityGrantMaterial(
        **revoked_fields,
        grant_hash=canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"})),
    )
    await _commit(
        governed,
        state_kind="authority_grant",
        state_id=GRANT_REF,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=revoked.model_dump(mode="python"),
        sequence=2,
        prior_revision_id=original_head.revision_id,
        resolved_grant=ResolvedAuthorityGrantV1(
            grant_ref=GRANT_REF,
            product_id=PRODUCT,
            authority="derive_propose",
            grant_hash=revision.payload["grant_hash"],
            effective_at=revision.payload["effective_at"],
            expires_at=revision.payload["expires_at"],
        ),
    )
    with pytest.raises(GovernedCompositionAuthorityError, match="revoked"):
        await _prepare_one(bridge, auth, task_ref="task:revoked-head")


@pytest.mark.asyncio
async def test_fabricated_resolution_receipt_and_cancelled_retry_lineage_are_detected() -> None:
    _, _, auth, bridge = await _environment()
    prepared = await _prepare_one(bridge, auth, task_ref="task:retry-lineage")
    bundle = prepared.planning_authority[0]
    fabricated_capability = ExactArtifactReferenceV1Alpha1(
        artifact_id="capability_use_receipt:fabricated",
        artifact_digest="sha256:" + "f" * 64,
        artifact_contract=bundle.resolution_receipt.capability_use.artifact_contract,
    )
    fabricated_resolution = bundle.resolution_receipt.model_copy(update={"capability_use": fabricated_capability})
    with pytest.raises(ValueError, match="receipt_id does not match|does not bind exact execution evidence"):
        bundle.__class__.model_validate(
            {
                **bundle.model_dump(mode="python"),
                "resolution_receipt": fabricated_resolution,
            }
        )
    execution = await bridge.authorize_execution(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        now=NOW + timedelta(seconds=6),
    )
    completed = bridge.complete(
        prepared=prepared,
        execution_authority=execution,
        pattern_result=PatternResult(
            run_id="run_cancelled",
            pattern_name="independent",
            status="cancelled",
            agent_results=[AgentResult(agent_id="one", status="cancelled")],
        ),
        snapshot={},
        actual_route=None,
        now=NOW + timedelta(seconds=7),
        attempt=2,
        retry_of_receipt_refs=("stage_run_receipt:prior",),
    )
    receipt = completed.run_receipts[0]
    assert receipt.state == RunState.CANCELLED
    assert receipt.attempt == 2
    assert receipt.retry_of_receipt_ref == "stage_run_receipt:prior"
    assert receipt.authority_exercised == ()
    expired = TaskAuthenticationReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        verification_policy_ref="jwt_verification_policy:v1",
        authenticated_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1),
    )
    with pytest.raises(GovernedCompositionAuthorityError, match="expired"):
        await bridge.prepare(
            authenticated_context=expired.runtime_context(),
            task_ref="task:retry",
            session_ref="workspace:ac2",
            objective="Retry.",
            classification={"archetype": "analyst"},
            snapshot={},
            pattern_name="independent",
            agent_configs=[AgentConfig(role="analyst")],
            now=NOW,
        )


@pytest.mark.asyncio
async def test_model_preferences_cannot_select_an_artifact_and_historical_reference_is_rejected() -> None:
    _, _, auth, bridge = await _environment()
    prepared = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref="task:model-preference",
        session_ref="workspace:ac2",
        objective="Use requested-model only as a constraint.",
        classification={"requested_model": "untrusted-provider/model"},
        snapshot={},
        pattern_name="independent",
        agent_configs=[AgentConfig(role="analyst", model="untrusted-provider/model")],
        trigger_artifacts=(
            ExactArtifactReferenceV1Alpha1(
                artifact_id="domain_activation_commit_reference:historical",
                artifact_digest="sha256:" + "d" * 64,
                artifact_contract="ace.application.domain-activation-commit-reference/v1alpha2",
            ),
        ),
        now=NOW + timedelta(seconds=5),
    )
    assert prepared.planning_authority[0].execution_binding.artifact == ARTIFACT
    assert prepared.plan.activation_lineage is None
    assert prepared.plan.trigger_artifacts[0].artifact_contract.endswith("domain-activation-commit-reference/v1alpha2")
    historical = prepared.plan.trigger_artifacts[0]
    with pytest.raises(ValueError, match="historical activation"):
        prepared.planning_authority[0].resolution_receipt.model_copy(
            update={"capability_use": historical}
        ).__class__.model_validate(
            prepared.planning_authority[0]
            .resolution_receipt.model_copy(update={"capability_use": historical})
            .model_dump(mode="python")
        )


@pytest.mark.asyncio
async def test_watch_brief_coordinates_are_inert_triggers_and_i3_lineage_stops_at_observed_reflection() -> None:
    _, _, auth, bridge = await _environment()
    triggers = (
        ExactArtifactReferenceV1Alpha1(
            artifact_id="intelligence_model_proposal:approved",
            artifact_digest="sha256:" + "1" * 64,
            artifact_contract=INTELLIGENCE_MODEL_PROPOSAL_VERSION,
        ),
        ExactArtifactReferenceV1Alpha1(
            artifact_id="intelligence_model_disposition:approved",
            artifact_digest="sha256:" + "2" * 64,
            artifact_contract=INTELLIGENCE_MODEL_DISPOSITION_VERSION,
        ),
        ExactArtifactReferenceV1Alpha1(
            artifact_id="first_briefing_preview:inert",
            artifact_digest="sha256:" + "3" * 64,
            artifact_contract=FIRST_BRIEFING_PREVIEW_VERSION,
        ),
    )
    prepared = await bridge.prepare(
        authenticated_context=auth.runtime_context(),
        task_ref="task:watch-brief-trigger",
        session_ref="workspace:ac2",
        objective="Analyze the approved inert proposal and preview.",
        classification={"archetype": "analyst"},
        snapshot={},
        pattern_name="independent",
        agent_configs=[AgentConfig(role="analyst")],
        trigger_artifacts=triggers,
        now=NOW + timedelta(seconds=5),
    )
    execution = await bridge.authorize_execution(
        prepared=prepared,
        authenticated_context=auth.runtime_context(),
        now=NOW + timedelta(seconds=6),
    )
    completed = bridge.complete(
        prepared=prepared,
        execution_authority=execution,
        pattern_result=PatternResult(
            run_id="run_watch_brief",
            pattern_name="independent",
            status="completed",
            output="synthesis",
            agent_results=[AgentResult(agent_id="one", status="completed", output="analysis")],
        ),
        snapshot={
            "_intelligence_use_trace": {
                "items": [{"id": "intelligence:1", "injected": True}],
                "reflected_ids": ["intelligence:1"],
            }
        },
        actual_route=None,
        now=NOW + timedelta(seconds=7),
    )
    assert prepared.plan.trigger_artifacts == tuple(sorted(triggers, key=lambda item: item.artifact_contract))
    receipt = completed.run_receipts[0]
    assert [item.value for item in receipt.context_states] == [
        "eligible",
        "authorized",
        "selected",
        "injected",
        "reflected",
    ]
    assert "decision_material" not in {item.value for item in receipt.context_states}
    assert not set(triggers).intersection(receipt.output_artifacts)
    assert completed.handoff_receipt.external_send_occurred is False


def test_public_task_and_mcp_contracts_are_not_expanded() -> None:
    from core.engine.api.tasks import TaskCreate
    from core.engine.orchestration.request import OrchestrationRequest

    forbidden = {
        "authenticated_context",
        "authority",
        "grant_ref",
        "execution_binding",
        "composition_plan",
        "stage_run_manifest",
    }
    assert forbidden.isdisjoint(TaskCreate.model_fields)
    assert forbidden.isdisjoint(OrchestrationRequest.model_fields)
