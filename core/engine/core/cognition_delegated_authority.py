"""Host adapter for delegated headless governed-cognition review and activation.

This edge is deliberately internal.  It reads the existing Core governed-state
plane through the existing ``GovernedStateRuntimeUseResolver``, resolves a
registered ``PrincipalKind.SERVICE`` principal and two pre-existing grants,
appends inert runtime-use evidence to the existing immutable-record store, and
commits activation through the existing cognition store with every governed
head participating in the same durable transaction.

It creates no grant, exposes no issue/mint/widen/renew/transfer path, adds no
public MCP tool, and never delegates lifecycle, source, reasoning, delivery, or
any external effect.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from ace.core.agent_composition import (
    AGENT_PRINCIPAL_VERSION,
    AgentPrincipalV1Alpha1,
    AuthorityClass,
    ExactArtifactReferenceV1Alpha1,
    PrincipalLifecycle,
)
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from core.engine.cognition.delegated_activation import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    DELEGATED_RECORD_SPACE,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
    DelegatedCognitionActivationReceiptV1Alpha1,
    DelegatedCognitionActivationRequestV1Alpha1,
    DelegatedCognitionApprovalReceiptV1Alpha1,
    DelegatedCognitionAuthorityError,
    DelegatedDenyCode,
    DelegatedGrantEvidenceV1Alpha1,
    delegated_activation_event_id,
    derive_delegated_cognition_material,
    require_delegated_lineage,
    require_distinct_producer,
    require_service_principal,
)
from core.engine.cognition.governance_persistence import (
    _DELEGATED_ACTIVATION_REPLAY_QUERY,
    _DELEGATED_APPROVAL_REPLAY_QUERY,
    CognitionDelegatedPreconditionError,
    CognitionGovernanceStore,
    CognitionPersistenceError,
    CognitionReplayConflict,
)
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
)
from core.engine.core.immutable_records import SurrealImmutableRecordStore

# Core reads the governed principal-lifecycle head by its stable state kind and
# payload-contract string. It deliberately does not import the Intelligence
# bounded context that authors that payload; this private mirror is the same
# pattern `CompositionAuthorityGrantMaterial` already uses for grants.
AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND = "agent_principal_lifecycle"
AGENT_PRINCIPAL_LIFECYCLE_PAYLOAD_CONTRACT = "ace.intelligence.agent-principal-lifecycle-revision/v1alpha1"

# A delegated cognition grant may never carry, or be able to reach, an external
# or delivery consequence. The bounded ceiling is the whole point of the
# `internal_cognition_selection_no_external_effect` class.
PERMITTED_DELEGATION_CEILING = frozenset(
    {
        AuthorityClass.OBSERVE_READ,
        AuthorityClass.DERIVE_PROPOSE,
        AuthorityClass.DECIDE_APPROVE,
        AuthorityClass.MUTATE_INTERNAL,
    }
)


def _deny(code: DelegatedDenyCode, detail: str = "") -> DelegatedCognitionAuthorityError:
    return DelegatedCognitionAuthorityError(code, detail)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class DelegatedPrincipalLifecycleMaterial(FrozenContract):
    """Core-local exact mirror of the durable principal-lifecycle payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    contract: Literal["ace.intelligence.agent-principal-lifecycle-revision/v1alpha1"] = (
        AGENT_PRINCIPAL_LIFECYCLE_PAYLOAD_CONTRACT
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    registration_implementation_ref: str
    registration_protocol_refs: tuple[str, ...] = Field(min_length=1)
    state: Literal["suspended", "active", "revoked", "retired"]
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    approval_receipt_ref: str
    actor_ref: str
    occurred_at: datetime
    lifecycle_revision_id: str
    lifecycle_revision_digest: str

    @field_validator("registration_protocol_refs")
    @classmethod
    def normalize_protocols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))


