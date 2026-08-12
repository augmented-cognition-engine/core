"""AC4 agent onboarding, governance, restart, and negative conformance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ace.application.agent_governance import (
    ADMINISTER_LIFECYCLE_AUTHORITY,
    AGENT_BINDING_LIFECYCLE_STATE_KIND,
    AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
    AgentGovernanceError,
    AgentGovernanceService,
    agent_governance_head_id,
)
from ace.core import (
    AgentGovernanceCoordinateV1Alpha1,
    AgentPrincipalV1Alpha1,
    AppendOnlyTransactionRequestV1,
    AuthorityClass,
    CompositionBudgetV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    PrincipalKind,
    PrincipalLifecycle,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts import (
    AgentBindingLifecycleRevisionV1Alpha1,
    AgentBindingProposalV1Alpha1,
    AgentCompatibilityReceiptV1Alpha1,
    AgentConformanceReceiptV1Alpha1,
    AgentDefinitionDraftV1Alpha1,
    AgentDefinitionLifecycleRevisionV1Alpha1,
    AgentDefinitionProposalV1Alpha1,
    AgentDryRunReceiptV1Alpha1,
    AgentGrantRequestLifecycleRevisionV1Alpha1,
    AgentGrantRequestV1Alpha1,
    AgentPrincipalLifecycleRevisionV1Alpha1,
    AgentReviewDispositionV1Alpha1,
    AgentRuntimeHealthRevisionV1Alpha1,
    EvidenceDisposition,
    GovernedContentState,
    GrantRequestState,
    LifecycleStage,
    OrchestrationPattern,
    PrincipalLifecycleState,
    ProposalKind,
    ReviewActorClass,
    ReviewDisposition,
    RuntimeHealthState,
    StageRoleBindingDraftV1Alpha1,
    exact_registration_reference,
    project_approved_binding,
    project_approved_definition,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 11, 17, tzinfo=UTC)
PRODUCT = "product:agent-governance-conformance"
FIXTURE = Path(__file__).parents[2] / "evaluations/fixtures/ac4_agent_onboarding_governance_conformance_v1.json"


class MemoryGovernedStore:
    def __init__(self) -> None:
        self.heads = {}
        self.revisions = {}
        self.receipts = {}

    async def load_head(self, *, state_kind, product_id, state_id):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id, *, product_id):
        value = self.revisions.get((product_id, revision_id))
        return value

    async def load_receipt(self, receipt_id, *, product_id):
        return self.receipts.get((product_id, receipt_id))

    async def commit(self, request: GovernedStateCommitRequestV1):
        revision = request.revision
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current = self.heads.get(key)
        current_id = current.revision_id if current else None
        if current_id != request.expected_head_revision_id:
            raise RuntimeError("governed_state_head_conflict")
        receipt = request.receipt()
        existing = self.receipts.get((revision.product_id, receipt.receipt_id))
        if existing is not None:
            if existing == receipt:
                return existing
            raise RuntimeError("governed_state_replay_conflict")
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, receipt.receipt_id)] = receipt
        self.heads[key] = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        return receipt


class MemoryAuditStore:
    def __init__(self, governed: MemoryGovernedStore) -> None:
        self.governed = governed
        self.transactions = {}
        self.records = {}

    async def append(self, request: AppendOnlyTransactionRequestV1):
        for precondition in request.governed_state_preconditions:
            head = await self.governed.load_head(
                state_kind=precondition.state_kind,
                product_id=precondition.product_id,
                state_id=precondition.state_id,
            )
            if head is None or (
                head.sequence,
                head.revision_id,
                head.commit_receipt_id,
            ) != (
                precondition.sequence,
                precondition.revision_id,
                precondition.commit_receipt_id,
            ):
                raise RuntimeError("immutable_record_precondition_failed")
        key = (request.product_id, request.record_space, request.transaction_key)
        receipt = request.receipt()
        existing = self.transactions.get(key)
        if existing is not None:
            if existing == receipt:
                return existing
            raise RuntimeError("immutable_record_replay_conflict")
        self.transactions[key] = receipt
        for record in request.records:
            self.records[record.storage_id] = record
        return receipt

    async def load_record(self, storage_id, *, product_id, record_space, record_kind):
        record = self.records.get(storage_id)
        if record is None:
            return None
        if (record.product_id, record.record_space, record.record_kind) != (
            product_id,
            record_space,
            record_kind,
        ):
            return None
        return record

    async def load_transaction_receipt(self, *, product_id, record_space, transaction_key):
        return self.transactions.get((product_id, record_space, transaction_key))

    async def read_as_of(self, *, product_id, record_space, record_kind, available_at):
        return tuple(
            value
            for value in self.records.values()
            if value.product_id == product_id
            and value.record_space == record_space
            and value.record_kind == record_kind
            and value.available_at <= available_at
        )

    async def count_as_of(self, **kwargs):
        return len(await self.read_as_of(**kwargs))


class ExactAuthority:
    def __init__(self) -> None:
        self.revoked = set()
        self.grant_mismatch = set()

    async def resolve_approval(self, *, receipt_ref, product_id, subject_ref, actor_ref, effective_at):
        return ResolvedApprovalReceiptV1(
            receipt_ref=receipt_ref,
            product_id=product_id,
            subject_ref=subject_ref,
            actor_ref=actor_ref,
            receipt_hash="a" * 64,
            approved_at=effective_at,
        )

    async def resolve_grant(self, *, grant_ref, product_id, authority, effective_at):
        if grant_ref in self.revoked:
            raise RuntimeError("grant_revoked")
        return ResolvedAuthorityGrantV1(
            grant_ref=(f"different:{grant_ref}" if grant_ref in self.grant_mismatch else grant_ref),
            product_id=product_id,
            authority=authority,
            grant_hash="b" * 64,
            effective_at=effective_at,
            expires_at=effective_at + timedelta(hours=1),
        )


def _principal(kind: PrincipalKind = PrincipalKind.SERVICE, *, lifecycle_revision: int = 1):
    protocol = "ace.agent.model/v1" if kind is PrincipalKind.MODEL_AGENT else "ace.agent.service/v1"
    return AgentPrincipalV1Alpha1(
        product_id=PRODUCT,
        principal_key="bounded-worker",
        principal_kind=kind,
        owner_ref="operator:owner",
        implementation_ref="implementation:bounded-worker:v1",
        supported_protocol_versions=(protocol,),
        lifecycle=PrincipalLifecycle.SUSPENDED,
        lifecycle_revision=lifecycle_revision,
    )


def _definition_draft(principal, *, tools=("tool:read",), authority=(AuthorityClass.DERIVE_PROPOSE,)):
    return AgentDefinitionDraftV1Alpha1(
        principal_id=str(principal.principal_id),
        purpose="Produce one bounded typed record.",
        eligible_stages=(LifecycleStage.DELIBERATE,),
        accepted_input_contracts=("example.input/v1",),
        produced_output_contracts=("example.output/v1",),
        required_tool_refs=tools,
        maximum_authority=authority,
        budget_ceiling=CompositionBudgetV1Alpha1(max_items=1, max_calls=1, max_tokens=128),
        failure_policy_ref="policy:fail-closed",
        implementation_protocol_ref=principal.supported_protocol_versions[0],
    )


def _binding_draft(definition, *, tools=("tool:read",), authority=(AuthorityClass.DERIVE_PROPOSE,)):
    return StageRoleBindingDraftV1Alpha1(
        definition_revision=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(definition.definition_revision_id),
            artifact_digest=str(definition.definition_digest),
            artifact_contract=definition.contract,
        ),
        stage=LifecycleStage.DELIBERATE,
        role_label="bounded contributor",
        objective_class="typed_record",
        required_input_contracts=("example.input/v1",),
        expected_output_contracts=("example.output/v1",),
        exit_criteria_refs=("criterion:typed-output",),
        orchestration_patterns=(OrchestrationPattern.SOLO,),
        independence_policy_ref="policy:independent",
        tool_refs=tools,
        authority_ceiling=authority,
        budget_ceiling=CompositionBudgetV1Alpha1(max_items=1, max_calls=1, max_tokens=128),
        escalation_policy_ref="policy:escalate",
    )


def _review(
    proposal,
    kind,
    *,
    actor="human:reviewer",
    disposition=ReviewDisposition.APPROVE,
    expected_head_revision_id=None,
    reviewed_at=NOW + timedelta(minutes=1),
):
    return AgentReviewDispositionV1Alpha1(
        review_request_id=f"review:{kind.value}",
        proposal_kind=kind,
        proposal_id=str(proposal.proposal_id),
        proposal_digest=str(proposal.proposal_digest),
        actor_ref=actor,
        actor_class=ReviewActorClass.HUMAN,
        disposition=disposition,
        rationale="Exact bounded material reviewed.",
        expected_head_revision_id=expected_head_revision_id,
        reviewed_at=reviewed_at,
    )


async def _active_stack(kind: PrincipalKind = PrincipalKind.SERVICE):
    governed = MemoryGovernedStore()
    audit = MemoryAuditStore(governed)
    authority = ExactAuthority()
    service = AgentGovernanceService(governed_store=governed, audit_store=audit, authority=authority)
    principal = _principal(kind)
    governance = AgentGovernanceCoordinateV1Alpha1(product_id=PRODUCT, principal_key=principal.principal_key)
    registration = exact_registration_reference(principal)

    principal_one = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        registration_implementation_ref=principal.implementation_ref,
        registration_protocol_refs=principal.supported_protocol_versions,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=1,
        approval_receipt_ref="approval:principal:onboard",
        actor_ref="human:admin",
        occurred_at=NOW,
    )
    await service.admit_principal_lifecycle(
        principal_one,
        registration=principal,
        admin_grant_ref="grant:admin",
        committed_at=NOW,
    )

    definition_proposal = AgentDefinitionProposalV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        draft=_definition_draft(principal),
        requested_by="agent:proposer",
        rationale="Bounded service definition.",
        proposed_at=NOW,
    )
    recorded_definition = await service.record_definition_proposal(
        definition_proposal,
        base_definition=None,
    )
    definition_review = _review(definition_proposal, ProposalKind.DEFINITION)
    definition = project_approved_definition(
        definition_proposal,
        definition_review,
        lifecycle_ref=agent_governance_head_id(
            state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            governance=governance,
        ),
        prior_revision_ref=None,
    )
    definition_review = AgentReviewDispositionV1Alpha1(
        **definition_review.model_dump(
            mode="python",
            exclude={"result_revision_id", "result_revision_digest", "receipt_id", "receipt_digest"},
        ),
        result_revision_id=str(definition.definition_revision_id),
        result_revision_digest=str(definition.definition_digest),
    )
    await service.record_review(proposal=definition_proposal, disposition=definition_review)
    definition_one = AgentDefinitionLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        definition=definition,
        state=GovernedContentState.APPROVED,
        sequence=1,
        disposition_receipt_ref=str(definition_review.receipt_id),
        approval_receipt_ref="approval:definition",
        actor_ref="human:reviewer",
        occurred_at=NOW + timedelta(minutes=1),
    )
    await service.admit_definition_lifecycle(definition_one, committed_at=NOW + timedelta(minutes=1))

    binding_proposal = AgentBindingProposalV1Alpha1(
        governance=governance,
        binding_key="deliberate:bounded-contributor",
        draft=_binding_draft(definition),
        requested_by="agent:proposer",
        rationale="Bounded stage role.",
        proposed_at=NOW + timedelta(minutes=2),
    )
    recorded_binding = await service.record_binding_proposal(binding_proposal, base_binding=None)
    binding_review = _review(
        binding_proposal,
        ProposalKind.BINDING,
        reviewed_at=NOW + timedelta(minutes=2),
    )
    binding_key = binding_proposal.binding_key
    binding = project_approved_binding(
        binding_proposal,
        binding_review,
        lifecycle_ref=agent_governance_head_id(
            state_kind=AGENT_BINDING_LIFECYCLE_STATE_KIND,
            governance=governance,
            binding_key=binding_key,
        ),
        prior_binding_ref=None,
    )
    binding_review = AgentReviewDispositionV1Alpha1(
        **binding_review.model_dump(
            mode="python",
            exclude={"result_revision_id", "result_revision_digest", "receipt_id", "receipt_digest"},
        ),
        result_revision_id=str(binding.binding_revision_id),
        result_revision_digest=str(binding.binding_digest),
    )
    await service.record_review(proposal=binding_proposal, disposition=binding_review)
    binding_one = AgentBindingLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        binding_key=binding_key,
        binding=binding,
        state=GovernedContentState.APPROVED,
        sequence=1,
        disposition_receipt_ref=str(binding_review.receipt_id),
        approval_receipt_ref="approval:binding",
        actor_ref="human:reviewer",
        occurred_at=NOW + timedelta(minutes=2),
    )
    await service.admit_binding_lifecycle(binding_one, committed_at=NOW + timedelta(minutes=2))

    principal_active = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        registration_implementation_ref=principal.implementation_ref,
        registration_protocol_refs=principal.supported_protocol_versions,
        state=PrincipalLifecycleState.ACTIVE,
        sequence=2,
        prior_revision_id=str(principal_one.lifecycle_revision_id),
        approval_receipt_ref="approval:principal:activate",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=3),
    )
    await service.admit_principal_lifecycle(
        principal_active,
        registration=principal,
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=3),
    )
    definition_active = AgentDefinitionLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        definition=definition,
        state=GovernedContentState.ACTIVE,
        sequence=2,
        prior_revision_id=str(definition_one.lifecycle_revision_id),
        disposition_receipt_ref="disposition:definition:activate",
        approval_receipt_ref="approval:definition:activate",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=3),
    )
    await service.admit_definition_lifecycle(
        definition_active,
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=3),
    )
    binding_active = AgentBindingLifecycleRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        binding_key=binding_key,
        binding=binding,
        state=GovernedContentState.ACTIVE,
        sequence=2,
        prior_revision_id=str(binding_one.lifecycle_revision_id),
        disposition_receipt_ref="disposition:binding:activate",
        approval_receipt_ref="approval:binding:activate",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=3),
    )
    await service.admit_binding_lifecycle(
        binding_active,
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=3),
    )
    grants = AgentGrantRequestLifecycleRevisionV1Alpha1(
        governance=governance,
        requests=(
            AgentGrantRequestV1Alpha1(
                authority_class=AuthorityClass.DERIVE_PROPOSE,
                requested_grant_ref="grant:derive",
                scope_ref="scope:bounded-record",
                policy_ref="policy:bounded-record",
            ),
        ),
        state=GrantRequestState.REQUESTED,
        sequence=1,
        approval_receipt_ref="approval:grant-request",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=3),
    )
    await service.admit_grant_requests(grants, committed_at=NOW + timedelta(minutes=3))
    health = AgentRuntimeHealthRevisionV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        state=RuntimeHealthState.HEALTHY,
        implementation_ref=principal.implementation_ref,
        evidence_refs=("health:probe:one",),
        sequence=1,
        approval_receipt_ref="approval:health",
        actor_ref="core:supervisor",
        observed_at=NOW + timedelta(minutes=3),
    )
    await service.admit_runtime_health(
        health,
        registration=principal,
        committed_at=NOW + timedelta(minutes=3),
    )
    return {
        "service": service,
        "governed": governed,
        "audit": audit,
        "authority": authority,
        "principal": principal,
        "governance": governance,
        "registration": registration,
        "principal_active": principal_active,
        "definition": definition,
        "definition_active": definition_active,
        "binding": binding,
        "binding_key": binding_key,
        "binding_active": binding_active,
        "grants": grants,
        "health": health,
        "recorded_definition": recorded_definition,
        "recorded_binding": recorded_binding,
    }


def _evidence(stack, *, compatible=True):
    principal = stack["principal"]
    governance = stack["governance"]
    registration = stack["registration"]
    required = principal.supported_protocol_versions[0] if compatible else "ace.agent.unsupported/v1"
    compatibility = AgentCompatibilityReceiptV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        disposition=EvidenceDisposition.PASSED if compatible else EvidenceDisposition.FAILED,
        required_protocol_ref=required,
        supported_protocol_refs=principal.supported_protocol_versions,
        checked_at=NOW + timedelta(minutes=4),
    )
    conformance = AgentConformanceReceiptV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        disposition=EvidenceDisposition.PASSED,
        suite_ref="suite:agent-conformance-v1",
        case_refs=("case:bounded",),
        definition=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(stack["definition"].definition_revision_id),
            artifact_digest=str(stack["definition"].definition_digest),
            artifact_contract=stack["definition"].contract,
        ),
        binding=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(stack["binding"].binding_revision_id),
            artifact_digest=str(stack["binding"].binding_digest),
            artifact_contract=stack["binding"].contract,
        ),
        checked_at=NOW + timedelta(minutes=4),
    )
    dry_run = AgentDryRunReceiptV1Alpha1(
        governance=governance,
        registration_snapshot=registration,
        disposition=EvidenceDisposition.PASSED,
        definition=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(stack["definition"].definition_revision_id),
            artifact_digest=str(stack["definition"].definition_digest),
            artifact_contract=stack["definition"].contract,
        ),
        binding=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(stack["binding"].binding_revision_id),
            artifact_digest=str(stack["binding"].binding_digest),
            artifact_contract=stack["binding"].contract,
        ),
        checked_at=NOW + timedelta(minutes=4),
    )
    return compatibility, conformance, dry_run


def test_fixture_freezes_all_required_cases_and_non_authority_invariants() -> None:
    payload = json.loads(FIXTURE.read_text())
    assert [case["case_id"] for case in payload["cases"]] == [
        "deterministic_service",
        "model_agent",
        "adversarial_definition",
        "stale_approval",
        "widened_binding",
        "revoked_grant",
        "incompatible_protocol",
        "retired_principal",
    ]
    assert len(payload["required_head_kinds"]) == 5
    assert not any(payload["invariants"].values())


def test_stable_governance_coordinate_excludes_frozen_registration_snapshot_material() -> None:
    first = _principal()
    changed = _principal(lifecycle_revision=2).model_copy(
        update={"implementation_ref": "implementation:bounded-worker:v2"}
    )
    coordinate = AgentGovernanceCoordinateV1Alpha1(product_id=PRODUCT, principal_key=first.principal_key)
    replay = AgentGovernanceCoordinateV1Alpha1(product_id=PRODUCT, principal_key=changed.principal_key)
    assert coordinate == replay
    assert first.principal_id != changed.principal_id
    with pytest.raises(ValueError, match="derive only"):
        AgentGovernanceCoordinateV1Alpha1(
            product_id=PRODUCT,
            principal_key=first.principal_key,
            governance_id="agent_governance:spoofed",
        )


async def test_first_lifecycle_exactly_binds_snapshot_and_starts_suspended() -> None:
    governed = MemoryGovernedStore()
    service = AgentGovernanceService(
        governed_store=governed,
        audit_store=MemoryAuditStore(governed),
        authority=ExactAuthority(),
    )
    principal = _principal()
    coordinate = AgentGovernanceCoordinateV1Alpha1(product_id=PRODUCT, principal_key=principal.principal_key)
    with pytest.raises(ValueError, match="begins suspended"):
        AgentPrincipalLifecycleRevisionV1Alpha1(
            governance=coordinate,
            registration_snapshot=exact_registration_reference(principal),
            registration_implementation_ref=principal.implementation_ref,
            registration_protocol_refs=principal.supported_protocol_versions,
            state=PrincipalLifecycleState.ACTIVE,
            sequence=1,
            approval_receipt_ref="approval:onboard",
            actor_ref="human:admin",
            occurred_at=NOW,
        )
    revision = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=coordinate,
        registration_snapshot=exact_registration_reference(principal),
        registration_implementation_ref=principal.implementation_ref,
        registration_protocol_refs=principal.supported_protocol_versions,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=1,
        approval_receipt_ref="approval:onboard",
        actor_ref="human:admin",
        occurred_at=NOW,
    )
    wrong = principal.model_copy(update={"principal_key": "different-key"})
    with pytest.raises(AgentGovernanceError, match="exact registration snapshot"):
        await service.admit_principal_lifecycle(
            revision,
            registration=wrong,
            admin_grant_ref="grant:admin",
            committed_at=NOW,
        )


async def test_deterministic_and_model_agents_activate_only_after_five_current_heads() -> None:
    for kind in (PrincipalKind.SERVICE, PrincipalKind.MODEL_AGENT):
        stack = await _active_stack(kind)
        compatibility, conformance, dry_run = _evidence(stack)
        receipt, durable = await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=5),
        )
        assert receipt.no_effect is True
        assert receipt.reusable_authority is False
        assert tuple(item.grant_ref for item in receipt.resolved_grants) == ("grant:derive",)
        assert receipt.lifecycle_authority.grant_ref == "grant:admin"
        assert len(durable.governed_state_preconditions) == 5


async def test_proposal_diff_review_and_reopen_are_exact_and_auditable() -> None:
    stack = await _active_stack()
    assert stack["recorded_definition"].diff.changes
    assert stack["recorded_binding"].diff.changes
    reopened = AgentGovernanceService(
        governed_store=stack["governed"],
        audit_store=stack["audit"],
        authority=stack["authority"],
    )
    view = await reopened.inspect(
        governance=stack["governance"],
        binding_keys=(stack["binding_key"],),
    )
    assert view.principal_lifecycle == stack["principal_active"]
    assert view.definition_lifecycle == stack["definition_active"]
    assert view.binding_lifecycles == (stack["binding_active"],)
    assert view.grant_requests == stack["grants"]
    assert view.runtime_health == stack["health"]
    audit = await reopened.audit(
        governance=stack["governance"],
        available_at=NOW + timedelta(hours=1),
    )
    assert {item.record_kind for item in audit} >= {
        "definition_proposal",
        "binding_proposal",
        "semantic_diff",
        "review_disposition",
        "lifecycle_revision",
        "governed_state_commit_receipt",
    }


async def test_compatibility_replacement_preserves_history_and_carries_no_authority() -> None:
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
    legacy = ExactArtifactReferenceV1Alpha1(
        artifact_id="compatibility_participant:ac3-service",
        artifact_digest="sha256:" + "c" * 64,
        artifact_contract="ace.application.lifecycle-participant-reference/v1alpha1",
    )
    replacement, durable = await stack["service"].replace_compatibility_participant(
        compatibility_participant=legacy,
        governance=stack["governance"],
        binding_key=stack["binding_key"],
        activation=activation,
        replaced_at=NOW + timedelta(minutes=6),
    )
    assert replacement.compatibility_participant == legacy
    assert replacement.rewrites_history is False
    assert replacement.carries_authority_forward is False
    assert replacement.reusable_authority is False
    assert len(durable.governed_state_preconditions) == 5


async def test_adversarial_definition_cannot_self_approve_or_self_activate() -> None:
    stack = await _active_stack()
    proposal = AgentDefinitionProposalV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        draft=_definition_draft(stack["principal"]),
        requested_by="agent:self",
        rationale="Attempt self approval.",
        proposed_at=NOW + timedelta(minutes=6),
    )
    review = _review(proposal, ProposalKind.DEFINITION, actor="agent:self")
    before = len(stack["audit"].records)
    with pytest.raises(AgentGovernanceError, match="Self-approval|self-approval"):
        await stack["service"].record_review(proposal=proposal, disposition=review)
    assert len(stack["audit"].records) == before
    compatibility, conformance, dry_run = _evidence(stack)
    with pytest.raises(AgentGovernanceError, match="self-activation"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref=str(stack["principal"].principal_id),
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=6),
        )


async def test_stale_definition_approval_leaves_current_head_unchanged() -> None:
    stack = await _active_stack()
    stale = AgentDefinitionLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        definition=stack["definition"],
        state=GovernedContentState.SUSPENDED,
        sequence=2,
        prior_revision_id=str(stack["definition_active"].prior_revision_id),
        disposition_receipt_ref="disposition:stale",
        approval_receipt_ref="approval:stale",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=6),
    )
    before = await stack["service"].inspect(governance=stack["governance"])
    with pytest.raises(AgentGovernanceError, match="stale or superseded"):
        await stack["service"].admit_definition_lifecycle(
            stale,
            admin_grant_ref="grant:admin",
            committed_at=NOW + timedelta(minutes=6),
        )
    after = await stack["service"].inspect(governance=stack["governance"])
    assert after.definition_lifecycle == before.definition_lifecycle


async def test_stale_review_disposition_is_not_appended() -> None:
    stack = await _active_stack()
    current = stack["definition_active"]
    base = ExactArtifactReferenceV1Alpha1(
        artifact_id=str(current.definition.definition_revision_id),
        artifact_digest=str(current.definition.definition_digest),
        artifact_contract=current.definition.contract,
    )
    proposal = AgentDefinitionProposalV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        draft=_definition_draft(stack["principal"]),
        base_definition=base,
        requested_by="agent:proposer",
        rationale="Revise exact current definition.",
        proposed_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].record_definition_proposal(proposal, base_definition=current)
    stale = _review(
        proposal,
        ProposalKind.DEFINITION,
        expected_head_revision_id="agent_definition_lifecycle_revision:stale",
        reviewed_at=NOW + timedelta(minutes=6),
    )
    before = len(stack["audit"].records)
    with pytest.raises(AgentGovernanceError, match="stale for the exact current head"):
        await stack["service"].record_review(proposal=proposal, disposition=stale)
    assert len(stack["audit"].records) == before


async def test_definition_content_cannot_claim_a_different_review_disposition() -> None:
    stack = await _active_stack()
    mismatched = stack["definition"].model_copy(
        update={
            "approval_receipt_ref": "agent_review_disposition:different",
            "definition_revision_id": None,
            "definition_digest": None,
        }
    )
    mismatched = type(stack["definition"]).model_validate(mismatched.model_dump(mode="python"))
    revision = AgentDefinitionLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        definition=mismatched,
        state=GovernedContentState.APPROVED,
        sequence=3,
        prior_revision_id=str(stack["definition_active"].lifecycle_revision_id),
        disposition_receipt_ref="agent_review_disposition:expected",
        approval_receipt_ref="approval:definition:revision",
        actor_ref="human:reviewer",
        occurred_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(AgentGovernanceError, match="exact review disposition"):
        await stack["service"].admit_definition_lifecycle(
            revision,
            committed_at=NOW + timedelta(minutes=6),
        )


async def test_widened_binding_is_rejected_without_head_change() -> None:
    stack = await _active_stack()
    widened = stack["binding"].model_copy(
        update={
            "tool_refs": ("tool:read", "tool:write"),
            "binding_revision_id": None,
            "binding_digest": None,
        }
    )
    widened = type(stack["binding"]).model_validate(widened.model_dump(mode="python"))
    revision = AgentBindingLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        binding_key=stack["binding_key"],
        binding=widened,
        state=GovernedContentState.APPROVED,
        sequence=3,
        prior_revision_id=str(stack["binding_active"].lifecycle_revision_id),
        disposition_receipt_ref="disposition:widened",
        approval_receipt_ref="approval:widened",
        actor_ref="human:reviewer",
        occurred_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(AgentGovernanceError, match="widens definition tools"):
        await stack["service"].admit_binding_lifecycle(
            revision,
            committed_at=NOW + timedelta(minutes=6),
        )


async def test_revoked_grant_and_incompatible_protocol_create_no_activation_receipt() -> None:
    stack = await _active_stack()
    before = len(stack["audit"].records)
    stack["authority"].revoked.add("grant:derive")
    with pytest.raises(AgentGovernanceError, match="grant admission failed closed"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=_evidence(stack)[0],
            conformance=_evidence(stack)[1],
            dry_run=_evidence(stack)[2],
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=6),
        )
    assert len(stack["audit"].records) == before
    stack["authority"].revoked.clear()
    compatibility, conformance, dry_run = _evidence(stack, compatible=False)
    with pytest.raises(AgentGovernanceError, match="evidence is not exact and passing"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=6),
        )
    assert len(stack["audit"].records) == before


async def test_runtime_health_can_only_constrain_and_retirement_blocks_retry() -> None:
    stack = await _active_stack()
    health = AgentRuntimeHealthRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        state=RuntimeHealthState.QUARANTINED,
        implementation_ref=stack["principal"].implementation_ref,
        evidence_refs=("health:incident",),
        sequence=2,
        prior_revision_id=str(stack["health"].health_revision_id),
        approval_receipt_ref="approval:health:quarantine",
        actor_ref="core:supervisor",
        observed_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].admit_runtime_health(
        health,
        registration=stack["principal"],
        committed_at=NOW + timedelta(minutes=6),
    )
    assert health.grants_authority is False
    compatibility, conformance, dry_run = _evidence(stack)
    with pytest.raises(AgentGovernanceError, match="health blocks"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=7),
        )
    retired = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        registration_implementation_ref=stack["principal"].implementation_ref,
        registration_protocol_refs=stack["principal"].supported_protocol_versions,
        state=PrincipalLifecycleState.RETIRED,
        sequence=3,
        prior_revision_id=str(stack["principal_active"].lifecycle_revision_id),
        approval_receipt_ref="approval:principal:retire",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=8),
    )
    await stack["service"].admit_principal_lifecycle(
        retired,
        registration=stack["principal"],
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=8),
    )
    assert stack["recorded_definition"].transaction_receipt in stack["audit"].transactions.values()
    with pytest.raises(AgentGovernanceError, match="suspended, revoked, or retired"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=9),
        )


async def test_registration_supersession_never_silently_retargets_definition() -> None:
    stack = await _active_stack()
    replacement = AgentPrincipalV1Alpha1(
        **stack["principal"].model_dump(
            mode="python",
            exclude={"implementation_ref", "lifecycle_revision", "principal_id", "principal_digest"},
        ),
        implementation_ref="implementation:bounded-worker:v2",
        lifecycle_revision=2,
    )
    suspended = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=exact_registration_reference(replacement),
        registration_implementation_ref=replacement.implementation_ref,
        registration_protocol_refs=replacement.supported_protocol_versions,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=3,
        prior_revision_id=str(stack["principal_active"].lifecycle_revision_id),
        approval_receipt_ref="approval:principal:replace",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].admit_principal_lifecycle(
        suspended,
        registration=replacement,
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=6),
    )
    replacement_active = AgentPrincipalLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=exact_registration_reference(replacement),
        registration_implementation_ref=replacement.implementation_ref,
        registration_protocol_refs=replacement.supported_protocol_versions,
        state=PrincipalLifecycleState.ACTIVE,
        sequence=4,
        prior_revision_id=str(suspended.lifecycle_revision_id),
        approval_receipt_ref="approval:principal:replace-active",
        actor_ref="human:admin",
        occurred_at=NOW + timedelta(minutes=7),
    )
    await stack["service"].admit_principal_lifecycle(
        replacement_active,
        registration=replacement,
        admin_grant_ref="grant:admin",
        committed_at=NOW + timedelta(minutes=7),
    )
    compatibility, conformance, dry_run = _evidence(stack)
    with pytest.raises(AgentGovernanceError, match="superseded registration snapshot"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=8),
        )


async def test_audit_filters_other_principals_in_the_same_product() -> None:
    stack = await _active_stack()
    other = AgentPrincipalV1Alpha1(
        **stack["principal"].model_dump(
            mode="python",
            exclude={"principal_key", "principal_id", "principal_digest"},
        ),
        principal_key="other-worker",
    )
    other_governance = AgentGovernanceCoordinateV1Alpha1(
        product_id=PRODUCT,
        principal_key=other.principal_key,
    )
    other_proposal = AgentDefinitionProposalV1Alpha1(
        governance=other_governance,
        registration_snapshot=exact_registration_reference(other),
        draft=_definition_draft(other),
        requested_by="agent:other-proposer",
        rationale="Other bounded definition.",
        proposed_at=NOW + timedelta(minutes=6),
    )
    await stack["service"].record_definition_proposal(other_proposal, base_definition=None)
    records = await stack["service"].audit(
        governance=stack["governance"],
        available_at=NOW + timedelta(hours=1),
    )
    assert all(item.payload.get("proposal_id") != other_proposal.proposal_id for item in records)


async def test_model_copy_cannot_poison_a_current_lifecycle_head() -> None:
    stack = await _active_stack()
    forged = stack["principal_active"].model_copy(update={"state": PrincipalLifecycleState.RETIRED})
    before = await stack["service"].inspect(governance=stack["governance"])
    with pytest.raises(AgentGovernanceError, match="exact boundary revalidation"):
        await stack["service"].admit_principal_lifecycle(
            forged,
            registration=stack["principal"],
            admin_grant_ref="grant:admin",
            committed_at=NOW + timedelta(minutes=6),
        )
    after = await stack["service"].inspect(governance=stack["governance"])
    assert after.principal_lifecycle == before.principal_lifecycle


async def test_unrecorded_review_cannot_admit_forged_revised_content() -> None:
    stack = await _active_stack()
    current = stack["definition_active"]
    proposal = AgentDefinitionProposalV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        draft=stack["recorded_definition"].proposal.draft.model_copy(update={"purpose": "Forged unreviewed content."}),
        base_definition=ExactArtifactReferenceV1Alpha1(
            artifact_id=str(current.definition.definition_revision_id),
            artifact_digest=str(current.definition.definition_digest),
            artifact_contract=current.definition.contract,
        ),
        requested_by="agent:proposer",
        rationale="This proposal is intentionally never recorded.",
        proposed_at=NOW + timedelta(minutes=6),
    )
    review = _review(
        proposal,
        ProposalKind.DEFINITION,
        expected_head_revision_id=str(current.lifecycle_revision_id),
        reviewed_at=NOW + timedelta(minutes=6),
    )
    definition = project_approved_definition(
        proposal,
        review,
        lifecycle_ref=current.definition.lifecycle_ref,
        prior_revision_ref=str(current.definition.definition_revision_id),
    )
    review = AgentReviewDispositionV1Alpha1(
        **review.model_dump(
            mode="python",
            exclude={"result_revision_id", "result_revision_digest", "receipt_id", "receipt_digest"},
        ),
        result_revision_id=str(definition.definition_revision_id),
        result_revision_digest=str(definition.definition_digest),
    )
    revision = AgentDefinitionLifecycleRevisionV1Alpha1(
        governance=stack["governance"],
        registration_snapshot=stack["registration"],
        definition=definition,
        state=GovernedContentState.APPROVED,
        sequence=3,
        prior_revision_id=str(current.lifecycle_revision_id),
        disposition_receipt_ref=str(review.receipt_id),
        approval_receipt_ref="approval:forged",
        actor_ref="human:reviewer",
        occurred_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(AgentGovernanceError, match="review_disposition record is unavailable"):
        await stack["service"].admit_definition_lifecycle(
            revision,
            committed_at=NOW + timedelta(minutes=6),
        )


async def test_activation_requires_current_admin_authority_and_nonfuture_evidence() -> None:
    stack = await _active_stack()
    compatibility, conformance, dry_run = _evidence(stack)
    stack["authority"].revoked.add("grant:admin")
    with pytest.raises(AgentGovernanceError, match="lifecycle authority resolution failed closed"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=conformance,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=5),
        )
    stack["authority"].revoked.clear()
    future = type(conformance).model_validate(
        conformance.model_copy(
            update={"checked_at": NOW + timedelta(hours=1), "receipt_id": None, "receipt_digest": None}
        ).model_dump(mode="python")
    )
    with pytest.raises(AgentGovernanceError, match="cannot postdate activation"):
        await stack["service"].activate(
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            compatibility=compatibility,
            conformance=future,
            dry_run=dry_run,
            actor_ref="human:admin",
            admin_grant_ref="grant:admin",
            activated_at=NOW + timedelta(minutes=5),
        )


async def test_compatibility_replacement_rejects_constructible_unrecorded_activation() -> None:
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
    fabricated = type(activation).model_validate(
        activation.model_copy(
            update={"actor_ref": "human:other", "receipt_id": None, "receipt_digest": None}
        ).model_dump(mode="python")
    )
    legacy = ExactArtifactReferenceV1Alpha1(
        artifact_id="compatibility_participant:unrecorded",
        artifact_digest="sha256:" + "d" * 64,
        artifact_contract="ace.application.lifecycle-participant-reference/v1alpha1",
    )
    with pytest.raises(AgentGovernanceError, match="activation_receipt record is unavailable"):
        await stack["service"].replace_compatibility_participant(
            compatibility_participant=legacy,
            governance=stack["governance"],
            binding_key=stack["binding_key"],
            activation=fabricated,
            replaced_at=NOW + timedelta(minutes=6),
        )


def test_requested_grants_and_no_effect_evidence_never_claim_authority() -> None:
    coordinate = AgentGovernanceCoordinateV1Alpha1(product_id=PRODUCT, principal_key="bounded-worker")
    requests = AgentGrantRequestLifecycleRevisionV1Alpha1(
        governance=coordinate,
        requests=(),
        state=GrantRequestState.REQUESTED,
        sequence=1,
        approval_receipt_ref="approval:request",
        actor_ref="human:admin",
        occurred_at=NOW,
    )
    assert requests.grants_authority is False
    assert ADMINISTER_LIFECYCLE_AUTHORITY not in requests.model_dump_json()
