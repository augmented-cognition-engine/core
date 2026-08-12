"""Application service for bounded agent onboarding and lifecycle governance.

The service composes Intelligence-owned immutable semantics with Core's
existing governed-state, approval/grant resolution, and append-only audit
ports.  It neither executes agents nor treats installation, discovery,
conformance, requested grants, health, or historical receipts as authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeAlias

from pydantic import BaseModel

from ace.core.agent_composition import AgentPrincipalV1Alpha1, ExactArtifactReferenceV1Alpha1
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import canonical_hash, stable_id
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
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
from ace.intelligence.contracts.agent_composition import validate_role_binding_narrows_definition
from ace.intelligence.contracts.agent_governance import (
    AGENT_BINDING_LIFECYCLE_REVISION_VERSION,
    AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION,
    AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION,
    AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION,
    AGENT_RUNTIME_HEALTH_REVISION_VERSION,
    AgentActivationReceiptV1Alpha1,
    AgentBindingLifecycleRevisionV1Alpha1,
    AgentBindingProposalV1Alpha1,
    AgentCompatibilityReceiptV1Alpha1,
    AgentCompatibilityReplacementReceiptV1Alpha1,
    AgentConformanceReceiptV1Alpha1,
    AgentDefinitionLifecycleRevisionV1Alpha1,
    AgentDefinitionProposalV1Alpha1,
    AgentDryRunReceiptV1Alpha1,
    AgentGovernanceDiffV1Alpha1,
    AgentGrantRequestLifecycleRevisionV1Alpha1,
    AgentPrincipalLifecycleRevisionV1Alpha1,
    AgentReviewDispositionV1Alpha1,
    AgentRuntimeHealthRevisionV1Alpha1,
    EvidenceDisposition,
    GovernedContentState,
    GrantRequestState,
    PrincipalLifecycleState,
    ProposalKind,
    ReviewActorClass,
    ReviewDisposition,
    RuntimeHealthState,
    build_governance_diff,
    exact_registration_reference,
    project_approved_binding,
    project_approved_definition,
)

AGENT_GOVERNANCE_RECORD_SPACE = "agent_governance"
AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND = "agent_principal_lifecycle"
AGENT_DEFINITION_LIFECYCLE_STATE_KIND = "agent_definition_lifecycle"
AGENT_BINDING_LIFECYCLE_STATE_KIND = "agent_binding_lifecycle"
AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND = "agent_grant_request_lifecycle"
AGENT_RUNTIME_HEALTH_STATE_KIND = "agent_runtime_health"
ADMINISTER_LIFECYCLE_AUTHORITY = "administer_lifecycle"


LifecyclePayload: TypeAlias = (
    AgentPrincipalLifecycleRevisionV1Alpha1
    | AgentDefinitionLifecycleRevisionV1Alpha1
    | AgentBindingLifecycleRevisionV1Alpha1
    | AgentGrantRequestLifecycleRevisionV1Alpha1
    | AgentRuntimeHealthRevisionV1Alpha1
)


_STATE_MODELS: dict[str, tuple[type[BaseModel], str, str]] = {
    AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND: (
        AgentPrincipalLifecycleRevisionV1Alpha1,
        AGENT_PRINCIPAL_LIFECYCLE_REVISION_VERSION,
        "lifecycle_revision_id",
    ),
    AGENT_DEFINITION_LIFECYCLE_STATE_KIND: (
        AgentDefinitionLifecycleRevisionV1Alpha1,
        AGENT_DEFINITION_LIFECYCLE_REVISION_VERSION,
        "lifecycle_revision_id",
    ),
    AGENT_BINDING_LIFECYCLE_STATE_KIND: (
        AgentBindingLifecycleRevisionV1Alpha1,
        AGENT_BINDING_LIFECYCLE_REVISION_VERSION,
        "lifecycle_revision_id",
    ),
    AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND: (
        AgentGrantRequestLifecycleRevisionV1Alpha1,
        AGENT_GRANT_REQUEST_LIFECYCLE_REVISION_VERSION,
        "lifecycle_revision_id",
    ),
    AGENT_RUNTIME_HEALTH_STATE_KIND: (
        AgentRuntimeHealthRevisionV1Alpha1,
        AGENT_RUNTIME_HEALTH_REVISION_VERSION,
        "health_revision_id",
    ),
}


class AgentGovernanceError(RuntimeError):
    """Agent governance failed closed before any runtime execution."""


@dataclass(frozen=True, slots=True)
class RequiredCoreGrant:
    grant_ref: str
    authority: str


@dataclass(frozen=True, slots=True)
class CommittedAgentGovernanceRevision:
    payload: LifecyclePayload
    commit_receipt: GovernedStateCommitReceiptV1

    @property
    def live_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class AgentGovernanceView:
    governance: AgentGovernanceCoordinateV1Alpha1
    principal_lifecycle: AgentPrincipalLifecycleRevisionV1Alpha1 | None
    definition_lifecycle: AgentDefinitionLifecycleRevisionV1Alpha1 | None
    binding_lifecycles: tuple[AgentBindingLifecycleRevisionV1Alpha1, ...]
    grant_requests: AgentGrantRequestLifecycleRevisionV1Alpha1 | None
    runtime_health: AgentRuntimeHealthRevisionV1Alpha1 | None


@dataclass(frozen=True, slots=True)
class RecordedProposal:
    proposal: AgentDefinitionProposalV1Alpha1 | AgentBindingProposalV1Alpha1
    diff: AgentGovernanceDiffV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1


def _binding_state_id(governance_id: str, binding_key: str) -> str:
    return f"agent_binding_lifecycle:{canonical_hash([governance_id, binding_key])[:32]}"


def agent_governance_head_id(
    *,
    state_kind: str,
    governance: AgentGovernanceCoordinateV1Alpha1,
    binding_key: str | None = None,
) -> str:
    """Return the stable Core head identity referenced by approved AC4 content."""

    if state_kind == AGENT_BINDING_LIFECYCLE_STATE_KIND:
        if binding_key is None:
            raise ValueError("binding lifecycle head identity requires binding_key")
        state_id = _binding_state_id(str(governance.governance_id), binding_key)
    else:
        if binding_key is not None:
            raise ValueError("binding_key applies only to binding lifecycle heads")
        state_id = str(governance.governance_id)
    return stable_id(
        "governed_state_head",
        {
            "state_kind": state_kind,
            "product_id": governance.product_id,
            "state_id": state_id,
        },
    )


def _state_id(payload: LifecyclePayload) -> str:
    governance_id = str(payload.governance.governance_id)
    if isinstance(payload, AgentBindingLifecycleRevisionV1Alpha1):
        return _binding_state_id(governance_id, payload.binding_key)
    return governance_id


def _state_kind(payload: LifecyclePayload) -> str:
    if isinstance(payload, AgentPrincipalLifecycleRevisionV1Alpha1):
        return AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND
    if isinstance(payload, AgentDefinitionLifecycleRevisionV1Alpha1):
        return AGENT_DEFINITION_LIFECYCLE_STATE_KIND
    if isinstance(payload, AgentBindingLifecycleRevisionV1Alpha1):
        return AGENT_BINDING_LIFECYCLE_STATE_KIND
    if isinstance(payload, AgentGrantRequestLifecycleRevisionV1Alpha1):
        return AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND
    return AGENT_RUNTIME_HEALTH_STATE_KIND


def _payload_revision_id(payload: LifecyclePayload) -> str:
    if isinstance(payload, AgentRuntimeHealthRevisionV1Alpha1):
        return str(payload.health_revision_id)
    return str(payload.lifecycle_revision_id)


def _payload_digest(payload: LifecyclePayload) -> str:
    if isinstance(payload, AgentRuntimeHealthRevisionV1Alpha1):
        return str(payload.health_revision_digest)
    return str(payload.lifecycle_revision_digest)


def _approval_ref(payload: LifecyclePayload) -> str:
    return payload.approval_receipt_ref


def _actor_ref(payload: LifecyclePayload) -> str:
    return payload.actor_ref


def _occurred_at(payload: LifecyclePayload) -> datetime:
    if isinstance(payload, AgentRuntimeHealthRevisionV1Alpha1):
        return payload.observed_at
    return payload.occurred_at


def _envelope(payload: LifecyclePayload, *, approval_subject_ref: str) -> GovernedStateRevisionV1:
    return GovernedStateRevisionV1(
        state_kind=_state_kind(payload),
        product_id=payload.governance.product_id,
        state_id=_state_id(payload),
        sequence=payload.sequence,
        revision_id=_payload_revision_id(payload),
        material_hash=_payload_digest(payload).removeprefix("sha256:"),
        prior_revision_id=payload.prior_revision_id,
        approval_subject_ref=approval_subject_ref,
        payload_contract=payload.contract,
        payload=payload.model_dump(mode="python"),
    )


def _validate_commit_pair(
    payload: LifecyclePayload,
    receipt: GovernedStateCommitReceiptV1,
    *,
    approval_subject_ref: str,
) -> CommittedAgentGovernanceRevision:
    envelope = _envelope(payload, approval_subject_ref=approval_subject_ref)
    fields = (
        "state_kind",
        "product_id",
        "state_id",
        "sequence",
        "revision_id",
        "material_hash",
        "prior_revision_id",
    )
    if any(getattr(envelope, field) != getattr(receipt, field) for field in fields):
        raise AgentGovernanceError("Core commit receipt does not bind the exact agent-governance revision")
    approval = receipt.approval
    if (
        receipt.actor_ref != payload.actor_ref
        or approval.receipt_ref != payload.approval_receipt_ref
        or approval.product_id != payload.governance.product_id
        or approval.subject_ref != approval_subject_ref
        or approval.actor_ref != payload.actor_ref
        or approval.approved_at > _occurred_at(payload)
        or receipt.committed_at < _occurred_at(payload)
    ):
        raise AgentGovernanceError("Core commit receipt does not close over exact approval and actor material")
    requires_admin = isinstance(payload, AgentPrincipalLifecycleRevisionV1Alpha1) or (
        isinstance(payload, (AgentDefinitionLifecycleRevisionV1Alpha1, AgentBindingLifecycleRevisionV1Alpha1))
        and payload.state is not GovernedContentState.APPROVED
    )
    if requires_admin:
        if len(receipt.authority_grants) != 1:
            raise AgentGovernanceError("Core commit receipt lacks exact lifecycle authority")
        grant = receipt.authority_grants[0]
        if (
            grant.product_id != payload.governance.product_id
            or grant.authority != ADMINISTER_LIFECYCLE_AUTHORITY
            or grant.effective_at != _occurred_at(payload)
            or (grant.expires_at is not None and grant.expires_at <= _occurred_at(payload))
        ):
            raise AgentGovernanceError("Core commit receipt lacks exact lifecycle authority")
    elif receipt.authority_grants:
        raise AgentGovernanceError("Core commit receipt carries unexpected authority")
    return CommittedAgentGovernanceRevision(payload=payload, commit_receipt=receipt)


def _transition_allowed(previous: Any, current: Any) -> bool:
    if isinstance(current, PrincipalLifecycleState):
        allowed = {
            PrincipalLifecycleState.SUSPENDED: {
                PrincipalLifecycleState.SUSPENDED,
                PrincipalLifecycleState.ACTIVE,
                PrincipalLifecycleState.REVOKED,
                PrincipalLifecycleState.RETIRED,
            },
            PrincipalLifecycleState.ACTIVE: {
                PrincipalLifecycleState.SUSPENDED,
                PrincipalLifecycleState.REVOKED,
                PrincipalLifecycleState.RETIRED,
            },
            PrincipalLifecycleState.REVOKED: {PrincipalLifecycleState.RETIRED},
            PrincipalLifecycleState.RETIRED: set(),
        }
        return current in allowed[previous]
    if isinstance(current, GovernedContentState):
        if previous is GovernedContentState.RETIRED:
            return False
        allowed = {
            GovernedContentState.APPROVED: {
                GovernedContentState.ACTIVE,
                GovernedContentState.REVOKED,
                GovernedContentState.RETIRED,
            },
            GovernedContentState.ACTIVE: {
                GovernedContentState.SUSPENDED,
                GovernedContentState.REVOKED,
                GovernedContentState.SUPERSEDED,
                GovernedContentState.RETIRED,
            },
            GovernedContentState.SUSPENDED: {
                GovernedContentState.ACTIVE,
                GovernedContentState.REVOKED,
                GovernedContentState.SUPERSEDED,
                GovernedContentState.RETIRED,
            },
            GovernedContentState.REVOKED: {GovernedContentState.RETIRED},
            GovernedContentState.SUPERSEDED: {GovernedContentState.RETIRED},
            GovernedContentState.RETIRED: set(),
        }
        return current in allowed[previous]
    return True


class AgentGovernanceService:
    """Coordinate exact heads, Core authority, inert evidence, and audit."""

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

    async def _load_exact_record(
        self,
        *,
        product_id: str,
        kind: str,
        key: str,
        model: type[BaseModel],
    ) -> BaseModel:
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=kind,
            record_key=key,
        )
        record = await self.audit_store.load_record(
            storage_id,
            product_id=product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=kind,
        )
        if record is None:
            raise AgentGovernanceError(f"required immutable {kind} record is unavailable")
        try:
            value = model.model_validate(record.payload)
        except Exception:
            raise AgentGovernanceError(f"immutable {kind} record failed exact revalidation") from None
        if value.model_dump(mode="python") != record.payload or value.contract != record.payload_contract:
            raise AgentGovernanceError(f"immutable {kind} record does not bind exact contract material")
        return value

    async def _require_recorded_lineage(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        disposition_ref: str,
        proposal_kind: ProposalKind,
        result_id: str,
        result_digest: str,
        lifecycle_ref: str,
        prior_content_ref: str | None,
        expected_result: BaseModel,
        actor_ref: str,
        expected_head_revision_id: str | None,
        admitted_at: datetime,
    ) -> None:
        disposition = await self._load_exact_record(
            product_id=governance.product_id,
            kind="review_disposition",
            key=disposition_ref,
            model=AgentReviewDispositionV1Alpha1,
        )
        if not isinstance(disposition, AgentReviewDispositionV1Alpha1):
            raise AgentGovernanceError("review disposition has an invalid type")
        proposal_model = (
            AgentDefinitionProposalV1Alpha1
            if proposal_kind is ProposalKind.DEFINITION
            else AgentBindingProposalV1Alpha1
        )
        proposal_record_kind = "definition_proposal" if proposal_kind is ProposalKind.DEFINITION else "binding_proposal"
        proposal = await self._load_exact_record(
            product_id=governance.product_id,
            kind=proposal_record_kind,
            key=disposition.proposal_id,
            model=proposal_model,
        )
        if (
            disposition.receipt_id != disposition_ref
            or disposition.proposal_kind is not proposal_kind
            or disposition.disposition is not ReviewDisposition.APPROVE
            or disposition.actor_class not in {ReviewActorClass.HUMAN, ReviewActorClass.CORE_POLICY}
            or disposition.actor_ref != actor_ref
            or disposition.proposal_id != proposal.proposal_id
            or disposition.proposal_digest != proposal.proposal_digest
            or disposition.result_revision_id != result_id
            or disposition.result_revision_digest != result_digest
            or disposition.expected_head_revision_id != expected_head_revision_id
            or disposition.reviewed_at > admitted_at
            or proposal.governance != governance
        ):
            raise AgentGovernanceError("approved content lacks exact proposal and disposition lineage")
        proposal_tx = await self.audit_store.load_transaction_receipt(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            transaction_key=str(proposal.proposal_id),
        )
        review_tx = await self.audit_store.load_transaction_receipt(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            transaction_key=disposition_ref,
        )
        if (
            proposal_tx is None
            or {item.record_kind for item in proposal_tx.records} != {proposal_record_kind, "semantic_diff"}
            or review_tx is None
            or len(review_tx.records) != 1
            or review_tx.records[0].record_kind != "review_disposition"
        ):
            raise AgentGovernanceError("approved content lacks durable proposal, diff, and review records")
        proposal_storage_id = immutable_record_storage_id(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=proposal_record_kind,
            record_key=str(proposal.proposal_id),
        )
        review_storage_id = immutable_record_storage_id(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind="review_disposition",
            record_key=disposition_ref,
        )
        if (
            proposal_tx.records[0].storage_id != proposal_storage_id
            or review_tx.records[0].storage_id != review_storage_id
        ):
            raise AgentGovernanceError("approved content transaction receipts crossed exact immutable records")
        diff_ref = next(item for item in proposal_tx.records if item.record_kind == "semantic_diff")
        diff_record = await self.audit_store.load_record(
            diff_ref.storage_id,
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind="semantic_diff",
        )
        try:
            diff = AgentGovernanceDiffV1Alpha1.model_validate(diff_record.payload if diff_record else {})
        except Exception:
            raise AgentGovernanceError("approved content semantic diff failed exact reload") from None
        if (
            diff.proposal_kind is not proposal_kind
            or diff.proposal_id != proposal.proposal_id
            or diff.proposal_digest != proposal.proposal_digest
            or diff_record.reference() != diff_ref
        ):
            raise AgentGovernanceError("approved content semantic diff crossed proposal lineage")
        if proposal_kind is ProposalKind.DEFINITION:
            projected = project_approved_definition(
                proposal,
                disposition,
                lifecycle_ref=lifecycle_ref,
                prior_revision_ref=prior_content_ref,
            )
        else:
            projected = project_approved_binding(
                proposal,
                disposition,
                lifecycle_ref=lifecycle_ref,
                prior_binding_ref=prior_content_ref,
            )
        if projected != expected_result:
            raise AgentGovernanceError("approved content differs from the exact reviewed projection")

    async def _load_current(
        self,
        *,
        state_kind: str,
        governance: AgentGovernanceCoordinateV1Alpha1,
        state_id: str | None = None,
    ) -> tuple[GovernedStateHeadV1, LifecyclePayload, GovernedStateCommitReceiptV1] | None:
        head = await self.governed_store.load_head(
            state_kind=state_kind,
            product_id=governance.product_id,
            state_id=state_id or str(governance.governance_id),
        )
        if head is None:
            return None
        envelope = await self.governed_store.load_revision(head.revision_id, product_id=governance.product_id)
        receipt = await self.governed_store.load_receipt(
            head.commit_receipt_id,
            product_id=governance.product_id,
        )
        if envelope is None or receipt is None:
            raise AgentGovernanceError("agent-governance head has an incomplete commit chain")
        model, contract, _ = _STATE_MODELS[state_kind]
        if envelope.payload_contract != contract:
            raise AgentGovernanceError("agent-governance head uses an unsupported payload contract")
        try:
            payload = model.model_validate(envelope.payload)
        except Exception:
            raise AgentGovernanceError("agent-governance payload failed exact revalidation") from None
        if payload.governance != governance or _state_id(payload) != head.state_id:
            raise AgentGovernanceError("agent-governance head crossed its exact coordinate")
        subject = envelope.approval_subject_ref
        expected = _envelope(payload, approval_subject_ref=subject)
        comparable = (
            "contract",
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
        if any(getattr(expected, field) != getattr(envelope, field) for field in comparable):
            raise AgentGovernanceError("persisted envelope does not match exact governance material")
        if (
            head.sequence != payload.sequence
            or head.revision_id != _payload_revision_id(payload)
            or head.commit_receipt_id != receipt.receipt_id
        ):
            raise AgentGovernanceError("agent-governance head does not bind its exact commit chain")
        _validate_commit_pair(payload, receipt, approval_subject_ref=subject)
        return head, payload, receipt

    async def _admit(
        self,
        payload: LifecyclePayload,
        *,
        approval_subject_ref: str,
        required_grants: tuple[RequiredCoreGrant, ...],
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        model = _STATE_MODELS[_state_kind(payload)][0]
        try:
            payload = model.model_validate(payload.model_dump(mode="python"))
        except Exception:
            raise AgentGovernanceError("governance revision failed exact boundary revalidation") from None
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise AgentGovernanceError("commit time must include a timezone")
        if _occurred_at(payload) > committed_at:
            raise AgentGovernanceError("governance commit cannot predate its exact transition")
        current = await self._load_current(
            state_kind=_state_kind(payload),
            governance=payload.governance,
            state_id=_state_id(payload),
        )
        if current is None:
            if payload.sequence != 1 or payload.prior_revision_id is not None:
                raise AgentGovernanceError("first governance revision requires an empty exact head")
        else:
            _, current_payload, _ = current
            if payload == current_payload:
                committed = _validate_commit_pair(
                    current_payload,
                    current[2],
                    approval_subject_ref=approval_subject_ref,
                )
                await self._record_lifecycle_commit(committed)
                return committed
            if payload.sequence != current_payload.sequence + 1 or payload.prior_revision_id != _payload_revision_id(
                current_payload
            ):
                raise AgentGovernanceError("agent-governance revision is stale or superseded")
            prior_state = getattr(current_payload, "state")
            if _occurred_at(payload) <= _occurred_at(current_payload):
                raise AgentGovernanceError("agent-governance transition chronology is not monotonic")
            if payload.state is not GovernedContentState.APPROVED and not _transition_allowed(
                prior_state, payload.state
            ):
                raise AgentGovernanceError("agent-governance lifecycle transition is not allowed")

        try:
            approval = await self.authority.resolve_approval(
                receipt_ref=_approval_ref(payload),
                product_id=payload.governance.product_id,
                subject_ref=approval_subject_ref,
                actor_ref=_actor_ref(payload),
                effective_at=_occurred_at(payload),
            )
        except Exception:
            raise AgentGovernanceError("approval resolution failed closed") from None
        if (
            approval.receipt_ref != _approval_ref(payload)
            or approval.product_id != payload.governance.product_id
            or approval.subject_ref != approval_subject_ref
            or approval.actor_ref != _actor_ref(payload)
            or approval.approved_at > _occurred_at(payload)
        ):
            raise AgentGovernanceError("approval did not resolve to the exact governance transition")

        grants = []
        for requirement in required_grants:
            try:
                resolved = await self.authority.resolve_grant(
                    grant_ref=requirement.grant_ref,
                    product_id=payload.governance.product_id,
                    authority=requirement.authority,
                    effective_at=_occurred_at(payload),
                )
            except Exception:
                raise AgentGovernanceError("current Core authority resolution failed closed") from None
            if (
                resolved.grant_ref != requirement.grant_ref
                or resolved.product_id != payload.governance.product_id
                or resolved.authority != requirement.authority
                or resolved.effective_at != _occurred_at(payload)
                or (resolved.expires_at is not None and resolved.expires_at <= _occurred_at(payload))
            ):
                raise AgentGovernanceError("current Core authority did not admit the exact lifecycle transition")
            grants.append(resolved)

        request = GovernedStateCommitRequestV1(
            revision=_envelope(payload, approval_subject_ref=approval_subject_ref),
            expected_head_revision_id=payload.prior_revision_id,
            actor_ref=_actor_ref(payload),
            approval=approval,
            authority_grants=tuple(grants),
            committed_at=committed_at,
        )
        expected_receipt = request.receipt()
        try:
            receipt = await self.governed_store.commit(request)
        except Exception:
            recovered = await self.governed_store.load_receipt(
                str(expected_receipt.receipt_id),
                product_id=payload.governance.product_id,
            )
            if recovered != expected_receipt:
                raise AgentGovernanceError("agent-governance commit failed closed") from None
            receipt = recovered
        committed = _validate_commit_pair(payload, receipt, approval_subject_ref=approval_subject_ref)
        await self._record_lifecycle_commit(committed)
        return committed

    async def admit_principal_lifecycle(
        self,
        revision: AgentPrincipalLifecycleRevisionV1Alpha1,
        *,
        registration: AgentPrincipalV1Alpha1,
        admin_grant_ref: str,
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        try:
            registration = AgentPrincipalV1Alpha1.model_validate(registration.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            raise AgentGovernanceError("principal lifecycle does not bind the exact registration snapshot") from None
        if (
            revision.governance.product_id != registration.product_id
            or revision.governance.principal_key != registration.principal_key
            or revision.registration_snapshot != exact_registration_reference(registration)
            or revision.registration_implementation_ref != registration.implementation_ref
            or revision.registration_protocol_refs != tuple(sorted(registration.supported_protocol_versions))
        ):
            raise AgentGovernanceError("principal lifecycle does not bind the exact registration snapshot")
        if revision.actor_ref in {revision.governance.governance_id, registration.principal_id}:
            raise AgentGovernanceError("an agent cannot approve or administer its own lifecycle")
        return await self._admit(
            revision,
            approval_subject_ref=str(revision.lifecycle_revision_id),
            required_grants=(RequiredCoreGrant(admin_grant_ref, ADMINISTER_LIFECYCLE_AUTHORITY),),
            committed_at=committed_at,
        )

    async def admit_definition_lifecycle(
        self,
        revision: AgentDefinitionLifecycleRevisionV1Alpha1,
        *,
        admin_grant_ref: str | None = None,
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        principal = await self._require_principal(revision.governance)
        if revision.registration_snapshot != principal.registration_snapshot:
            raise AgentGovernanceError("definition targets a superseded registration snapshot")
        if (
            revision.state is GovernedContentState.APPROVED
            and revision.definition.approval_receipt_ref != revision.disposition_receipt_ref
        ):
            raise AgentGovernanceError("definition content does not bind its exact review disposition")
        current = await self._load_current(
            state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            governance=revision.governance,
        )
        if current is None:
            if revision.definition.prior_revision_ref is not None:
                raise AgentGovernanceError("first definition cannot name prior content")
        else:
            current_definition = current[1]
            if not isinstance(current_definition, AgentDefinitionLifecycleRevisionV1Alpha1):
                raise AgentGovernanceError("current definition lifecycle has an invalid type")
            if revision.definition.definition_revision_id != current_definition.definition.definition_revision_id:
                if (
                    revision.state is not GovernedContentState.APPROVED
                    or revision.definition.prior_revision_ref != current_definition.definition.definition_revision_id
                ):
                    raise AgentGovernanceError("revised definition does not extend the exact current content")
        expected_lifecycle_ref = agent_governance_head_id(
            state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            governance=revision.governance,
        )
        if revision.definition.lifecycle_ref != expected_lifecycle_ref:
            raise AgentGovernanceError("definition does not reference its exact stable lifecycle head")
        if revision.actor_ref in {revision.governance.governance_id, revision.registration_snapshot.artifact_id}:
            raise AgentGovernanceError("an agent cannot approve its own definition")
        required_grants = ()
        if revision.state is GovernedContentState.APPROVED:
            if (
                current is not None
                and revision.definition.definition_revision_id == current[1].definition.definition_revision_id
            ):
                raise AgentGovernanceError("approved state requires a newly reviewed definition revision")
            await self._require_recorded_lineage(
                governance=revision.governance,
                disposition_ref=revision.disposition_receipt_ref,
                proposal_kind=ProposalKind.DEFINITION,
                result_id=str(revision.definition.definition_revision_id),
                result_digest=str(revision.definition.definition_digest),
                lifecycle_ref=revision.definition.lifecycle_ref,
                prior_content_ref=revision.definition.prior_revision_ref,
                expected_result=revision.definition,
                actor_ref=revision.actor_ref,
                expected_head_revision_id=(current[0].revision_id if current is not None else None),
                admitted_at=revision.occurred_at,
            )
        if revision.state is not GovernedContentState.APPROVED:
            if admin_grant_ref is None:
                raise AgentGovernanceError("definition lifecycle transition requires current administrative authority")
            required_grants = (RequiredCoreGrant(admin_grant_ref, ADMINISTER_LIFECYCLE_AUTHORITY),)
        return await self._admit(
            revision,
            approval_subject_ref=revision.disposition_receipt_ref,
            required_grants=required_grants,
            committed_at=committed_at,
        )

    async def admit_binding_lifecycle(
        self,
        revision: AgentBindingLifecycleRevisionV1Alpha1,
        *,
        admin_grant_ref: str | None = None,
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        principal = await self._require_principal(revision.governance)
        definition = await self._require_definition(revision.governance)
        if revision.registration_snapshot != principal.registration_snapshot:
            raise AgentGovernanceError("binding targets a superseded registration snapshot")
        try:
            validate_role_binding_narrows_definition(definition.definition, revision.binding)
        except ValueError as exc:
            raise AgentGovernanceError(str(exc)) from None
        current = await self._load_current(
            state_kind=AGENT_BINDING_LIFECYCLE_STATE_KIND,
            governance=revision.governance,
            state_id=_binding_state_id(str(revision.governance.governance_id), revision.binding_key),
        )
        if current is None:
            if revision.binding.prior_binding_ref is not None:
                raise AgentGovernanceError("first binding cannot name prior content")
        else:
            current_binding = current[1]
            if not isinstance(current_binding, AgentBindingLifecycleRevisionV1Alpha1):
                raise AgentGovernanceError("current binding lifecycle has an invalid type")
            if revision.binding.binding_revision_id != current_binding.binding.binding_revision_id:
                if (
                    revision.state is not GovernedContentState.APPROVED
                    or revision.binding.prior_binding_ref != current_binding.binding.binding_revision_id
                ):
                    raise AgentGovernanceError("revised binding does not extend the exact current content")
        expected_lifecycle_ref = agent_governance_head_id(
            state_kind=AGENT_BINDING_LIFECYCLE_STATE_KIND,
            governance=revision.governance,
            binding_key=revision.binding_key,
        )
        if revision.binding.lifecycle_ref != expected_lifecycle_ref:
            raise AgentGovernanceError("binding does not reference its exact stable lifecycle head")
        required_grants = ()
        if revision.state is GovernedContentState.APPROVED:
            if current is not None and revision.binding.binding_revision_id == current[1].binding.binding_revision_id:
                raise AgentGovernanceError("approved state requires a newly reviewed binding revision")
            await self._require_recorded_lineage(
                governance=revision.governance,
                disposition_ref=revision.disposition_receipt_ref,
                proposal_kind=ProposalKind.BINDING,
                result_id=str(revision.binding.binding_revision_id),
                result_digest=str(revision.binding.binding_digest),
                lifecycle_ref=revision.binding.lifecycle_ref,
                prior_content_ref=revision.binding.prior_binding_ref,
                expected_result=revision.binding,
                actor_ref=revision.actor_ref,
                expected_head_revision_id=(current[0].revision_id if current is not None else None),
                admitted_at=revision.occurred_at,
            )
        if revision.state is not GovernedContentState.APPROVED:
            if admin_grant_ref is None:
                raise AgentGovernanceError("binding lifecycle transition requires current administrative authority")
            required_grants = (RequiredCoreGrant(admin_grant_ref, ADMINISTER_LIFECYCLE_AUTHORITY),)
        return await self._admit(
            revision,
            approval_subject_ref=revision.disposition_receipt_ref,
            required_grants=required_grants,
            committed_at=committed_at,
        )

    async def admit_grant_requests(
        self,
        revision: AgentGrantRequestLifecycleRevisionV1Alpha1,
        *,
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        definition = await self._require_definition(revision.governance)
        if any(item.authority_class not in definition.definition.maximum_authority for item in revision.requests):
            raise AgentGovernanceError("requested grant widens the current definition authority ceiling")
        return await self._admit(
            revision,
            approval_subject_ref=str(revision.lifecycle_revision_id),
            required_grants=(),
            committed_at=committed_at,
        )

    async def admit_runtime_health(
        self,
        revision: AgentRuntimeHealthRevisionV1Alpha1,
        *,
        registration: AgentPrincipalV1Alpha1,
        committed_at: datetime,
    ) -> CommittedAgentGovernanceRevision:
        principal = await self._require_principal(revision.governance)
        if (
            principal.registration_snapshot != exact_registration_reference(registration)
            or revision.registration_snapshot != principal.registration_snapshot
            or revision.implementation_ref != registration.implementation_ref
        ):
            raise AgentGovernanceError("runtime health does not observe the current registration implementation")
        return await self._admit(
            revision,
            approval_subject_ref=str(revision.health_revision_id),
            required_grants=(),
            committed_at=committed_at,
        )

    async def _require_principal(
        self,
        governance: AgentGovernanceCoordinateV1Alpha1,
    ) -> AgentPrincipalLifecycleRevisionV1Alpha1:
        current = await self._load_current(
            state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
            governance=governance,
        )
        if current is None or not isinstance(current[1], AgentPrincipalLifecycleRevisionV1Alpha1):
            raise AgentGovernanceError("current principal lifecycle head is unavailable")
        return current[1]

    async def _require_definition(
        self,
        governance: AgentGovernanceCoordinateV1Alpha1,
    ) -> AgentDefinitionLifecycleRevisionV1Alpha1:
        current = await self._load_current(
            state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            governance=governance,
        )
        if current is None or not isinstance(current[1], AgentDefinitionLifecycleRevisionV1Alpha1):
            raise AgentGovernanceError("current definition lifecycle head is unavailable")
        return current[1]

    async def _record_models(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        transaction_key: str,
        values: tuple[tuple[str, BaseModel], ...],
        submitted_at: datetime,
        preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = (),
    ) -> AppendOnlyTransactionReceiptV1:
        validated_values = []
        for kind, value in values:
            try:
                validated = type(value).model_validate(value.model_dump(mode="python"))
            except Exception:
                raise AgentGovernanceError(f"{kind} failed exact boundary revalidation") from None
            validated_values.append((kind, validated))

        def record_key(kind: str, value: BaseModel) -> str:
            if kind in {"definition_proposal", "binding_proposal"}:
                return str(getattr(value, "proposal_id"))
            if kind == "semantic_diff":
                return str(getattr(value, "diff_id"))
            if kind == "lifecycle_revision":
                return str(getattr(value, "lifecycle_revision_id", None) or getattr(value, "health_revision_id", None))
            return str(getattr(value, "receipt_id"))

        records = tuple(
            ImmutableRecordV1(
                product_id=governance.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                record_kind=kind,
                record_key=record_key(kind, value),
                payload_contract=str(value.model_dump(mode="json")["contract"]),
                payload=value.model_dump(mode="python"),
                as_of=submitted_at,
                available_at=submitted_at,
                processing_order=index,
            )
            for index, (kind, value) in enumerate(validated_values)
        )
        request = AppendOnlyTransactionRequestV1(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            transaction_key=transaction_key,
            records=records,
            submitted_at=submitted_at,
            governed_state_preconditions=preconditions,
        )
        return await self.audit_store.append(request)

    async def _record_lifecycle_commit(self, committed: CommittedAgentGovernanceRevision) -> None:
        payload = committed.payload
        await self._record_models(
            governance=payload.governance,
            transaction_key=f"lifecycle-audit:{committed.commit_receipt.receipt_id}",
            values=(
                ("lifecycle_revision", payload),
                ("governed_state_commit_receipt", committed.commit_receipt),
            ),
            submitted_at=committed.commit_receipt.committed_at,
        )

    async def record_definition_proposal(
        self,
        proposal: AgentDefinitionProposalV1Alpha1,
        *,
        base_definition: AgentDefinitionLifecycleRevisionV1Alpha1 | None,
    ) -> RecordedProposal:
        current = await self._load_current(
            state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            governance=proposal.governance,
        )
        expected_base = None
        preconditions = ()
        if current is not None:
            head, current_payload, _ = current
            if not isinstance(current_payload, AgentDefinitionLifecycleRevisionV1Alpha1):
                raise AgentGovernanceError("current definition lifecycle has an invalid type")
            if base_definition != current_payload:
                raise AgentGovernanceError("definition proposal does not extend the exact current head")
            expected_base = ExactArtifactReferenceV1Alpha1(
                artifact_id=str(current_payload.definition.definition_revision_id),
                artifact_digest=str(current_payload.definition.definition_digest),
                artifact_contract=current_payload.definition.contract,
            )
            preconditions = (GovernedStateHeadPreconditionV1Alpha1.from_head(head),)
        elif base_definition is not None:
            raise AgentGovernanceError("initial definition proposal cannot name absent current content")
        if proposal.base_definition != expected_base:
            raise AgentGovernanceError("definition proposal base does not bind the exact current content")
        base = base_definition.definition.model_dump(mode="json") if base_definition else None
        diff = build_governance_diff(
            proposal_kind=ProposalKind.DEFINITION,
            proposal_id=str(proposal.proposal_id),
            proposal_digest=str(proposal.proposal_digest),
            draft=proposal.draft.model_dump(mode="json"),
            base=base,
            base_revision_id=(str(base_definition.definition.definition_revision_id) if base_definition else None),
            base_digest=(str(base_definition.definition.definition_digest) if base_definition else None),
        )
        receipt = await self._record_models(
            governance=proposal.governance,
            transaction_key=str(proposal.proposal_id),
            values=(("definition_proposal", proposal), ("semantic_diff", diff)),
            submitted_at=proposal.proposed_at,
            preconditions=preconditions,
        )
        return RecordedProposal(proposal=proposal, diff=diff, transaction_receipt=receipt)

    async def record_binding_proposal(
        self,
        proposal: AgentBindingProposalV1Alpha1,
        *,
        base_binding: AgentBindingLifecycleRevisionV1Alpha1 | None,
    ) -> RecordedProposal:
        current = await self._load_current(
            state_kind=AGENT_BINDING_LIFECYCLE_STATE_KIND,
            governance=proposal.governance,
            state_id=_binding_state_id(str(proposal.governance.governance_id), proposal.binding_key),
        )
        expected_base = None
        preconditions = ()
        if current is not None:
            head, current_payload, _ = current
            if not isinstance(current_payload, AgentBindingLifecycleRevisionV1Alpha1):
                raise AgentGovernanceError("current binding lifecycle has an invalid type")
            if base_binding != current_payload:
                raise AgentGovernanceError("binding proposal does not extend the exact current head")
            expected_base = ExactArtifactReferenceV1Alpha1(
                artifact_id=str(current_payload.binding.binding_revision_id),
                artifact_digest=str(current_payload.binding.binding_digest),
                artifact_contract=current_payload.binding.contract,
            )
            preconditions = (GovernedStateHeadPreconditionV1Alpha1.from_head(head),)
        elif base_binding is not None:
            raise AgentGovernanceError("initial binding proposal cannot name absent current content")
        if proposal.base_binding != expected_base:
            raise AgentGovernanceError("binding proposal base does not bind the exact current content")
        base = base_binding.binding.model_dump(mode="json") if base_binding else None
        diff = build_governance_diff(
            proposal_kind=ProposalKind.BINDING,
            proposal_id=str(proposal.proposal_id),
            proposal_digest=str(proposal.proposal_digest),
            draft=proposal.draft.model_dump(mode="json"),
            base=base,
            base_revision_id=(str(base_binding.binding.binding_revision_id) if base_binding else None),
            base_digest=(str(base_binding.binding.binding_digest) if base_binding else None),
        )
        receipt = await self._record_models(
            governance=proposal.governance,
            transaction_key=str(proposal.proposal_id),
            values=(("binding_proposal", proposal), ("semantic_diff", diff)),
            submitted_at=proposal.proposed_at,
            preconditions=preconditions,
        )
        return RecordedProposal(proposal=proposal, diff=diff, transaction_receipt=receipt)

    async def record_review(
        self,
        *,
        proposal: AgentDefinitionProposalV1Alpha1 | AgentBindingProposalV1Alpha1,
        disposition: AgentReviewDispositionV1Alpha1,
    ) -> AppendOnlyTransactionReceiptV1:
        expected_kind = (
            ProposalKind.DEFINITION if isinstance(proposal, AgentDefinitionProposalV1Alpha1) else ProposalKind.BINDING
        )
        if (
            disposition.proposal_kind is not expected_kind
            or disposition.proposal_id != proposal.proposal_id
            or disposition.proposal_digest != proposal.proposal_digest
        ):
            raise AgentGovernanceError("review does not bind the exact proposal")
        if disposition.disposition is ReviewDisposition.APPROVE and disposition.actor_ref == proposal.requested_by:
            raise AgentGovernanceError("self-approval is forbidden")
        if disposition.reviewed_at < proposal.proposed_at:
            raise AgentGovernanceError("review cannot predate its exact proposal")
        if isinstance(proposal, AgentDefinitionProposalV1Alpha1):
            current = await self._load_current(
                state_kind=AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
                governance=proposal.governance,
            )
        else:
            current = await self._load_current(
                state_kind=AGENT_BINDING_LIFECYCLE_STATE_KIND,
                governance=proposal.governance,
                state_id=_binding_state_id(str(proposal.governance.governance_id), proposal.binding_key),
            )
        current_revision_id = current[0].revision_id if current is not None else None
        if disposition.expected_head_revision_id != current_revision_id:
            raise AgentGovernanceError("review disposition is stale for the exact current head")
        if disposition.disposition is ReviewDisposition.APPROVE and disposition.result_revision_id is None:
            raise AgentGovernanceError("approval must bind the exact projected result revision")
        preconditions = (GovernedStateHeadPreconditionV1Alpha1.from_head(current[0]),) if current is not None else ()
        return await self._record_models(
            governance=proposal.governance,
            transaction_key=str(disposition.receipt_id),
            values=(("review_disposition", disposition),),
            submitted_at=disposition.reviewed_at,
            preconditions=preconditions,
        )

    async def activate(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        binding_key: str,
        compatibility: AgentCompatibilityReceiptV1Alpha1,
        conformance: AgentConformanceReceiptV1Alpha1,
        dry_run: AgentDryRunReceiptV1Alpha1,
        actor_ref: str,
        admin_grant_ref: str,
        activated_at: datetime,
    ) -> tuple[AgentActivationReceiptV1Alpha1, AppendOnlyTransactionReceiptV1]:
        if activated_at.tzinfo is None or activated_at.utcoffset() is None:
            raise AgentGovernanceError("activation time must include a timezone")
        if actor_ref == governance.governance_id:
            raise AgentGovernanceError("self-activation is forbidden")
        try:
            compatibility = AgentCompatibilityReceiptV1Alpha1.model_validate(compatibility.model_dump(mode="python"))
            conformance = AgentConformanceReceiptV1Alpha1.model_validate(conformance.model_dump(mode="python"))
            dry_run = AgentDryRunReceiptV1Alpha1.model_validate(dry_run.model_dump(mode="python"))
        except Exception:
            raise AgentGovernanceError("activation evidence failed exact boundary revalidation") from None
        loaded = []
        for state_kind, state_id in (
            (AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_DEFINITION_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_BINDING_LIFECYCLE_STATE_KIND, _binding_state_id(str(governance.governance_id), binding_key)),
            (AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_RUNTIME_HEALTH_STATE_KIND, str(governance.governance_id)),
        ):
            item = await self._load_current(state_kind=state_kind, governance=governance, state_id=state_id)
            if item is None:
                raise AgentGovernanceError(f"current {state_kind} head is unavailable")
            loaded.append(item)
        principal = loaded[0][1]
        definition = loaded[1][1]
        binding = loaded[2][1]
        requests = loaded[3][1]
        health = loaded[4][1]
        if (
            not isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
            or principal.state is not PrincipalLifecycleState.ACTIVE
        ):
            raise AgentGovernanceError("principal is suspended, revoked, or retired")
        if actor_ref == principal.registration_snapshot.artifact_id:
            raise AgentGovernanceError("self-activation is forbidden")
        if (
            not isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
            or definition.state is not GovernedContentState.ACTIVE
        ):
            raise AgentGovernanceError("definition is not active")
        if (
            not isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1)
            or binding.state is not GovernedContentState.ACTIVE
        ):
            raise AgentGovernanceError("binding is not active")
        if (
            not isinstance(requests, AgentGrantRequestLifecycleRevisionV1Alpha1)
            or requests.state is not GrantRequestState.REQUESTED
        ):
            raise AgentGovernanceError("requested-grant lifecycle is not current")
        if not isinstance(health, AgentRuntimeHealthRevisionV1Alpha1) or health.state is not RuntimeHealthState.HEALTHY:
            raise AgentGovernanceError("runtime health blocks eligibility")
        if (
            definition.registration_snapshot != principal.registration_snapshot
            or binding.registration_snapshot != principal.registration_snapshot
            or definition.definition.principal_id != principal.registration_snapshot.artifact_id
        ):
            raise AgentGovernanceError("current definition or binding targets a superseded registration snapshot")
        try:
            validate_role_binding_narrows_definition(definition.definition, binding.binding)
        except ValueError as exc:
            raise AgentGovernanceError(str(exc)) from None
        if (
            compatibility.governance != governance
            or conformance.governance != governance
            or dry_run.governance != governance
            or compatibility.registration_snapshot != principal.registration_snapshot
            or conformance.registration_snapshot != principal.registration_snapshot
            or dry_run.registration_snapshot != principal.registration_snapshot
            or compatibility.disposition is not EvidenceDisposition.PASSED
            or conformance.disposition is not EvidenceDisposition.PASSED
            or dry_run.disposition is not EvidenceDisposition.PASSED
            or compatibility.required_protocol_ref != definition.definition.implementation_protocol_ref
            or compatibility.supported_protocol_refs != principal.registration_protocol_refs
            or compatibility.required_protocol_ref not in principal.registration_protocol_refs
            or conformance.definition
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(definition.definition.definition_revision_id),
                artifact_digest=str(definition.definition.definition_digest),
                artifact_contract=definition.definition.contract,
            )
            or conformance.binding
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(binding.binding.binding_revision_id),
                artifact_digest=str(binding.binding.binding_digest),
                artifact_contract=binding.binding.contract,
            )
            or dry_run.definition
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(definition.definition.definition_revision_id),
                artifact_digest=str(definition.definition.definition_digest),
                artifact_contract=definition.definition.contract,
            )
            or dry_run.binding
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(binding.binding.binding_revision_id),
                artifact_digest=str(binding.binding.binding_digest),
                artifact_contract=binding.binding.contract,
            )
        ):
            raise AgentGovernanceError("compatibility, conformance, or dry-run evidence is not exact and passing")
        if any(item.checked_at > activated_at for item in (compatibility, conformance, dry_run)):
            raise AgentGovernanceError("activation evidence cannot postdate activation")

        try:
            lifecycle_authority = await self.authority.resolve_grant(
                grant_ref=admin_grant_ref,
                product_id=governance.product_id,
                authority=ADMINISTER_LIFECYCLE_AUTHORITY,
                effective_at=activated_at,
            )
        except Exception:
            raise AgentGovernanceError("activation lifecycle authority resolution failed closed") from None
        if (
            lifecycle_authority.grant_ref != admin_grant_ref
            or lifecycle_authority.product_id != governance.product_id
            or lifecycle_authority.authority != ADMINISTER_LIFECYCLE_AUTHORITY
            or lifecycle_authority.effective_at != activated_at
            or (lifecycle_authority.expires_at is not None and lifecycle_authority.expires_at <= activated_at)
        ):
            raise AgentGovernanceError("activation lacks exact current lifecycle authority")

        resolved_grants = []
        for request in requests.requests:
            if (
                request.authority_class not in definition.definition.maximum_authority
                or request.authority_class not in binding.binding.authority_ceiling
            ):
                raise AgentGovernanceError("current grant request widens current definition or binding authority")
            try:
                resolved = await self.authority.resolve_grant(
                    grant_ref=request.requested_grant_ref,
                    product_id=governance.product_id,
                    authority=request.authority_class.value,
                    effective_at=activated_at,
                )
            except Exception:
                raise AgentGovernanceError("current requested-grant admission failed closed") from None
            if (
                resolved.grant_ref != request.requested_grant_ref
                or resolved.product_id != governance.product_id
                or resolved.authority != request.authority_class.value
                or resolved.effective_at != activated_at
                or (resolved.expires_at is not None and resolved.expires_at <= activated_at)
            ):
                raise AgentGovernanceError("requested grant is not currently admitted by Core authority")
            resolved_grants.append(resolved)

        receipt = AgentActivationReceiptV1Alpha1(
            governance=governance,
            principal_lifecycle_revision_id=_payload_revision_id(principal),
            definition_lifecycle_revision_id=_payload_revision_id(definition),
            binding_lifecycle_revision_id=_payload_revision_id(binding),
            grant_request_lifecycle_revision_id=_payload_revision_id(requests),
            runtime_health_revision_id=_payload_revision_id(health),
            compatibility_receipt_id=str(compatibility.receipt_id),
            conformance_receipt_id=str(conformance.receipt_id),
            dry_run_receipt_id=str(dry_run.receipt_id),
            lifecycle_authority=lifecycle_authority,
            resolved_grants=tuple(resolved_grants),
            actor_ref=actor_ref,
            activated_at=activated_at,
        )
        preconditions = tuple(GovernedStateHeadPreconditionV1Alpha1.from_head(item[0]) for item in loaded)
        audit_receipt = await self._record_models(
            governance=governance,
            transaction_key=str(receipt.receipt_id),
            values=(
                ("compatibility_receipt", compatibility),
                ("conformance_receipt", conformance),
                ("dry_run_receipt", dry_run),
                ("activation_receipt", receipt),
            ),
            submitted_at=activated_at,
            preconditions=preconditions,
        )
        return receipt, audit_receipt

    async def inspect(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        binding_keys: tuple[str, ...] = (),
    ) -> AgentGovernanceView:
        async def payload(kind: str, state_id: str | None = None):
            loaded = await self._load_current(state_kind=kind, governance=governance, state_id=state_id)
            return loaded[1] if loaded else None

        principal = await payload(AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND)
        definition = await payload(AGENT_DEFINITION_LIFECYCLE_STATE_KIND)
        grants = await payload(AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND)
        health = await payload(AGENT_RUNTIME_HEALTH_STATE_KIND)
        bindings = []
        for key in sorted(set(binding_keys)):
            item = await payload(
                AGENT_BINDING_LIFECYCLE_STATE_KIND,
                _binding_state_id(str(governance.governance_id), key),
            )
            if item is not None:
                bindings.append(item)
        return AgentGovernanceView(
            governance=governance,
            principal_lifecycle=(principal if isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1) else None),
            definition_lifecycle=(
                definition if isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1) else None
            ),
            binding_lifecycles=tuple(
                item for item in bindings if isinstance(item, AgentBindingLifecycleRevisionV1Alpha1)
            ),
            grant_requests=(grants if isinstance(grants, AgentGrantRequestLifecycleRevisionV1Alpha1) else None),
            runtime_health=(health if isinstance(health, AgentRuntimeHealthRevisionV1Alpha1) else None),
        )

    async def replace_compatibility_participant(
        self,
        *,
        compatibility_participant: ExactArtifactReferenceV1Alpha1,
        governance: AgentGovernanceCoordinateV1Alpha1,
        binding_key: str,
        activation: AgentActivationReceiptV1Alpha1,
        replaced_at: datetime,
    ) -> tuple[AgentCompatibilityReplacementReceiptV1Alpha1, AppendOnlyTransactionReceiptV1]:
        """Map an opaque compatibility reference to exact eligible AC4 material."""

        if replaced_at.tzinfo is None or replaced_at.utcoffset() is None:
            raise AgentGovernanceError("replacement time must include a timezone")
        try:
            activation = AgentActivationReceiptV1Alpha1.model_validate(activation.model_dump(mode="python"))
        except Exception:
            raise AgentGovernanceError("replacement activation failed exact boundary revalidation") from None
        recorded_activation = await self._load_exact_record(
            product_id=governance.product_id,
            kind="activation_receipt",
            key=str(activation.receipt_id),
            model=AgentActivationReceiptV1Alpha1,
        )
        if recorded_activation != activation:
            raise AgentGovernanceError("compatibility replacement requires the exact durable activation receipt")
        activation_tx = await self.audit_store.load_transaction_receipt(
            product_id=governance.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            transaction_key=str(activation.receipt_id),
        )
        expected_activation_kinds = {
            "compatibility_receipt",
            "conformance_receipt",
            "dry_run_receipt",
            "activation_receipt",
        }
        if activation_tx is None or {item.record_kind for item in activation_tx.records} != expected_activation_kinds:
            raise AgentGovernanceError("compatibility replacement requires the complete activation transaction")
        if activation.activated_at > replaced_at:
            raise AgentGovernanceError("compatibility replacement cannot predate activation")
        loaded = []
        for state_kind, state_id in (
            (AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_DEFINITION_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_BINDING_LIFECYCLE_STATE_KIND, _binding_state_id(str(governance.governance_id), binding_key)),
            (AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_RUNTIME_HEALTH_STATE_KIND, str(governance.governance_id)),
        ):
            current = await self._load_current(
                state_kind=state_kind,
                governance=governance,
                state_id=state_id,
            )
            if current is None:
                raise AgentGovernanceError("compatibility replacement requires every exact current head")
            loaded.append(current)
        principal, definition, binding, grants, health = (item[1] for item in loaded)
        if (
            not isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
            or principal.state is not PrincipalLifecycleState.ACTIVE
            or not isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
            or definition.state is not GovernedContentState.ACTIVE
            or not isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1)
            or binding.state is not GovernedContentState.ACTIVE
            or not isinstance(grants, AgentGrantRequestLifecycleRevisionV1Alpha1)
            or grants.state is not GrantRequestState.REQUESTED
            or not isinstance(health, AgentRuntimeHealthRevisionV1Alpha1)
            or health.state is not RuntimeHealthState.HEALTHY
        ):
            raise AgentGovernanceError("compatibility replacement target is not currently eligible")
        if (
            activation.governance != governance
            or activation.principal_lifecycle_revision_id != _payload_revision_id(principal)
            or activation.definition_lifecycle_revision_id != _payload_revision_id(definition)
            or activation.binding_lifecycle_revision_id != _payload_revision_id(binding)
            or activation.grant_request_lifecycle_revision_id != _payload_revision_id(grants)
            or activation.runtime_health_revision_id != _payload_revision_id(health)
        ):
            raise AgentGovernanceError("compatibility replacement activation is stale or crossed scope")
        activation_ids = {
            "compatibility_receipt": activation.compatibility_receipt_id,
            "conformance_receipt": activation.conformance_receipt_id,
            "dry_run_receipt": activation.dry_run_receipt_id,
            "activation_receipt": activation.receipt_id,
        }
        for reference in activation_tx.records:
            if reference.record_key != activation_ids[reference.record_kind]:
                raise AgentGovernanceError("compatibility replacement activation transaction crossed evidence")
        current_requirements = (
            (activation.lifecycle_authority.grant_ref, ADMINISTER_LIFECYCLE_AUTHORITY),
            *((item.requested_grant_ref, item.authority_class.value) for item in grants.requests),
        )
        for grant_ref, authority in current_requirements:
            try:
                resolved = await self.authority.resolve_grant(
                    grant_ref=grant_ref,
                    product_id=governance.product_id,
                    authority=authority,
                    effective_at=replaced_at,
                )
            except Exception:
                raise AgentGovernanceError("compatibility replacement grant resolution failed closed") from None
            if (
                resolved.grant_ref != grant_ref
                or resolved.product_id != governance.product_id
                or resolved.authority != authority
                or resolved.effective_at != replaced_at
                or (resolved.expires_at is not None and resolved.expires_at <= replaced_at)
            ):
                raise AgentGovernanceError("compatibility replacement requires current exact grants")
        receipt = AgentCompatibilityReplacementReceiptV1Alpha1(
            compatibility_participant=compatibility_participant,
            governance=governance,
            registration_snapshot=principal.registration_snapshot,
            definition=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(definition.definition.definition_revision_id),
                artifact_digest=str(definition.definition.definition_digest),
                artifact_contract=definition.definition.contract,
            ),
            binding=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(binding.binding.binding_revision_id),
                artifact_digest=str(binding.binding.binding_digest),
                artifact_contract=binding.binding.contract,
            ),
            activation_receipt=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(activation.receipt_id),
                artifact_digest=str(activation.receipt_digest),
                artifact_contract=activation.contract,
            ),
            replaced_at=replaced_at,
        )
        preconditions = tuple(GovernedStateHeadPreconditionV1Alpha1.from_head(item[0]) for item in loaded)
        durable = await self._record_models(
            governance=governance,
            transaction_key=str(receipt.receipt_id),
            values=(("compatibility_replacement_receipt", receipt),),
            submitted_at=replaced_at,
            preconditions=preconditions,
        )
        return receipt, durable

    async def audit(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        available_at: datetime,
    ) -> tuple[ImmutableRecordV1, ...]:
        kinds = (
            "definition_proposal",
            "binding_proposal",
            "semantic_diff",
            "review_disposition",
            "compatibility_receipt",
            "conformance_receipt",
            "dry_run_receipt",
            "activation_receipt",
            "compatibility_replacement_receipt",
            "lifecycle_revision",
            "governed_state_commit_receipt",
        )
        records = []
        for kind in kinds:
            records.extend(
                await self.audit_store.read_as_of(
                    product_id=governance.product_id,
                    record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                    record_kind=kind,
                    available_at=available_at,
                )
            )
        governance_material = governance.model_dump(mode="python")
        direct = [item for item in records if item.payload.get("governance") == governance_material]
        proposal_ids = {
            item.payload.get("proposal_id")
            for item in direct
            if item.record_kind in {"definition_proposal", "binding_proposal"}
        }
        linked = [
            item
            for item in records
            if item.record_kind in {"semantic_diff", "review_disposition"}
            and item.payload.get("proposal_id") in proposal_ids
        ]
        lifecycle_revision_ids = {
            item.payload.get("lifecycle_revision_id") or item.payload.get("health_revision_id")
            for item in direct
            if item.record_kind == "lifecycle_revision"
        }
        linked.extend(
            item
            for item in records
            if item.record_kind == "governed_state_commit_receipt"
            and item.payload.get("revision_id") in lifecycle_revision_ids
        )
        selected = {str(item.storage_id): item for item in (*direct, *linked)}
        return tuple(
            sorted(
                selected.values(),
                key=lambda item: (item.available_at, item.processing_order, str(item.storage_id)),
            )
        )


__all__ = [
    "ADMINISTER_LIFECYCLE_AUTHORITY",
    "AGENT_BINDING_LIFECYCLE_STATE_KIND",
    "AGENT_DEFINITION_LIFECYCLE_STATE_KIND",
    "AGENT_GOVERNANCE_RECORD_SPACE",
    "AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND",
    "AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND",
    "AGENT_RUNTIME_HEALTH_STATE_KIND",
    "AgentGovernanceError",
    "AgentGovernanceService",
    "AgentGovernanceView",
    "CommittedAgentGovernanceRevision",
    "RecordedProposal",
    "RequiredCoreGrant",
    "agent_governance_head_id",
]
