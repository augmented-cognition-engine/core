"""AC7 governed composition-policy admission and runtime-resolution proof."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace.application.composition_policy_admission import (
    CompositionPolicyAdmissionError,
    CompositionPolicyAdmissionService,
)
from ace.application.measured_composition import MeasuredCompositionEvaluationService
from ace.core.contracts import canonical_hash
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.composition_policy import (
    CompositionPolicyAction,
    CompositionPolicyAdmissionPlanV1Alpha1,
    CompositionPolicyAdmissionRequestV1Alpha1,
    CompositionPolicyLifecycle,
    CompositionPolicyReviewDisposition,
    CompositionPolicyReviewerClass,
    CompositionPolicyReviewV1Alpha1,
    composition_policy_reference,
)
from ace.intelligence.contracts.measured_composition import measured_composition_reference
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from evaluations.source.ac6_measured_composition import (
    BASE,
    FIXTURE_PATH,
    _build_assignment,
    _build_authority,
    _build_observation,
    _build_protocol,
    _ref,
)

pytestmark = pytest.mark.unit
REPO = Path(__file__).resolve().parents[2]
AC7_FIXTURE = REPO / "evaluations/fixtures/ac7_composition_policy_admission_conformance_v1.json"
PRODUCT = "product:ac6-conformance"
POLICY = "composition_policy:ac7-current"
SCOPE = "scope:ac6-exact-fixture"
REQUESTER = "principal:policy-requester"
REQUESTER_PRINCIPAL = "agent_principal:policy-requester"
ADMIN = "principal:policy-administrator"
ADMIN_PRINCIPAL = "agent_principal:policy-administrator"
GRANT = "grant:administer-composition-policy"
CONFIG = "composition_policy_configuration:ac7"


class CasGovernedStateStore:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions = {}
        self.receipts = {}

    async def commit(self, request: GovernedStateCommitRequestV1):
        revision = request.revision
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current = self.heads.get(key)
        actual = current.revision_id if current is not None else None
        if actual != request.expected_head_revision_id:
            raise RuntimeError("governed_state_head_conflict")
        if current is not None and revision.sequence != current.sequence + 1:
            raise RuntimeError("governed_state_sequence_conflict")
        if current is None and revision.sequence != 1:
            raise RuntimeError("governed_state_sequence_conflict")
        receipt = request.receipt()
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
        self.heads[key] = head
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))


class PresentAuthority:
    def __init__(self) -> None:
        self.revoked = False

    async def resolve_approval(self, *, receipt_ref, product_id, subject_ref, actor_ref, effective_at):
        return ResolvedApprovalReceiptV1(
            receipt_ref=receipt_ref,
            product_id=product_id,
            subject_ref=subject_ref,
            actor_ref=actor_ref,
            receipt_hash=canonical_hash([receipt_ref, product_id, subject_ref, actor_ref, effective_at.isoformat()]),
            approved_at=effective_at - timedelta(milliseconds=1),
        )

    async def resolve_grant(self, *, grant_ref, product_id, authority, effective_at):
        if self.revoked:
            raise RuntimeError("revoked")
        return ResolvedAuthorityGrantV1(
            grant_ref=grant_ref,
            product_id=product_id,
            authority=authority,
            grant_hash=canonical_hash([grant_ref, product_id, authority]),
            effective_at=effective_at,
            expires_at=effective_at + timedelta(minutes=5),
        )


def _head(kind: str, state_id: str, *, sequence: int = 1) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=f"{kind}_revision:ac7-{sequence}",
        commit_receipt_id=f"governed_state_commit:{kind}-ac7-{sequence}",
        updated_at=BASE,
    )


async def _environment():
    import json

    fixture = json.loads(FIXTURE_PATH.read_text())
    authority, ac6_heads = _build_authority(fixture["product_id"])
    protocol = _build_protocol(fixture, authority)
    case = next(item for item in fixture["cases"] if item["case_id"] == "dynamic_helps")
    assignment = _build_assignment(protocol, case_id="dynamic_helps", assigned_at=BASE + timedelta(minutes=1))
    observations = tuple(
        _build_observation(
            fixture,
            protocol,
            assignment,
            case,
            condition,
            observed_at=assignment.assigned_at + timedelta(seconds=index + 1),
        )
        for index, condition in enumerate(protocol.conditions)
    )
    governed = CasGovernedStateStore()
    grant_head = _head("authority_grant", GRANT)
    config_head = _head("composition_policy_configuration", CONFIG)
    for item in (*ac6_heads, grant_head, config_head):
        governed.heads[(item.state_kind, item.product_id, item.state_id)] = item
    records = InMemoryImmutableRecordStore(governed_state_heads=governed.heads)
    measured = MeasuredCompositionEvaluationService(store=records)
    await measured.preregister(authority=authority, protocol=protocol)
    await measured.assign(assignment)
    for observation in observations:
        await measured.observe(observation)
    closure = await measured.close(
        product_id=protocol.product_id,
        protocol_ref=measured_composition_reference(protocol),
        assignment_ref=measured_composition_reference(assignment),
        observation_refs=tuple(measured_composition_reference(item) for item in observations),
        current_policy=_ref("composition_policy:none", "ace.governance.composition-policy/v1"),
        proposed_policy_rule_ref="composition_policy_rule:dynamic-exact-scope",
        compared_at=assignment.assigned_at + timedelta(seconds=10),
    )
    assert closure.proposal is not None
    current_heads = tuple(
        sorted(
            (
                GovernedStateHeadPreconditionV1Alpha1.from_head(grant_head),
                GovernedStateHeadPreconditionV1Alpha1.from_head(config_head),
            ),
            key=lambda item: item.state_kind,
        )
    )
    service = CompositionPolicyAdmissionService(
        governed_store=governed,
        audit_store=records,
        authority=PresentAuthority(),
    )
    return service, governed, records, protocol, closure.comparison, closure.proposal, current_heads


def _packet(
    *,
    action: CompositionPolicyAction,
    protocol,
    comparison,
    proposal,
    heads,
    at,
    nonce,
    expected=None,
    disposition=CompositionPolicyReviewDisposition.APPROVE,
    rollback_target=None,
):
    evidence = action in {
        CompositionPolicyAction.ADMIT,
        CompositionPolicyAction.SUPERSEDE,
        CompositionPolicyAction.ROLLBACK,
    }
    plan = CompositionPolicyAdmissionPlanV1Alpha1(
        product_id=PRODUCT,
        policy_id=POLICY,
        scope_ref=SCOPE,
        action=action,
        proposal=measured_composition_reference(proposal) if evidence else None,
        protocol=measured_composition_reference(protocol) if evidence else None,
        comparison=measured_composition_reference(comparison) if evidence else None,
        expected_current_head=expected,
        rollback_target_revision=rollback_target,
        proposed_policy_rule_ref=proposal.proposed_policy_rule_ref if evidence else None,
        selection_constraints=("constraint:prefer-dynamic-only-inside-exact-scope",) if evidence else (),
        selection_preferences=("preference:bounded-evidence-closure",) if evidence else (),
        frozen_ac6_authority_lineage=protocol.current_governed_heads if evidence else (),
        rationale=f"Exercise exact governed {action.value} without widening authority.",
        created_at=at,
        expires_at=at + timedelta(minutes=10),
    )
    request = CompositionPolicyAdmissionRequestV1Alpha1(
        product_id=PRODUCT,
        policy_id=POLICY,
        scope_ref=SCOPE,
        plan=composition_policy_reference(plan),
        requester_actor_ref=REQUESTER,
        requester_principal_ref=REQUESTER_PRINCIPAL,
        administrator_actor_ref=ADMIN,
        administrator_principal_ref=ADMIN_PRINCIPAL,
        approval_receipt_ref=f"approval:{nonce}",
        administration_grant_ref=GRANT,
        expected_current_head=expected,
        current_core_heads=heads,
        request_nonce=nonce,
        requested_at=at + timedelta(seconds=1),
        expires_at=at + timedelta(minutes=10),
    )
    review = CompositionPolicyReviewV1Alpha1(
        product_id=PRODUCT,
        policy_id=POLICY,
        scope_ref=SCOPE,
        plan=composition_policy_reference(plan),
        request=composition_policy_reference(request),
        reviewer_actor_ref=ADMIN,
        reviewer_principal_ref=ADMIN_PRINCIPAL,
        reviewer_class=CompositionPolicyReviewerClass.HUMAN,
        disposition=disposition,
        reasons=(f"review:{action.value}:{disposition.value}",),
        reviewed_at=at + timedelta(seconds=2),
    )
    return plan, request, review


@pytest.mark.asyncio
async def test_positive_admit_suspend_recover_restart_runtime_and_exact_replay() -> None:
    service, governed, records, protocol, comparison, proposal, heads = await _environment()
    packet = _packet(
        action=CompositionPolicyAction.ADMIT,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=3),
        nonce="admit-1",
    )
    admitted = await service.admit(
        plan=packet[0], request=packet[1], review=packet[2], admitted_at=BASE + timedelta(minutes=3, seconds=3)
    )
    replay = await service.admit(
        plan=packet[0], request=packet[1], review=packet[2], admitted_at=BASE + timedelta(minutes=3, seconds=3)
    )
    assert replay == admitted
    assert admitted.revision.lifecycle is CompositionPolicyLifecycle.ACTIVE
    assert admitted.live_authority is False

    runtime = await service.resolve_runtime(
        product_id=PRODUCT,
        policy_id=POLICY,
        scope_ref=SCOPE,
        actor_ref="principal:runtime-actor",
        principal_ref="agent_principal:runtime-participant",
        use_subject_ref="task:ac7-runtime",
        use_subject_digest="sha256:" + "d" * 64,
        current_authority_and_configuration_heads=heads,
        request_nonce="runtime-1",
        resolved_at=BASE + timedelta(minutes=4),
        expires_at=BASE + timedelta(minutes=4, seconds=10),
    )
    assert runtime.reusable is False
    assert runtime.grants_authority is False
    assert runtime.makes_participant_eligible is False

    expected = GovernedStateHeadPreconditionV1Alpha1.from_head(admitted.head)
    suspend = _packet(
        action=CompositionPolicyAction.SUSPEND,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=5),
        nonce="suspend-1",
        expected=expected,
    )
    suspended = await service.admit(
        plan=suspend[0], request=suspend[1], review=suspend[2], admitted_at=BASE + timedelta(minutes=5, seconds=3)
    )
    with pytest.raises(CompositionPolicyAdmissionError, match="suspended"):
        await service.resolve_runtime(
            product_id=PRODUCT,
            policy_id=POLICY,
            scope_ref=SCOPE,
            actor_ref="principal:runtime-actor",
            principal_ref="agent_principal:runtime-participant",
            use_subject_ref="task:suspended",
            use_subject_digest="sha256:" + "e" * 64,
            current_authority_and_configuration_heads=heads,
            request_nonce="runtime-suspended",
            resolved_at=BASE + timedelta(minutes=6),
            expires_at=BASE + timedelta(minutes=6, seconds=10),
        )
    recover = _packet(
        action=CompositionPolicyAction.RECOVER,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=7),
        nonce="recover-1",
        expected=GovernedStateHeadPreconditionV1Alpha1.from_head(suspended.head),
    )
    recovered = await service.admit(
        plan=recover[0], request=recover[1], review=recover[2], admitted_at=BASE + timedelta(minutes=7, seconds=3)
    )
    restarted = CompositionPolicyAdmissionService(
        governed_store=governed, audit_store=records, authority=PresentAuthority()
    )
    assert await restarted.reopen(product_id=PRODUCT, policy_id=POLICY) == recovered
    assert recovered.revision.lifecycle is CompositionPolicyLifecycle.ACTIVE

    superseding_proposal = type(proposal).model_validate(
        {
            **proposal.model_dump(mode="python"),
            "proposed_policy_rule_ref": "composition_policy_rule:dynamic-exact-scope-v2",
            "proposal_id": None,
            "proposal_digest": None,
        }
    )
    proposal_record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="measured_composition",
        record_kind="policy_change_proposal",
        record_key=str(superseding_proposal.proposal_id),
        payload_contract=superseding_proposal.contract,
        payload=superseding_proposal.model_dump(mode="python"),
        as_of=superseding_proposal.proposed_at,
        available_at=BASE + timedelta(minutes=8),
        processing_order=0,
    )
    await records.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT,
            record_space="measured_composition",
            transaction_key=f"ac7_superseding_proposal:{superseding_proposal.proposal_id}",
            records=(proposal_record,),
            submitted_at=BASE + timedelta(minutes=8),
        )
    )
    supersede = _packet(
        action=CompositionPolicyAction.SUPERSEDE,
        protocol=protocol,
        comparison=comparison,
        proposal=superseding_proposal,
        heads=heads,
        at=BASE + timedelta(minutes=9),
        nonce="supersede-1",
        expected=GovernedStateHeadPreconditionV1Alpha1.from_head(recovered.head),
    )
    superseded = await service.admit(
        plan=supersede[0],
        request=supersede[1],
        review=supersede[2],
        admitted_at=BASE + timedelta(minutes=9, seconds=3),
    )
    assert superseded.revision.sequence == recovered.revision.sequence + 1
    assert superseded.revision.proposal == measured_composition_reference(superseding_proposal)

    rollback = _packet(
        action=CompositionPolicyAction.ROLLBACK,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=11),
        nonce="rollback-1",
        expected=GovernedStateHeadPreconditionV1Alpha1.from_head(superseded.head),
        rollback_target=composition_policy_reference(recovered.revision),
    )
    rolled_back = await service.admit(
        plan=rollback[0],
        request=rollback[1],
        review=rollback[2],
        admitted_at=BASE + timedelta(minutes=11, seconds=3),
    )
    assert rolled_back.revision.action is CompositionPolicyAction.ROLLBACK
    assert rolled_back.revision.policy_rule_ref == recovered.revision.policy_rule_ref
    assert rolled_back.revision.revision_id != recovered.revision.revision_id


@pytest.mark.asyncio
async def test_rejection_is_durable_and_creates_no_policy_head() -> None:
    service, governed, records, protocol, comparison, proposal, heads = await _environment()
    packet = _packet(
        action=CompositionPolicyAction.ADMIT,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=3),
        nonce="reject-1",
        disposition=CompositionPolicyReviewDisposition.REJECT,
    )
    rejection = await service.reject(
        plan=packet[0], request=packet[1], review=packet[2], rejected_at=BASE + timedelta(minutes=3, seconds=3)
    )
    assert rejection.creates_policy_head is False
    assert await service.reopen(product_id=PRODUCT, policy_id=POLICY) is None
    assert any(record.record_kind == "rejection" for record in records.records.values())
    assert not any(key[0] == "composition_policy" for key in governed.heads)


@pytest.mark.asyncio
async def test_stale_head_concurrent_adoption_self_approval_revocation_and_duplicate_nonce_fail_closed() -> None:
    service, _, _, protocol, comparison, proposal, heads = await _environment()
    packet = _packet(
        action=CompositionPolicyAction.ADMIT,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=3),
        nonce="admit-1",
    )
    admitted = await service.admit(
        plan=packet[0], request=packet[1], review=packet[2], admitted_at=BASE + timedelta(minutes=3, seconds=3)
    )
    stale = GovernedStateHeadPreconditionV1Alpha1.from_head(admitted.head)
    suspend = _packet(
        action=CompositionPolicyAction.SUSPEND,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=4),
        nonce="suspend-good",
        expected=stale,
    )
    await service.admit(
        plan=suspend[0], request=suspend[1], review=suspend[2], admitted_at=BASE + timedelta(minutes=4, seconds=3)
    )
    stale_again = _packet(
        action=CompositionPolicyAction.SUSPEND,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=5),
        nonce="suspend-stale",
        expected=stale,
    )
    with pytest.raises(CompositionPolicyAdmissionError, match="stale expected"):
        await service.admit(
            plan=stale_again[0],
            request=stale_again[1],
            review=stale_again[2],
            admitted_at=BASE + timedelta(minutes=5, seconds=3),
        )

    changed_review = packet[2].model_copy(
        update={
            "reviewer_actor_ref": REQUESTER,
            "reviewer_principal_ref": REQUESTER_PRINCIPAL,
            "review_id": None,
            "review_digest": None,
        }
    )
    with pytest.raises(CompositionPolicyAdmissionError, match="self-approval"):
        await service.admit(
            plan=packet[0], request=packet[1], review=changed_review, admitted_at=BASE + timedelta(minutes=3, seconds=3)
        )

    current = await service.reopen(product_id=PRODUCT, policy_id=POLICY)
    assert current is not None
    recover = _packet(
        action=CompositionPolicyAction.RECOVER,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=6),
        nonce="recover-revoked",
        expected=GovernedStateHeadPreconditionV1Alpha1.from_head(current.head),
    )
    service.authority.revoked = True
    with pytest.raises(CompositionPolicyAdmissionError, match="authority resolution"):
        await service.admit(
            plan=recover[0],
            request=recover[1],
            review=recover[2],
            admitted_at=BASE + timedelta(minutes=6, seconds=3),
        )
    service.authority.revoked = False
    duplicate_nonce = _packet(
        action=CompositionPolicyAction.RECOVER,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=6),
        nonce="suspend-good",
        expected=GovernedStateHeadPreconditionV1Alpha1.from_head(current.head),
    )
    with pytest.raises(CompositionPolicyAdmissionError, match="audit append"):
        await service.admit(
            plan=duplicate_nonce[0],
            request=duplicate_nonce[1],
            review=duplicate_nonce[2],
            admitted_at=BASE + timedelta(minutes=6, seconds=3),
        )


@pytest.mark.asyncio
async def test_concurrent_compare_and_swap_allows_exactly_one_policy_head_transition() -> None:
    service, _, _, protocol, comparison, proposal, heads = await _environment()
    first = _packet(
        action=CompositionPolicyAction.ADMIT,
        protocol=protocol,
        comparison=comparison,
        proposal=proposal,
        heads=heads,
        at=BASE + timedelta(minutes=3),
        nonce="admit-concurrency",
    )
    admitted = await service.admit(
        plan=first[0], request=first[1], review=first[2], admitted_at=BASE + timedelta(minutes=3, seconds=3)
    )
    expected = GovernedStateHeadPreconditionV1Alpha1.from_head(admitted.head)
    packets = tuple(
        _packet(
            action=CompositionPolicyAction.SUSPEND,
            protocol=protocol,
            comparison=comparison,
            proposal=proposal,
            heads=heads,
            at=BASE + timedelta(minutes=4),
            nonce=f"concurrent-{index}",
            expected=expected,
        )
        for index in range(2)
    )
    outcomes = await asyncio.gather(
        *(
            service.admit(
                plan=packet[0],
                request=packet[1],
                review=packet[2],
                admitted_at=BASE + timedelta(minutes=4, seconds=3),
            )
            for packet in packets
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, CompositionPolicyAdmissionError) for item in outcomes) == 1
    current = await service.reopen(product_id=PRODUCT, policy_id=POLICY)
    assert current is not None
    assert current.revision.sequence == 2
    assert current.revision.lifecycle is CompositionPolicyLifecycle.SUSPENDED


def test_contracts_reject_proposal_self_activation_forbidden_effects_and_tampering() -> None:
    with pytest.raises(ValidationError):
        CompositionPolicyAdmissionPlanV1Alpha1(
            product_id=PRODUCT,
            policy_id=POLICY,
            scope_ref=SCOPE,
            action=CompositionPolicyAction.ADMIT,
            rationale="A proposal cannot activate itself.",
            created_at=BASE,
            expires_at=BASE + timedelta(minutes=1),
        )
    with pytest.raises(ValidationError, match="plan_digest"):
        CompositionPolicyAdmissionPlanV1Alpha1(
            product_id=PRODUCT,
            policy_id=POLICY,
            scope_ref=SCOPE,
            action=CompositionPolicyAction.SUSPEND,
            expected_current_head=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="composition_policy",
                product_id=PRODUCT,
                state_id=POLICY,
                sequence=1,
                revision_id="composition_policy_revision:one",
                commit_receipt_id="governed_state_commit:one",
            ),
            rationale="Tampered material.",
            created_at=BASE,
            expires_at=BASE + timedelta(minutes=1),
            plan_digest="sha256:" + "0" * 64,
        )


def test_provider_free_fixture_freezes_complete_fail_closed_and_public_surface_matrix() -> None:
    fixture = json.loads(AC7_FIXTURE.read_text())
    assert fixture["provider_required"] is False
    assert fixture["network_required"] is False
    assert fixture["credentials_required"] is False
    assert fixture["agent_memory_writes"] is False
    assert len(fixture["fail_closed"]) == 17
    assert fixture["runtime_invariants"] == {
        "receipt_reusable": False,
        "policy_grants_authority": False,
        "policy_makes_participant_eligible": False,
        "ac2_ac4_authority_revalidated_separately": True,
        "participant_heads_revalidated_separately": True,
        "task_scope_budget_revalidated_separately": True,
        "delivery_export_effect_revalidated_separately": True,
    }
    assert fixture["public_surface"]["package"] == "ace-core"
    assert fixture["public_surface"]["public_mcp_tool_count"] == 11
    assert fixture["public_surface"]["taskcreate_changed"] is False
    assert fixture["public_surface"]["schema_changed"] is False
    assert fixture["public_surface"]["am1_dependency"] is False


def test_provider_free_verifier_is_deterministic_across_fresh_processes() -> None:
    outputs = []
    for seed in ("1", "991"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
        completed = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_ac7_composition_policy_admission.py"), "--json"],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(json.loads(completed.stdout))
    assert outputs[0] == outputs[1]
    assert outputs[0]["status"] == "passed_provider_free_candidate_gate"
    assert outputs[0]["fail_closed_count"] == 17
    assert outputs[0]["public_mcp_tool_count"] == 11