def _same_grant_position(
    current: DelegatedGrantEvidenceV1Alpha1,
    approved: DelegatedGrantEvidenceV1Alpha1,
) -> bool:
    """Compare everything except the per-evaluation authority-use receipt identity."""

    fields = (
        "grant_ref",
        "grant_hash",
        "authority_class",
        "operation",
        "scope_ref",
        "policy_ref",
        "delegator_ref",
        "commit_receipt_id",
        "head_sequence",
        "head_revision_id",
        "expires_at",
    )
    return all(getattr(current, field) == getattr(approved, field) for field in fields)


class ResolvedDelegatedAuthority:
    """One point-of-use resolution of principal, both grants, and capability."""

    __slots__ = (
        "capability_head",
        "capability_use",
        "context",
        "grant_expiries",
        "activation_evidence",
        "activation_use",
        "principal_head",
        "review_evidence",
        "review_use",
    )

    def __init__(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        principal_head: GovernedStateHeadPreconditionV1Alpha1,
        review_evidence: DelegatedGrantEvidenceV1Alpha1,
        activation_evidence: DelegatedGrantEvidenceV1Alpha1,
        review_use: AuthorityUseReceiptV1Alpha1,
        activation_use: AuthorityUseReceiptV1Alpha1,
        capability_use: CapabilityUseReceiptV1Alpha1,
        capability_head: GovernedStateHeadPreconditionV1Alpha1,
        grant_expiries: tuple[datetime | None, ...],
    ) -> None:
        self.context = context
        self.principal_head = principal_head
        self.review_evidence = review_evidence
        self.activation_evidence = activation_evidence
        self.review_use = review_use
        self.activation_use = activation_use
        self.capability_use = capability_use
        self.capability_head = capability_head
        self.grant_expiries = grant_expiries

    @property
    def preconditions(self) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        """Every governed head that must still be current at commit time."""

        return (
            self.principal_head,
            self.review_use.state_head_precondition,
            self.activation_use.state_head_precondition,
            self.capability_head,
        )


def parse_delegated_inputs(
    request_payload: dict[str, Any],
    principal_payload: dict[str, Any],
) -> tuple[DelegatedCognitionActivationRequestV1Alpha1, AgentPrincipalV1Alpha1]:
    """Validate one wire envelope and registration snapshot at the host edge.

    Both nested contracts are strict and forbid extras. Wire adapters must
    decode JSON types without applying Python-side coercion.
    """

    request = DelegatedCognitionActivationRequestV1Alpha1.model_validate_json(
        json.dumps(request_payload, allow_nan=False, separators=(",", ":")),
        strict=True,
    )
    principal = AgentPrincipalV1Alpha1.model_validate_json(
        json.dumps(principal_payload, allow_nan=False, separators=(",", ":")),
        strict=True,
    )
    return request, principal


