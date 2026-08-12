"""Governed admission and present-tense resolution of composition policy.

The service composes existing Core authority, governed-state, and immutable
record ports.  It never interprets an AC6 proposal as live state and never
uses a historical approval or commit receipt as current authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from pydantic_core import to_json

from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.composition_policy import (
    COMPOSITION_POLICY_REVISION_VERSION,
    CompositionPolicyAction,
    CompositionPolicyAdmissionPlanV1Alpha1,
    CompositionPolicyAdmissionReceiptV1Alpha1,
    CompositionPolicyAdmissionRequestV1Alpha1,
    CompositionPolicyLifecycle,
    CompositionPolicyRejectionV1Alpha1,
    CompositionPolicyReviewDisposition,
    CompositionPolicyReviewV1Alpha1,
    CompositionPolicyRevisionV1Alpha1,
    CompositionPolicyRuntimeResolutionReceiptV1Alpha1,
    composition_policy_reference,
)
from ace.intelligence.contracts.measured_composition import (
    COMPOSITION_CONDITION_ASSIGNMENT_VERSION,
    COMPOSITION_EVALUATION_PROTOCOL_VERSION,
    COMPOSITION_MATCHED_COMPARISON_VERSION,
    COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION,
    COMPOSITION_RUN_OBSERVATION_VERSION,
    CompositionConditionAssignmentV1Alpha1,
    CompositionEvaluationProtocolV1Alpha1,
    CompositionMatchedComparisonV1Alpha1,
    CompositionPolicyChangeProposalV1Alpha1,
    CompositionRunObservationV1Alpha1,
    measured_composition_reference,
)
from ace.intelligence.measured_composition import compare_measured_composition

COMPOSITION_POLICY_STATE_KIND = "composition_policy"
COMPOSITION_POLICY_RECORD_SPACE = "composition_policy_governance"
ADMINISTER_COMPOSITION_POLICY_AUTHORITY = "administer_composition_policy"

_AC6_RECORDS: dict[str, tuple[str, type[BaseModel]]] = {
    COMPOSITION_EVALUATION_PROTOCOL_VERSION: ("evaluation_protocol", CompositionEvaluationProtocolV1Alpha1),
    COMPOSITION_CONDITION_ASSIGNMENT_VERSION: ("condition_assignment", CompositionConditionAssignmentV1Alpha1),
    COMPOSITION_RUN_OBSERVATION_VERSION: ("run_observation", CompositionRunObservationV1Alpha1),
    COMPOSITION_MATCHED_COMPARISON_VERSION: ("matched_comparison", CompositionMatchedComparisonV1Alpha1),
    COMPOSITION_POLICY_CHANGE_PROPOSAL_VERSION: ("policy_change_proposal", CompositionPolicyChangeProposalV1Alpha1),
}

_FORBIDDEN_POLICY_MARKERS = (
    "grant_authority",
    "grants_authority",
    "changes_roster",
    "make_eligible",
    "makes_eligible",
    "model_selection",
    "provider_selection",
    "schedule_execution",
    "execute_effect",
    "external_effect",
    "deliver_external",
    "export_external",
    "agent_lifecycle",
    "agent_memory",
)


class CompositionPolicyAdmissionError(RuntimeError):
    """Policy governance failed closed before returning a usable head/receipt."""


@dataclass(frozen=True, slots=True)
class CommittedCompositionPolicy:
    revision: CompositionPolicyRevisionV1Alpha1
    commit_receipt: GovernedStateCommitReceiptV1
    head: GovernedStateHeadV1
    admission_receipt: CompositionPolicyAdmissionReceiptV1Alpha1
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False


def _exact(model: type[BaseModel], value: object, *, name: str):
    try:
        return model.model_validate_json(to_json(value.model_dump(mode="python")))
    except Exception:
        raise CompositionPolicyAdmissionError(f"{name} failed exact boundary revalidation") from None


def _envelope(revision: CompositionPolicyRevisionV1Alpha1) -> GovernedStateRevisionV1:
    return GovernedStateRevisionV1(
        state_kind=COMPOSITION_POLICY_STATE_KIND,
        product_id=revision.product_id,
        state_id=revision.policy_id,
        sequence=revision.sequence,
        revision_id=str(revision.revision_id),
        material_hash=str(revision.revision_digest).removeprefix("sha256:"),
        prior_revision_id=revision.prior_revision_id,
        approval_subject_ref=str(revision.plan.artifact_id),
        payload_contract=COMPOSITION_POLICY_REVISION_VERSION,
        payload=revision.model_dump(mode="python"),
    )


def _head_matches(left: GovernedStateHeadV1, right: GovernedStateHeadPreconditionV1Alpha1) -> bool:
    return (
        left.state_kind == right.state_kind
        and left.product_id == right.product_id
        and left.state_id == right.state_id
        and left.sequence == right.sequence
        and left.revision_id == right.revision_id
        and left.commit_receipt_id == right.commit_receipt_id
    )


class CompositionPolicyAdmissionService:
    """Review, reject, admit, suspend, recover, rollback, and resolve policy."""

    def __init__(
        self,
        *,
        governed_store: GovernedStateStore,
        audit_store: ImmutableRecordStore,
        authority: CoreAuthorityResolver,
    ) -> None:
        self.governed_store = governed_store
        self.audit_store = audit_store
        self.authority = authority

    async def _load_ac6(self, reference, *, product_id: str):
        layout = _AC6_RECORDS.get(reference.artifact_contract)
        if layout is None:
            raise CompositionPolicyAdmissionError("foreign AC6 artifact contract")
        kind, model = layout
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space="measured_composition",
            record_kind=kind,
            record_key=reference.artifact_id,
        )
        try:
            record = await self.audit_store.load_record(
                storage_id,
                product_id=product_id,
                record_space="measured_composition",
                record_kind=kind,
            )
        except Exception:
            raise CompositionPolicyAdmissionError("AC6 durable evidence owner is unavailable") from None
        if record is None or record.payload_contract != reference.artifact_contract:
            raise CompositionPolicyAdmissionError("required exact AC6 evidence is unavailable")
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception:
            raise CompositionPolicyAdmissionError("AC6 evidence failed exact revalidation") from None
        if measured_composition_reference(value) != reference:
            raise CompositionPolicyAdmissionError("AC6 evidence changed from its content address")
        return value

    async def _validate_ac6_lineage(
        self, plan: CompositionPolicyAdmissionPlanV1Alpha1, *, evaluated_at: datetime
    ) -> CompositionPolicyChangeProposalV1Alpha1 | None:
        if plan.proposal is None:
            return None
        protocol = await self._load_ac6(plan.protocol, product_id=plan.product_id)
        comparison = await self._load_ac6(plan.comparison, product_id=plan.product_id)
        proposal = await self._load_ac6(plan.proposal, product_id=plan.product_id)
        assignment = await self._load_ac6(comparison.assignment, product_id=plan.product_id)
        observations = tuple(
            [
                await self._load_ac6(item.observation, product_id=plan.product_id)
                for item in comparison.condition_results
            ]
        )
        if (
            proposal.product_id != plan.product_id
            or proposal.scope_ref != plan.scope_ref
            or proposal.protocol != plan.protocol
            or proposal.comparison != plan.comparison
            or comparison.protocol != plan.protocol
            or protocol.current_governed_heads != plan.frozen_ac6_authority_lineage
            or proposal.proposed_policy_rule_ref != plan.proposed_policy_rule_ref
            or proposal.proposed_at > evaluated_at
            or comparison.compared_at > evaluated_at
        ):
            raise CompositionPolicyAdmissionError("policy plan crossed exact AC6 protocol/comparison/proposal lineage")
        try:
            recomputed_comparison, recomputed_proposal = compare_measured_composition(
                protocol,
                assignment,
                observations,
                current_policy=proposal.current_policy,
                proposed_policy_rule_ref=proposal.proposed_policy_rule_ref,
                compared_at=comparison.compared_at,
            )
        except Exception:
            raise CompositionPolicyAdmissionError("AC6 positive-result threshold no longer validates") from None
        if recomputed_comparison != comparison or recomputed_proposal != proposal:
            raise CompositionPolicyAdmissionError("AC6 positive-result threshold no longer validates")
        inert_flags = (
            proposal.live_effect,
            proposal.activates_policy,
            proposal.changes_roster,
            proposal.grants_authority,
            proposal.schedules_execution,
            proposal.delivers,
            proposal.exports,
            proposal.sends_external_effect,
            proposal.writes_agent_memory,
            proposal.trains_or_rewrites_policy,
        )
        if any(inert_flags) or not proposal.requires_present_tense_approval or not proposal.requires_separate_admission:
            raise CompositionPolicyAdmissionError("AC6 proposal is not inert and non-authorizing")
        return proposal

    def _validate_common(
        self,
        plan: CompositionPolicyAdmissionPlanV1Alpha1,
        request: CompositionPolicyAdmissionRequestV1Alpha1,
        review: CompositionPolicyReviewV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> None:
        if (
            request.plan != composition_policy_reference(plan)
            or review.plan != request.plan
            or review.request != composition_policy_reference(request)
            or (plan.product_id, plan.policy_id, plan.scope_ref)
            != (request.product_id, request.policy_id, request.scope_ref)
            or (plan.product_id, plan.policy_id, plan.scope_ref)
            != (review.product_id, review.policy_id, review.scope_ref)
            or request.expected_current_head != plan.expected_current_head
        ):
            raise CompositionPolicyAdmissionError("plan, request, and review crossed exact scope or material")
        if (
            review.reviewer_actor_ref == request.requester_actor_ref
            or review.reviewer_principal_ref == request.requester_principal_ref
            or review.reviewer_actor_ref != request.administrator_actor_ref
            or review.reviewer_principal_ref != request.administrator_principal_ref
        ):
            raise CompositionPolicyAdmissionError("self-approval or reviewer/administrator mismatch")
        if not (
            plan.created_at <= request.requested_at <= review.reviewed_at <= evaluated_at
            and evaluated_at < plan.expires_at
            and evaluated_at < request.expires_at
        ):
            raise CompositionPolicyAdmissionError("policy transaction is future-dated, stale, or expired")
        selection_material = (
            *((plan.proposed_policy_rule_ref,) if plan.proposed_policy_rule_ref is not None else ()),
            *plan.selection_constraints,
            *plan.selection_preferences,
        )
        lowered = "\n".join(selection_material).lower()
        if any(marker in lowered for marker in _FORBIDDEN_POLICY_MARKERS):
            raise CompositionPolicyAdmissionError(
                "selection policy embeds forbidden authority, eligibility, or effect semantics"
            )

    async def _require_heads(self, heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]) -> None:
        for expected in heads:
            try:
                current = await self.governed_store.load_head(
                    state_kind=expected.state_kind,
                    product_id=expected.product_id,
                    state_id=expected.state_id,
                )
            except Exception:
                raise CompositionPolicyAdmissionError("durable governed-state owner is unavailable") from None
            if current is None or not _head_matches(current, expected):
                raise CompositionPolicyAdmissionError("current Core authority/configuration head is missing or stale")

    async def _load_current(self, *, product_id: str, policy_id: str) -> CommittedCompositionPolicy | None:
        try:
            head = await self.governed_store.load_head(
                state_kind=COMPOSITION_POLICY_STATE_KIND,
                product_id=product_id,
                state_id=policy_id,
            )
        except Exception:
            raise CompositionPolicyAdmissionError("durable policy owner is unavailable") from None
        if head is None:
            return None
        try:
            envelope = await self.governed_store.load_revision(head.revision_id, product_id=product_id)
            commit = await self.governed_store.load_receipt(head.commit_receipt_id, product_id=product_id)
        except Exception:
            raise CompositionPolicyAdmissionError("durable policy commit chain is unavailable") from None
        if envelope is None or commit is None or envelope.payload_contract != COMPOSITION_POLICY_REVISION_VERSION:
            raise CompositionPolicyAdmissionError("current policy commit chain is incomplete or unsupported")
        try:
            revision = CompositionPolicyRevisionV1Alpha1.model_validate_json(to_json(envelope.payload))
        except Exception:
            raise CompositionPolicyAdmissionError("current policy revision failed exact revalidation") from None
        expected = _envelope(revision)
        fields = (
            "state_kind",
            "product_id",
            "state_id",
            "sequence",
            "revision_id",
            "material_hash",
            "prior_revision_id",
            "approval_subject_ref",
            "payload_contract",
        )
        if (
            any(getattr(expected, field) != getattr(envelope, field) for field in fields)
            or head.product_id != product_id
            or head.state_id != policy_id
            or head.revision_id != revision.revision_id
            or head.commit_receipt_id != commit.receipt_id
            or commit.revision_id != revision.revision_id
            or commit.material_hash != str(revision.revision_digest).removeprefix("sha256:")
        ):
            raise CompositionPolicyAdmissionError("current policy head is cross-wired or tampered")
        receipt = CompositionPolicyAdmissionReceiptV1Alpha1(
            product_id=revision.product_id,
            policy_id=revision.policy_id,
            scope_ref=revision.scope_ref,
            action=revision.action,
            revision=composition_policy_reference(revision),
            current_policy_head=GovernedStateHeadPreconditionV1Alpha1.from_head(head),
            core_commit_receipt_id=str(commit.receipt_id),
            core_commit_receipt_digest=f"sha256:{commit.receipt_hash}",
            review=revision.review,
            admitted_at=revision.admitted_at,
        )
        return CommittedCompositionPolicy(
            revision=revision, commit_receipt=commit, head=head, admission_receipt=receipt
        )

    async def _record_review_transaction(
        self,
        *,
        plan: CompositionPolicyAdmissionPlanV1Alpha1,
        request: CompositionPolicyAdmissionRequestV1Alpha1,
        review: CompositionPolicyReviewV1Alpha1,
        rejection: CompositionPolicyRejectionV1Alpha1 | None,
        submitted_at: datetime,
    ) -> None:
        values: list[tuple[str, BaseModel]] = [
            ("admission_plan", plan),
            ("admission_request", request),
            ("review", review),
        ]
        if rejection is not None:
            values.append(("rejection", rejection))
        records = tuple(
            ImmutableRecordV1(
                product_id=plan.product_id,
                record_space=COMPOSITION_POLICY_RECORD_SPACE,
                record_kind=kind,
                record_key=f"{request.request_nonce}:{kind}",
                payload_contract=str(value.contract),
                payload=value.model_dump(mode="python"),
                as_of=submitted_at,
                available_at=submitted_at,
                processing_order=index,
            )
            for index, (kind, value) in enumerate(values)
        )
        preconditions = list(request.current_core_heads)
        if request.expected_current_head is not None:
            preconditions.append(request.expected_current_head)
        append = AppendOnlyTransactionRequestV1(
            product_id=plan.product_id,
            record_space=COMPOSITION_POLICY_RECORD_SPACE,
            transaction_key=f"composition_policy_request:{request.request_nonce}",
            records=records,
            submitted_at=submitted_at,
            governed_state_preconditions=tuple(preconditions),
        )
        try:
            receipt = await self.audit_store.append(append)
        except Exception:
            raise CompositionPolicyAdmissionError("policy review audit append failed closed") from None
        if receipt != append.receipt():
            raise CompositionPolicyAdmissionError("policy review audit owner returned divergent receipt material")

    async def reject(
        self,
        *,
        plan: CompositionPolicyAdmissionPlanV1Alpha1,
        request: CompositionPolicyAdmissionRequestV1Alpha1,
        review: CompositionPolicyReviewV1Alpha1,
        rejected_at: datetime,
    ) -> CompositionPolicyRejectionV1Alpha1:
        plan = _exact(CompositionPolicyAdmissionPlanV1Alpha1, plan, name="policy plan")
        request = _exact(CompositionPolicyAdmissionRequestV1Alpha1, request, name="policy request")
        review = _exact(CompositionPolicyReviewV1Alpha1, review, name="policy review")
        self._validate_common(plan, request, review, evaluated_at=rejected_at)
        if review.disposition is not CompositionPolicyReviewDisposition.REJECT:
            raise CompositionPolicyAdmissionError("rejection requires an exact reject disposition")
        await self._validate_ac6_lineage(plan, evaluated_at=rejected_at)
        await self._require_heads(request.current_core_heads)
        current = await self._load_current(product_id=plan.product_id, policy_id=plan.policy_id)
        if plan.expected_current_head is None:
            if current is not None:
                raise CompositionPolicyAdmissionError("rejected first admission encountered a concurrent policy head")
        elif current is None or not _head_matches(current.head, plan.expected_current_head):
            raise CompositionPolicyAdmissionError("rejection expected-current-head precondition is stale")
        rejection = CompositionPolicyRejectionV1Alpha1(
            product_id=plan.product_id,
            policy_id=plan.policy_id,
            scope_ref=plan.scope_ref,
            plan=composition_policy_reference(plan),
            request=composition_policy_reference(request),
            review=composition_policy_reference(review),
            reasons=review.reasons,
            rejected_at=rejected_at,
        )
        await self._record_review_transaction(
            plan=plan, request=request, review=review, rejection=rejection, submitted_at=rejected_at
        )
        return rejection

    async def admit(
        self,
        *,
        plan: CompositionPolicyAdmissionPlanV1Alpha1,
        request: CompositionPolicyAdmissionRequestV1Alpha1,
        review: CompositionPolicyReviewV1Alpha1,
        admitted_at: datetime,
    ) -> CommittedCompositionPolicy:
        plan = _exact(CompositionPolicyAdmissionPlanV1Alpha1, plan, name="policy plan")
        request = _exact(CompositionPolicyAdmissionRequestV1Alpha1, request, name="policy request")
        review = _exact(CompositionPolicyReviewV1Alpha1, review, name="policy review")
        self._validate_common(plan, request, review, evaluated_at=admitted_at)
        if review.disposition is not CompositionPolicyReviewDisposition.APPROVE:
            raise CompositionPolicyAdmissionError("admission requires an exact approve disposition")
        proposal = await self._validate_ac6_lineage(plan, evaluated_at=admitted_at)
        await self._require_heads(request.current_core_heads)
        current = await self._load_current(product_id=plan.product_id, policy_id=plan.policy_id)
        if plan.expected_current_head is None:
            if current is not None:
                if current.revision.request == composition_policy_reference(request):
                    return current
                raise CompositionPolicyAdmissionError("first admission lost the expected-empty-head CAS")
            sequence = 1
            prior_revision_id = None
        else:
            if current is None or not _head_matches(current.head, plan.expected_current_head):
                raise CompositionPolicyAdmissionError("stale expected policy head or concurrent adoption")
            if current.revision.request == composition_policy_reference(request):
                return current
            sequence = current.revision.sequence + 1
            prior_revision_id = str(current.revision.revision_id)

        if plan.action is CompositionPolicyAction.SUPERSEDE:
            if current is None or proposal is None or current.revision.proposal == plan.proposal:
                raise CompositionPolicyAdmissionError("supersession requires a new immutable AC6 proposal transaction")
        if plan.action is CompositionPolicyAction.SUSPEND:
            if current is None or current.revision.lifecycle is not CompositionPolicyLifecycle.ACTIVE:
                raise CompositionPolicyAdmissionError("only a current active policy may be suspended")
        if plan.action is CompositionPolicyAction.RECOVER:
            if current is None or current.revision.lifecycle is not CompositionPolicyLifecycle.SUSPENDED:
                raise CompositionPolicyAdmissionError("operator recovery requires a current suspended policy")

        rollback = None
        if plan.action is CompositionPolicyAction.ROLLBACK:
            if current is None or plan.rollback_target_revision is None:
                raise CompositionPolicyAdmissionError("rollback lacks current and exact historical target")
            try:
                target_envelope = await self.governed_store.load_revision(
                    plan.rollback_target_revision.artifact_id, product_id=plan.product_id
                )
            except Exception:
                raise CompositionPolicyAdmissionError("rollback target owner is unavailable") from None
            if target_envelope is None or target_envelope.payload_contract != COMPOSITION_POLICY_REVISION_VERSION:
                raise CompositionPolicyAdmissionError("rollback target is missing or foreign")
            try:
                rollback = CompositionPolicyRevisionV1Alpha1.model_validate_json(to_json(target_envelope.payload))
            except Exception:
                raise CompositionPolicyAdmissionError("rollback target failed exact immutable revalidation") from None
            if (
                composition_policy_reference(rollback) != plan.rollback_target_revision
                or rollback.product_id != plan.product_id
                or rollback.policy_id != plan.policy_id
                or rollback.scope_ref != plan.scope_ref
                or rollback.sequence >= current.revision.sequence
                or rollback.lifecycle is not CompositionPolicyLifecycle.ACTIVE
                or proposal is None
                or proposal.proposed_policy_rule_ref != rollback.policy_rule_ref
                or plan.selection_constraints != rollback.selection_constraints
                or plan.selection_preferences != rollback.selection_preferences
            ):
                raise CompositionPolicyAdmissionError("rollback target is not an exact prior active revision")

        if plan.action in {CompositionPolicyAction.SUSPEND, CompositionPolicyAction.RECOVER}:
            assert current is not None
            policy_rule_ref = current.revision.policy_rule_ref
            constraints = current.revision.selection_constraints
            preferences = current.revision.selection_preferences
            proposal_ref = current.revision.proposal
            protocol_ref = current.revision.protocol
            comparison_ref = current.revision.comparison
        elif rollback is not None:
            policy_rule_ref = rollback.policy_rule_ref
            constraints = rollback.selection_constraints
            preferences = rollback.selection_preferences
            proposal_ref = plan.proposal
            protocol_ref = plan.protocol
            comparison_ref = plan.comparison
        else:
            policy_rule_ref = plan.proposed_policy_rule_ref
            constraints = plan.selection_constraints
            preferences = plan.selection_preferences
            proposal_ref = plan.proposal
            protocol_ref = plan.protocol
            comparison_ref = plan.comparison

        lifecycle = (
            CompositionPolicyLifecycle.SUSPENDED
            if plan.action is CompositionPolicyAction.SUSPEND
            else CompositionPolicyLifecycle.ACTIVE
        )
        revision = CompositionPolicyRevisionV1Alpha1(
            product_id=plan.product_id,
            policy_id=plan.policy_id,
            scope_ref=plan.scope_ref,
            sequence=sequence,
            prior_revision_id=prior_revision_id,
            action=plan.action,
            lifecycle=lifecycle,
            proposal=proposal_ref,
            protocol=protocol_ref,
            comparison=comparison_ref,
            rollback_target_revision=plan.rollback_target_revision,
            policy_rule_ref=policy_rule_ref,
            selection_constraints=constraints,
            selection_preferences=preferences,
            plan=composition_policy_reference(plan),
            request=composition_policy_reference(request),
            review=composition_policy_reference(review),
            authority_and_configuration_heads=request.current_core_heads,
            administrator_actor_ref=request.administrator_actor_ref,
            administrator_principal_ref=request.administrator_principal_ref,
            admitted_at=admitted_at,
        )

        try:
            approval = await self.authority.resolve_approval(
                receipt_ref=request.approval_receipt_ref,
                product_id=plan.product_id,
                subject_ref=str(plan.plan_id),
                actor_ref=request.administrator_actor_ref,
                effective_at=admitted_at,
            )
            grant = await self.authority.resolve_grant(
                grant_ref=request.administration_grant_ref,
                product_id=plan.product_id,
                authority=ADMINISTER_COMPOSITION_POLICY_AUTHORITY,
                effective_at=admitted_at,
            )
        except Exception:
            raise CompositionPolicyAdmissionError(
                "present-tense policy approval or authority resolution failed"
            ) from None
        if (
            approval.receipt_ref != request.approval_receipt_ref
            or approval.product_id != plan.product_id
            or approval.subject_ref != plan.plan_id
            or approval.actor_ref != request.administrator_actor_ref
            or approval.approved_at < plan.created_at
            or approval.approved_at > admitted_at
            or grant.grant_ref != request.administration_grant_ref
            or grant.product_id != plan.product_id
            or grant.authority != ADMINISTER_COMPOSITION_POLICY_AUTHORITY
            or grant.effective_at != admitted_at
            or (grant.expires_at is not None and grant.expires_at <= admitted_at)
        ):
            raise CompositionPolicyAdmissionError("approval or administration authority crossed exact scope/time")

        await self._record_review_transaction(
            plan=plan, request=request, review=review, rejection=None, submitted_at=admitted_at
        )
        commit_request = GovernedStateCommitRequestV1(
            revision=_envelope(revision),
            expected_head_revision_id=prior_revision_id,
            actor_ref=request.administrator_actor_ref,
            approval=approval,
            authority_grants=(grant,),
            committed_at=admitted_at,
        )
        try:
            commit = await self.governed_store.commit(commit_request)
        except Exception:
            raise CompositionPolicyAdmissionError("policy head compare-and-swap commit failed closed") from None
        if commit != commit_request.receipt():
            raise CompositionPolicyAdmissionError("policy durable owner returned divergent commit receipt")
        committed = await self._load_current(product_id=plan.product_id, policy_id=plan.policy_id)
        if committed is None or committed.revision != revision or committed.commit_receipt != commit:
            raise CompositionPolicyAdmissionError("policy commit did not reopen through the exact durable head")
        return committed

    async def reopen(self, *, product_id: str, policy_id: str) -> CommittedCompositionPolicy | None:
        """Reopen exact durable state without treating history as live authority."""

        return await self._load_current(product_id=product_id, policy_id=policy_id)

    async def resolve_runtime(
        self,
        *,
        product_id: str,
        policy_id: str,
        scope_ref: str,
        actor_ref: str,
        principal_ref: str,
        use_subject_ref: str,
        use_subject_digest: str,
        current_authority_and_configuration_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
        request_nonce: str,
        resolved_at: datetime,
        expires_at: datetime,
    ) -> CompositionPolicyRuntimeResolutionReceiptV1Alpha1:
        if resolved_at.tzinfo is None or expires_at.tzinfo is None:
            raise CompositionPolicyAdmissionError("runtime policy resolution requires timezone-aware bounds")
        await self._require_heads(current_authority_and_configuration_heads)
        current = await self._load_current(product_id=product_id, policy_id=policy_id)
        if current is None:
            raise CompositionPolicyAdmissionError("no current composition policy head")
        revision = current.revision
        if revision.scope_ref != scope_ref or revision.lifecycle is not CompositionPolicyLifecycle.ACTIVE:
            raise CompositionPolicyAdmissionError("composition policy is suspended or crossed exact scope")
        if any(item.product_id != product_id for item in current_authority_and_configuration_heads):
            raise CompositionPolicyAdmissionError("runtime authority/configuration heads crossed product scope")
        return CompositionPolicyRuntimeResolutionReceiptV1Alpha1(
            product_id=product_id,
            policy_id=policy_id,
            scope_ref=scope_ref,
            actor_ref=actor_ref,
            principal_ref=principal_ref,
            use_subject_ref=use_subject_ref,
            use_subject_digest=use_subject_digest,
            current_policy_head=GovernedStateHeadPreconditionV1Alpha1.from_head(current.head),
            policy_revision=composition_policy_reference(revision),
            current_authority_and_configuration_heads=current_authority_and_configuration_heads,
            selection_constraints=revision.selection_constraints,
            selection_preferences=revision.selection_preferences,
            request_nonce=request_nonce,
            resolved_at=resolved_at,
            expires_at=expires_at,
        )


__all__ = [
    "ADMINISTER_COMPOSITION_POLICY_AUTHORITY",
    "COMPOSITION_POLICY_RECORD_SPACE",
    "COMPOSITION_POLICY_STATE_KIND",
    "CommittedCompositionPolicy",
    "CompositionPolicyAdmissionError",
    "CompositionPolicyAdmissionService",
]