class DelegatedCognitionAuthority:
    """Resolve the delegated holder, both grants, and the capability at point of use."""

    def __init__(self, *, runtime_use: GovernedStateRuntimeUseResolver) -> None:
        self.runtime_use = runtime_use

    @staticmethod
    def _context(request: DelegatedCognitionActivationRequestV1Alpha1) -> AuthenticatedRuntimeContextV1Alpha1:
        return AuthenticatedRuntimeContextV1Alpha1(
            product_id=request.product_id,
            actor_ref=request.authenticated_actor_ref,
            authentication_receipt_ref=request.authentication_receipt_ref,
            authentication_receipt_digest=request.authentication_receipt_digest,
            authenticated_at=request.authenticated_at,
            expires_at=request.authentication_expires_at,
        )

    async def _resolve_principal(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        principal: AgentPrincipalV1Alpha1,
    ) -> GovernedStateHeadPreconditionV1Alpha1:
        binding = request.service_principal
        try:
            material = await self.runtime_use._load(
                state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
                product_id=request.product_id,
                state_id=binding.lifecycle_state_id,
            )
        except GovernedCompositionAuthorityError as exc:
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, str(exc)) from exc
        if material.revision.payload_contract != AGENT_PRINCIPAL_LIFECYCLE_PAYLOAD_CONTRACT:
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "principal lifecycle uses an unsupported payload")
        try:
            # Durable stores return JSON-shaped values; the semantic lifecycle,
            # registration, and product checks below still fail closed.
            lifecycle = DelegatedPrincipalLifecycleMaterial.model_validate(material.revision.payload)
        except ValueError as exc:
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "lifecycle payload failed validation") from exc
        lifecycle_material_hash = canonical_hash(
            lifecycle.model_dump(
                mode="json",
                exclude={"lifecycle_revision_id", "lifecycle_revision_digest"},
            )
        )
        if (
            lifecycle.lifecycle_revision_digest != f"sha256:{lifecycle_material_hash}"
            or lifecycle_material_hash != material.revision.material_hash
        ):
            raise _deny(
                DelegatedDenyCode.PRINCIPAL_UNAVAILABLE,
                "principal lifecycle payload no longer matches its admitted material hash",
            )
        if (
            lifecycle.governance.product_id != request.product_id
            or str(lifecycle.governance.governance_id) != binding.lifecycle_state_id
            or lifecycle.lifecycle_revision_id != material.revision.revision_id
        ):
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "lifecycle head crossed product or coordinate")
        if lifecycle.state != "active":
            raise _deny(DelegatedDenyCode.PRINCIPAL_INACTIVE, lifecycle.state)
        snapshot = lifecycle.registration_snapshot
        if (
            snapshot.artifact_id != binding.principal_ref
            or snapshot.artifact_digest != binding.principal_digest
            or snapshot.artifact_contract != AGENT_PRINCIPAL_VERSION
        ):
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "registration snapshot is superseded")
        try:
            exact = AgentPrincipalV1Alpha1.model_validate(principal.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "registration failed exact validation") from exc
        require_service_principal(exact, product_id=request.product_id, binding=binding)
        if (
            exact.principal_key != lifecycle.governance.principal_key
            or exact.implementation_ref != lifecycle.registration_implementation_ref
            or tuple(sorted(exact.supported_protocol_versions)) != lifecycle.registration_protocol_refs
            or exact.lifecycle is not PrincipalLifecycle.ACTIVE
        ):
            raise _deny(DelegatedDenyCode.PRINCIPAL_UNAVAILABLE, "registration does not match its lifecycle head")
        return material.head

    async def _resolve_grant(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        authority_class: AuthorityClass,
        operation: str,
        evaluated_at: datetime,
    ) -> tuple[DelegatedGrantEvidenceV1Alpha1, AuthorityUseReceiptV1Alpha1, datetime | None]:
        grant_ref = request.grant_ref_for(operation)
        try:
            grant, material = await self.runtime_use.load_grant(
                context=context,
                participant_principal_ref=request.service_principal.principal_ref,
                authority_class=authority_class,
                operation=operation,
                grant_ref=grant_ref,
                scope_ref=request.scope_ref,
                policy_ref=request.policy_ref,
                evaluated_at=evaluated_at,
            )
        except GovernedCompositionAuthorityError as exc:
            detail = str(exc)
            code = (
                DelegatedDenyCode.GRANT_UNAVAILABLE
                if "missing" in detail or "incomplete" in detail
                else DelegatedDenyCode.GRANT_MISMATCH
            )
            raise _deny(code, detail) from exc
        if tuple(grant.operations) != (operation,):
            raise _deny(DelegatedDenyCode.GRANT_MISMATCH, "grant must carry exactly one delegated operation")
        if not set(grant.delegation_ceiling).issubset(PERMITTED_DELEGATION_CEILING):
            raise _deny(DelegatedDenyCode.CONSEQUENCE_FORBIDDEN, "delegation ceiling reaches an external consequence")
        delegator_ref = require_delegated_lineage(
            delegator_ref=grant.delegator_ref,
            beneficiary_principal_ref=request.service_principal.principal_ref,
            beneficiary_actor_ref=context.actor_ref,
            commit_actor_ref=material.receipt.actor_ref,
            approval_actor_ref=material.receipt.approval.actor_ref,
            authority_class=authority_class,
            delegation_ceiling=tuple(grant.delegation_ceiling),
        )

        # `resolve_authority_use` alone cannot see participant, scope, or policy;
        # `load_grant` alone produces no receipt. Both are required, and both must
        # observe the exact same governed head, revision, and commit receipt.
        try:
            authority_use = await self.runtime_use.resolve_authority_use(
                context=context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=operation,
                authority=authority_class.value,
                grant_ref=grant_ref,
                evaluated_at=evaluated_at,
            )
        except GovernedCompositionAuthorityError as exc:
            raise _deny(DelegatedDenyCode.GRANT_MISMATCH, str(exc)) from exc
        if (
            authority_use.state_head_precondition != material.head
            or authority_use.grant_ref != grant_ref
            or authority_use.grant_hash != grant.grant_hash
            or authority_use.authority != authority_class.value
            or authority_use.operation != operation
            or authority_use.product_id != request.product_id
            or authority_use.actor_ref != context.actor_ref
            or authority_use.expires_at != grant.expires_at
        ):
            raise _deny(DelegatedDenyCode.GRANT_MISMATCH, "grant load and authority use disagree")
        evidence = DelegatedGrantEvidenceV1Alpha1(
            grant_ref=grant_ref,
            grant_hash=grant.grant_hash,
            authority_class=authority_class,
            operation=operation,
            scope_ref=grant.scope_ref,
            policy_ref=grant.policy_ref,
            delegator_ref=delegator_ref,
            commit_receipt_id=material.head.commit_receipt_id,
            head_sequence=material.head.sequence,
            head_revision_id=material.head.revision_id,
            authority_use_receipt_ref=str(authority_use.receipt_id),
            authority_use_receipt_digest=str(authority_use.receipt_digest),
            expires_at=grant.expires_at,
        )
        return evidence, authority_use, grant.expires_at

    async def resolve(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        principal: AgentPrincipalV1Alpha1,
        operation: str,
        evaluated_at: datetime,
    ) -> ResolvedDelegatedAuthority:
        """Resolve the full delegated bundle at one exact point in time."""

        evaluated_at = _aware(evaluated_at, "evaluated_at")
        context = self._context(request)
        if not (context.authenticated_at <= evaluated_at < context.expires_at):
            raise _deny(DelegatedDenyCode.HUMAN_REVIEW_REQUIRED, "authentication window is closed")
        principal_head = await self._resolve_principal(request, principal=principal)
        review_evidence, review_use, review_expiry = await self._resolve_grant(
            request,
            context=context,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operation=REVIEW_OPERATION,
            evaluated_at=evaluated_at,
        )
        activation_evidence, activation_use, activation_expiry = await self._resolve_grant(
            request,
            context=context,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operation=ACTIVATION_OPERATION,
            evaluated_at=evaluated_at,
        )
        try:
            capability_use = await self.runtime_use.resolve_capability_use(
                context=context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=operation,
                artifact=request.capability_artifact,
                capability_state_ref=request.capability_state_ref,
                configuration_ref=request.configuration_ref,
                evaluated_at=evaluated_at,
            )
        except GovernedCompositionAuthorityError as exc:
            raise _deny(DelegatedDenyCode.CAPABILITY_UNAVAILABLE, str(exc)) from exc
        try:
            capability_material = await self.runtime_use._load(
                state_kind="capability_state",
                product_id=request.product_id,
                state_id=request.capability_state_ref,
            )
        except GovernedCompositionAuthorityError as exc:
            raise _deny(DelegatedDenyCode.CAPABILITY_UNAVAILABLE, str(exc)) from exc
        capability_digest = f"sha256:{capability_material.revision.material_hash}"
        if (
            capability_material.head != capability_use.state_head_precondition
            or capability_material.revision.revision_id != request.capability_head_ref
            or capability_digest != request.capability_state_digest
            or capability_digest != request.capability_head_digest
        ):
            raise _deny(
                DelegatedDenyCode.CAPABILITY_UNAVAILABLE,
                "current capability position does not match the delegated scope",
            )
        return ResolvedDelegatedAuthority(
            context=context,
            principal_head=principal_head,
            review_evidence=review_evidence,
            activation_evidence=activation_evidence,
            review_use=review_use,
            activation_use=activation_use,
            capability_use=capability_use,
            capability_head=capability_use.state_head_precondition,
            grant_expiries=(review_expiry, activation_expiry),
        )


class DelegatedCognitionActivationService:
    """Two-stage delegated governed-cognition review then activation."""

    def __init__(
        self,
        *,
        store: CognitionGovernanceStore,
        authority: DelegatedCognitionAuthority,
        records: ImmutableRecordStore,
    ) -> None:
        governed_state = getattr(getattr(authority, "runtime_use", None), "governed_state", None)
        governed_pool = getattr(governed_state, "pool", None)
        if (
            not isinstance(records, SurrealImmutableRecordStore)
            or records.pool is not store.pool
            or governed_pool is not store.pool
        ):
            raise ValueError("delegated cognition requires one shared Surreal transaction store")
        self.store = store
        self.authority = authority
        self.records = records

    def _prepare_evidence(
        self,
        *,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        resolved: ResolvedDelegatedAuthority,
        stage: str,
        evaluated_at: datetime,
    ) -> AppendOnlyTransactionRequestV1:
        """Prepare inert runtime-use evidence for the cognition transaction."""

        values = (
            ("capability_use", resolved.capability_use),
            ("authority_use", resolved.review_use),
            ("authority_use", resolved.activation_use),
        )
        records = tuple(
            ImmutableRecordV1(
                product_id=request.product_id,
                record_space=DELEGATED_RECORD_SPACE,
                record_kind=f"{stage}_{kind}",
                record_key=str(value.receipt_id),
                payload_contract=str(value.contract),
                payload=value.model_dump(mode="python"),
                as_of=evaluated_at,
                available_at=evaluated_at,
                processing_order=index,
            )
            for index, (kind, value) in enumerate(values)
        )
        return AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=DELEGATED_RECORD_SPACE,
            transaction_key=f"delegated_cognition:{stage}:{request.request_id}",
            records=records,
            submitted_at=evaluated_at,
            governed_state_preconditions=resolved.preconditions,
        )

    async def _require_pending_proposal(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
    ) -> Any:
        proposal = await self.store.load_proposal(request.proposal_id, product_id=request.product_id)
        if proposal is None:
            raise _deny(DelegatedDenyCode.PROPOSAL_MISMATCH, "proposal is unavailable in product scope")
        if (
            str(proposal.proposal_hash) != request.proposal_hash
            or str(proposal.target_identity.cognition_id) != request.target_cognition_id
            or proposal.base_revision_id != request.base_revision_id
            or proposal.scope.product_id != request.product_id
        ):
            raise _deny(DelegatedDenyCode.PROPOSAL_MISMATCH, "proposal does not match the exact request envelope")
        if len(proposal.sources) != 1:
            raise _deny(DelegatedDenyCode.PROPOSAL_MISMATCH, "proposal must name exactly one governed capture")
        source = proposal.sources[0]
        if (
            source.source_kind != "capture"
            or str(source.source_id) != request.capture_ref
            or f"sha256:{source.content_hash}" != request.capture_digest
        ):
            raise _deny(
                DelegatedDenyCode.PROPOSAL_MISMATCH,
                "proposal provenance does not match the exact governed capture",
            )
        state = await self.store.load_proposal_state(request.proposal_id, product_id=request.product_id)
        if state is None or state.value != "pending":
            raise _deny(DelegatedDenyCode.PROPOSAL_MISMATCH, f"proposal is not pending: {state}")
        return proposal

    async def _require_head_generation(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        head_id: str,
    ) -> None:
        head = await self.store.load_head(head_id)
        actual = 0 if head is None else head.generation
        if actual != request.expected_head_generation:
            raise _deny(
                DelegatedDenyCode.HEAD_PRECONDITION_FAILED,
                f"expected={request.expected_head_generation}:actual={actual}",
            )
        if head is not None and head.scope.product_id != request.product_id:
            raise _deny(DelegatedDenyCode.HEAD_PRECONDITION_FAILED, "current head crossed product scope")

    def _derive(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        proposal: Any,
        *,
        reviewed_at: datetime,
    ) -> tuple[Any, Any, Any]:
        review_receipt, revision, head = derive_delegated_cognition_material(
            proposal,
            service_principal_ref=request.service_principal.principal_ref,
            expected_head_generation=request.expected_head_generation,
            replay_key=request.replay_key,
            reviewed_at=reviewed_at,
        )
        if (
            str(revision.revision_id) != request.derived_revision_id
            or f"sha256:{revision.material_hash}" != request.derived_material_digest
        ):
            raise _deny(DelegatedDenyCode.REQUEST_MISMATCH, "derived revision does not match the request envelope")
        return review_receipt, revision, head

    async def review(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        principal: AgentPrincipalV1Alpha1,
        evaluated_at: datetime,
    ) -> DelegatedCognitionApprovalReceiptV1Alpha1:
        """Stage one: resolve authority and persist approval-only evidence.

        No cognition revision, head, or activation event is written here.
        """

        evaluated_at = _aware(evaluated_at, "evaluated_at")
        if request.model_participant is not None:
            raise _deny(
                DelegatedDenyCode.PARTICIPANT_FORGED,
                "model participation requires durable canonical run evidence",
            )
        existing = await self.store._load_delegated_by_replay(
            _DELEGATED_APPROVAL_REPLAY_QUERY,
            DelegatedCognitionApprovalReceiptV1Alpha1,
            product_id=request.product_id,
            replay_key=request.replay_key,
        )
        if existing is not None:
            if existing.request_digest == request.request_digest and existing.request_ref == request.request_id:
                try:
                    await self.store.validate_delegated_approval_history(existing)
                except CognitionReplayConflict as exc:
                    raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, str(exc)) from exc
                return existing
            raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, "replay key already binds a different request")

        proposal = await self._require_pending_proposal(request)
        require_distinct_producer(
            producer_actor_id=str(proposal.created_by.actor_id),
            service_principal_ref=request.service_principal.principal_ref,
            authenticated_actor_ref=request.authenticated_actor_ref,
            model_participant=request.model_participant,
        )
        _, revision, head = self._derive(request, proposal, reviewed_at=evaluated_at)
        await self._require_head_generation(request, head_id=str(head.head_id))
        resolved = await self.authority.resolve(
            request,
            principal=principal,
            operation=REVIEW_OPERATION,
            evaluated_at=evaluated_at,
        )
        receipt = DelegatedCognitionApprovalReceiptV1Alpha1(
            product_id=request.product_id,
            request_ref=str(request.request_id),
            request_digest=str(request.request_digest),
            authenticated_actor_ref=request.authenticated_actor_ref,
            authentication_receipt_ref=request.authentication_receipt_ref,
            service_principal=request.service_principal,
            principal_lifecycle_head_sequence=resolved.principal_head.sequence,
            principal_lifecycle_head_revision_id=resolved.principal_head.revision_id,
            review_grant=resolved.review_evidence,
            activation_grant=resolved.activation_evidence,
            capability_state_ref=request.capability_state_ref,
            capability_use_receipt_ref=str(resolved.capability_use.receipt_id),
            capability_use_receipt_digest=str(resolved.capability_use.receipt_digest),
            capability_head_sequence=resolved.capability_head.sequence,
            capability_head_revision_id=resolved.capability_head.revision_id,
            proposal_id=request.proposal_id,
            proposal_hash=request.proposal_hash,
            derived_revision_id=str(revision.revision_id),
            derived_material_digest=f"sha256:{revision.material_hash}",
            expected_head_generation=request.expected_head_generation,
            replay_key=request.replay_key,
            resolved_at=evaluated_at,
        )
        evidence = self._prepare_evidence(
            request=request,
            resolved=resolved,
            stage="approval",
            evaluated_at=evaluated_at,
        )
        try:
            return await self.store.persist_delegated_approval(
                receipt=receipt,
                evidence=evidence,
                preconditions=resolved.preconditions,
                grant_expiries=resolved.grant_expiries,
            )
        except CognitionDelegatedPreconditionError as exc:
            raise _deny(DelegatedDenyCode.HEAD_PRECONDITION_FAILED, str(exc)) from exc
        except CognitionReplayConflict as exc:
            raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, str(exc)) from exc

    async def activate(
        self,
        request: DelegatedCognitionActivationRequestV1Alpha1,
        *,
        principal: AgentPrincipalV1Alpha1,
        evaluated_at: datetime,
    ) -> tuple[DelegatedCognitionActivationReceiptV1Alpha1, bool]:
        """Stage two: re-resolve everything, then commit atomically.

        Returns the receipt and whether it was an exact historical replay. A
        replay re-reads durable history and claims no current authority.
        """

        evaluated_at = _aware(evaluated_at, "evaluated_at")
        if request.model_participant is not None:
            raise _deny(
                DelegatedDenyCode.PARTICIPANT_FORGED,
                "model participation requires durable canonical run evidence",
            )
        replayed = await self.store._load_delegated_by_replay(
            _DELEGATED_ACTIVATION_REPLAY_QUERY,
            DelegatedCognitionActivationReceiptV1Alpha1,
            product_id=request.product_id,
            replay_key=request.replay_key,
        )
        if replayed is not None:
            if replayed.request_digest == request.request_digest and replayed.request_ref == request.request_id:
                try:
                    await self.store.validate_delegated_activation_history(replayed)
                except CognitionReplayConflict as exc:
                    raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, str(exc)) from exc
                return replayed, True
            raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, "replay key already binds a different activation")

        approval = await self.store._load_delegated_by_replay(
            _DELEGATED_APPROVAL_REPLAY_QUERY,
            DelegatedCognitionApprovalReceiptV1Alpha1,
            product_id=request.product_id,
            replay_key=request.replay_key,
        )
        if approval is None:
            raise _deny(DelegatedDenyCode.APPROVAL_UNAVAILABLE, "no stage-one approval for this replay key")
        if (
            approval.request_digest != request.request_digest
            or approval.request_ref != request.request_id
            or approval.proposal_id != request.proposal_id
            or approval.proposal_hash != request.proposal_hash
            or approval.derived_revision_id != request.derived_revision_id
            or approval.expected_head_generation != request.expected_head_generation
            or approval.authentication_receipt_ref != request.authentication_receipt_ref
        ):
            raise _deny(DelegatedDenyCode.APPROVAL_UNAVAILABLE, "stored approval does not bind this exact request")

        proposal = await self._require_pending_proposal(request)
        require_distinct_producer(
            producer_actor_id=str(proposal.created_by.actor_id),
            service_principal_ref=request.service_principal.principal_ref,
            authenticated_actor_ref=request.authenticated_actor_ref,
            model_participant=request.model_participant,
        )
        review_receipt, revision, head = self._derive(request, proposal, reviewed_at=evaluated_at)
        await self._require_head_generation(request, head_id=str(head.head_id))

        resolved = await self.authority.resolve(
            request,
            principal=principal,
            operation=ACTIVATION_OPERATION,
            evaluated_at=evaluated_at,
        )
        # Revocation, rotation, or re-issue between the two stages moves the
        # governed head, so the approval's recorded coordinates stop matching.
        if (
            resolved.principal_head.sequence != approval.principal_lifecycle_head_sequence
            or resolved.principal_head.revision_id != approval.principal_lifecycle_head_revision_id
            or not _same_grant_position(resolved.review_evidence, approval.review_grant)
            or not _same_grant_position(resolved.activation_evidence, approval.activation_grant)
            or resolved.capability_head.sequence != approval.capability_head_sequence
            or resolved.capability_head.revision_id != approval.capability_head_revision_id
        ):
            raise _deny(
                DelegatedDenyCode.HEAD_PRECONDITION_FAILED,
                "current authority no longer matches the stage-one approval",
            )

        activation_receipt = DelegatedCognitionActivationReceiptV1Alpha1(
            product_id=request.product_id,
            request_ref=str(request.request_id),
            request_digest=str(request.request_digest),
            approval_receipt_ref=str(approval.receipt_id),
            approval_receipt_digest=str(approval.receipt_digest),
            authenticated_actor_ref=request.authenticated_actor_ref,
            authentication_receipt_ref=request.authentication_receipt_ref,
            service_principal=request.service_principal,
            principal_lifecycle_head_sequence=resolved.principal_head.sequence,
            principal_lifecycle_head_revision_id=resolved.principal_head.revision_id,
            review_grant=resolved.review_evidence,
            activation_grant=resolved.activation_evidence,
            capability_state_ref=request.capability_state_ref,
            capability_use_receipt_ref=str(resolved.capability_use.receipt_id),
            capability_use_receipt_digest=str(resolved.capability_use.receipt_digest),
            capability_head_sequence=resolved.capability_head.sequence,
            capability_head_revision_id=resolved.capability_head.revision_id,
            capture_ref=request.capture_ref,
            capture_digest=request.capture_digest,
            proposal_id=request.proposal_id,
            proposal_hash=request.proposal_hash,
            base_revision_id=request.base_revision_id,
            result_revision_id=str(revision.revision_id),
            result_material_digest=f"sha256:{revision.material_hash}",
            cognition_review_receipt_id=str(review_receipt.receipt_id),
            result_head_id=str(head.head_id),
            prior_head_generation=request.expected_head_generation,
            result_head_generation=head.generation,
            activation_event_id=delegated_activation_event_id(
                head_id=str(head.head_id),
                generation=head.generation,
                review_receipt_id=str(review_receipt.receipt_id),
            ),
            replay_key=request.replay_key,
            activated_at=evaluated_at,
        )
        evidence = self._prepare_evidence(
            request=request,
            resolved=resolved,
            stage="activation",
            evaluated_at=evaluated_at,
        )
        try:
            stored = await self.store.persist_delegated_activation(
                proposal=proposal,
                review_receipt=review_receipt,
                revision=revision,
                head=head,
                activation_receipt=activation_receipt,
                evidence=evidence,
                preconditions=resolved.preconditions,
                grant_expiries=resolved.grant_expiries,
            )
        except CognitionDelegatedPreconditionError as exc:
            raise _deny(DelegatedDenyCode.HEAD_PRECONDITION_FAILED, str(exc)) from exc
        except CognitionReplayConflict as exc:
            raise _deny(DelegatedDenyCode.REPLAY_CONFLICT, str(exc)) from exc
        except CognitionPersistenceError as exc:
            raise _deny(DelegatedDenyCode.HEAD_PRECONDITION_FAILED, str(exc)) from exc
        return stored, False


__all__ = [
    "AGENT_PRINCIPAL_LIFECYCLE_PAYLOAD_CONTRACT",
    "AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND",
    "PERMITTED_DELEGATION_CEILING",
    "DelegatedPrincipalLifecycleMaterial",
    "DelegatedCognitionActivationService",
    "DelegatedCognitionAuthority",
    "ResolvedDelegatedAuthority",
    "parse_delegated_inputs",
]
