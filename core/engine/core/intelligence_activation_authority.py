"""Durable single-owner approval adapter for reviewed Intelligence activation.

The public Builder flow already separates an inert plan, exact bindings, and a
governed start.  This host adapter closes the missing production approval seam:
an authenticated local owner explicitly approves the exact bound activation
specification, Core stores that receipt append-only, and the existing
``CoreAuthorityResolver`` port resolves it again at every activation use.

No grant is minted here.  Authority bindings continue to resolve from the
existing governed-state authority heads and therefore fail closed when setup is
missing, expired, revoked, or mismatched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ace.application.intelligence_build_execution import IntelligenceBuildStartV1Alpha2
from ace.application.intelligence_build_plan_binding import BoundIntelligenceBuildPlanV1Alpha1
from ace.application.intelligence_build_planning import intelligence_build_execution_identity
from ace.application.intelligence_builder import (
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionReplayConflict,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import IntelligenceBuilderSessionRevisionV1
from ace.core.contracts import canonical_hash
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateStore,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.agent_composition_runtime import (
    GRANT_PAYLOAD_CONTRACT,
    CompositionAuthorityGrantMaterial,
)
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_ACTOR_REF,
    LOCAL_OWNER_PRODUCT_ID,
)

INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE = "intelligence_activation_approval"
INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND = "reviewed_activation_approval"
INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION = "ace.host.reviewed-intelligence-activation-approval/v1alpha1"
LOCAL_OWNER_BUILD_GRANT_REF = "authority_grant:atrium-intelligence-build"
LOCAL_OWNER_READ_GRANT_REF = "authority_grant:atrium-observe-read"


class IntelligenceActivationApprovalError(RuntimeError):
    """Base failure for exact reviewed activation approval."""


class IntelligenceActivationApprovalDenied(IntelligenceActivationApprovalError):
    """The verified caller cannot approve this exact activation."""


class IntelligenceActivationApprovalConflict(IntelligenceActivationApprovalError):
    """Approval material crossed or changed exact reviewed bindings."""


class IntelligenceActivationApprovalUnavailable(IntelligenceActivationApprovalError):
    """Durable approval or authority material cannot currently be resolved."""


class IntelligenceActivationApproveRequestV1Alpha1(BaseModel):
    """One explicit owner decision over an exact already-bound plan."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve"]
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1
    approved_at: datetime

    @field_validator("approved_at")
    @classmethod
    def _approved_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must include a timezone")
        return value.astimezone(UTC)


class ReviewedIntelligenceActivationApprovalV1Alpha1(BaseModel):
    """Append-only evidence binding an owner receipt to exact plan identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.reviewed-intelligence-activation-approval/v1alpha1"] = (
        INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION
    )
    product_id: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    bound_plan_id: str = Field(min_length=1, max_length=240)
    bound_plan_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    execution_request_id: str = Field(min_length=1, max_length=240)
    execution_request_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    activation_spec_id: str = Field(min_length=1, max_length=240)
    activation_spec_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    approval: ResolvedApprovalReceiptV1

    @model_validator(mode="after")
    def _exact_receipt(self):
        if (
            self.approval.product_id != self.product_id
            or self.approval.actor_ref != self.actor_ref
            or self.approval.subject_ref != self.activation_spec_id
        ):
            raise ValueError("approval receipt crossed its exact activation scope")
        material = self.model_dump(mode="json", exclude={"approval"})
        material["approved_at"] = self.approval.approved_at.isoformat().replace("+00:00", "Z")
        expected_hash = canonical_hash(material)
        expected_ref = f"approval:intelligence-activation:{expected_hash[:32]}"
        if self.approval.receipt_hash != expected_hash or self.approval.receipt_ref != expected_ref:
            raise ValueError("approval receipt identity does not match exact reviewed material")
        return self


class IntelligenceActivationApprovalResultV1Alpha1(BaseModel):
    """Exact approval plus the existing start request it authorizes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.http.intelligence-activation-approval-result/v1alpha1"] = (
        "ace.http.intelligence-activation-approval-result/v1alpha1"
    )
    approval: ResolvedApprovalReceiptV1
    bound_plan_id: str
    bound_plan_digest: str
    start_request: IntelligenceBuildStartV1Alpha2


class IntelligenceBuildSessionAssociateRequestV1Alpha1(BaseModel):
    """Associate one exact bound plan with its recorded reviewed approval receipt."""

    model_config = ConfigDict(extra="forbid")

    bound_plan: BoundIntelligenceBuildPlanV1Alpha1
    approval_receipt_ref: str = Field(min_length=1, max_length=240)


class IntelligenceBuildSessionAssociationResultV1Alpha1(BaseModel):
    """Exact bound/approval coordinates plus the resulting Builder session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.http.intelligence-build-session-association-result/v1alpha1"] = (
        "ace.http.intelligence-build-session-association-result/v1alpha1"
    )
    bound_plan_id: str
    bound_plan_digest: str
    approval: ResolvedApprovalReceiptV1
    session: IntelligenceBuilderSessionRevisionV1
    replayed: bool


class IntelligenceBuildRetryRequestV1Alpha1(BaseModel):
    """Exact blocked Builder revision selected by its owner for one retry."""

    model_config = ConfigDict(extra="forbid")

    current: IntelligenceBuilderSessionRevisionV1
    requested_at: datetime

    @field_validator("current", mode="before")
    @classmethod
    def _json_session(cls, value):
        if isinstance(value, dict):
            return IntelligenceBuilderSessionRevisionV1.model_validate(value, strict=False)
        return value

    @field_validator("requested_at")
    @classmethod
    def _requested_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone")
        return value.astimezone(UTC)


def verified_local_intelligence_owner(user: dict) -> tuple[str, str]:
    """Return the fixed local owner's (actor_ref, product_id) or deny."""
    authorities = user.get("authorities")
    if (
        user.get("local_owner") is not True
        or user.get("sub") != LOCAL_OWNER_ACTOR_REF
        or user.get("product") != LOCAL_OWNER_PRODUCT_ID
        or not isinstance(authorities, list)
        or not {"intelligence_build", "observe_read"}.issubset(authorities)
    ):
        raise IntelligenceActivationApprovalDenied("verified caller is not the local Intelligence owner")
    return LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID


def _artifact_for(
    *,
    bound: BoundIntelligenceBuildPlanV1Alpha1,
    actor_ref: str,
    product_id: str,
    approved_at: datetime,
) -> ReviewedIntelligenceActivationApprovalV1Alpha1:
    spec = bound.activation_spec
    if (
        bound.bound_plan_id is None
        or bound.bound_plan_digest is None
        or bound.execution_request_id is None
        or bound.execution_request_digest is None
        or spec.spec_id is None
        or spec.spec_hash is None
    ):
        raise IntelligenceActivationApprovalConflict("bound activation plan is missing exact identity")
    material = {
        "contract": INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION,
        "product_id": product_id,
        "actor_ref": actor_ref,
        "bound_plan_id": bound.bound_plan_id,
        "bound_plan_digest": bound.bound_plan_digest,
        "execution_request_id": bound.execution_request_id,
        "execution_request_digest": bound.execution_request_digest,
        "activation_spec_id": spec.spec_id,
        "activation_spec_digest": f"sha256:{spec.spec_hash}",
        "approved_at": approved_at.isoformat().replace("+00:00", "Z"),
    }
    receipt_hash = canonical_hash(material)
    approval = ResolvedApprovalReceiptV1(
        receipt_ref=f"approval:intelligence-activation:{receipt_hash[:32]}",
        product_id=product_id,
        subject_ref=spec.spec_id,
        actor_ref=actor_ref,
        receipt_hash=receipt_hash,
        approved_at=approved_at,
    )
    return ReviewedIntelligenceActivationApprovalV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        bound_plan_id=bound.bound_plan_id,
        bound_plan_digest=bound.bound_plan_digest,
        execution_request_id=bound.execution_request_id,
        execution_request_digest=bound.execution_request_digest,
        activation_spec_id=spec.spec_id,
        activation_spec_digest=f"sha256:{spec.spec_hash}",
        approval=approval,
    )


def intelligence_activation_start_request(
    *,
    bound: BoundIntelligenceBuildPlanV1Alpha1,
    approval: ResolvedApprovalReceiptV1,
) -> IntelligenceBuildStartV1Alpha2:
    """Derive the exact ``/start`` request one recorded approval authorizes."""
    request = IntelligenceBuildStartV1Alpha2(
        authority_grant_ref=LOCAL_OWNER_BUILD_GRANT_REF,
        resource_authority_grant_ref=LOCAL_OWNER_READ_GRANT_REF,
        activation_approval_receipt_ref=approval.receipt_ref,
        **bound.execution_material(),
    )
    execution_id, execution_digest = intelligence_build_execution_identity(
        product_id=bound.binding_request.plan.request.product_id,
        actor_ref=bound.binding_request.plan.request.actor_ref,
        request_material=request.model_dump(
            mode="json",
            exclude={
                "authority_grant_ref",
                "resource_authority_grant_ref",
                "activation_approval_receipt_ref",
            },
        ),
    )
    if execution_id != bound.execution_request_id or execution_digest != bound.execution_request_digest:
        raise IntelligenceActivationApprovalConflict("approved start request changed the exact bound execution")
    return request


class RecordedIntelligenceActivationAuthority(CoreAuthorityResolver):
    """Resolve reviewed approvals and existing governed grants at point of use."""

    def __init__(self, *, records: ImmutableRecordStore, governed_state: GovernedStateStore) -> None:
        self.records = records
        self.governed_state = governed_state

    async def resolve_approval(
        self,
        *,
        receipt_ref: str,
        product_id: str,
        subject_ref: str,
        actor_ref: str,
        effective_at: datetime,
    ) -> ResolvedApprovalReceiptV1:
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
            record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
            record_key=receipt_ref,
        )
        try:
            record = await self.records.load_record(
                storage_id,
                product_id=product_id,
                record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
                record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
            )
            if record is None:
                raise IntelligenceActivationApprovalDenied("reviewed activation approval is not recorded")
            artifact = ReviewedIntelligenceActivationApprovalV1Alpha1.model_validate(record.payload)
        except IntelligenceActivationApprovalError:
            raise
        except Exception as exc:
            raise IntelligenceActivationApprovalUnavailable(
                "reviewed activation approval storage is unavailable"
            ) from exc
        if (
            record.payload_contract != INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION
            or record.record_key != receipt_ref
            or artifact.approval.receipt_ref != receipt_ref
            or artifact.product_id != product_id
            or artifact.activation_spec_id != subject_ref
            or artifact.actor_ref != actor_ref
            or artifact.approval.approved_at > effective_at
        ):
            raise IntelligenceActivationApprovalDenied("reviewed activation approval is stale or mismatched")
        return artifact.approval

    async def resolve_grant(
        self,
        *,
        grant_ref: str,
        product_id: str,
        authority: str,
        effective_at: datetime,
    ) -> ResolvedAuthorityGrantV1:
        try:
            head = await self.governed_state.load_head(
                state_kind=AUTHORITY_GRANT_STATE_KIND,
                product_id=product_id,
                state_id=grant_ref,
            )
            if head is None:
                raise IntelligenceActivationApprovalDenied("required activation authority grant is missing")
            revision = await self.governed_state.load_revision(head.revision_id, product_id=product_id)
            receipt = await self.governed_state.load_receipt(head.commit_receipt_id, product_id=product_id)
            if revision is None or receipt is None:
                raise IntelligenceActivationApprovalDenied("required activation authority lineage is incomplete")
            grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload, strict=False)
        except IntelligenceActivationApprovalError:
            raise
        except Exception as exc:
            raise IntelligenceActivationApprovalUnavailable("activation authority storage is unavailable") from exc
        matches = tuple(item for item in receipt.authority_grants if item.grant_ref == grant_ref)
        if (
            revision.state_kind != AUTHORITY_GRANT_STATE_KIND
            or revision.product_id != product_id
            or revision.state_id != grant_ref
            or revision.payload_contract != GRANT_PAYLOAD_CONTRACT
            or revision.revision_id != head.revision_id
            or receipt.receipt_id != head.commit_receipt_id
            or len(matches) != 1
            or grant.grant_ref != grant_ref
            or grant.product_id != product_id
            or grant.authority_class.value != authority
            or grant.lifecycle != "active"
            or grant.effective_at > effective_at
            or grant.revoked_at is not None
            or (grant.expires_at is not None and grant.expires_at <= effective_at)
            or matches[0].product_id != product_id
            or matches[0].authority != authority
            or matches[0].grant_hash != grant.grant_hash
            or matches[0].state != "active"
        ):
            raise IntelligenceActivationApprovalDenied("required activation authority is inactive or mismatched")
        return ResolvedAuthorityGrantV1(
            grant_ref=grant_ref,
            product_id=product_id,
            authority=authority,
            grant_hash=grant.grant_hash,
            effective_at=effective_at,
            expires_at=grant.expires_at,
        )


async def approve_intelligence_activation(
    *,
    request: IntelligenceActivationApproveRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> IntelligenceActivationApprovalResultV1Alpha1:
    """Record an explicit local-owner approval for one exact bound plan."""

    actor_ref, product_id = verified_local_intelligence_owner(user)
    now = datetime.now(UTC)
    bound = request.bound_plan
    plan_request = bound.binding_request.plan.request
    if request.approved_at > now + timedelta(minutes=5):
        raise IntelligenceActivationApprovalConflict("approved_at cannot be materially in the future")
    if request.approved_at < bound.binding_request.bound_at:
        raise IntelligenceActivationApprovalConflict("approval cannot predate exact plan binding")
    if plan_request.product_id != product_id or plan_request.actor_ref != actor_ref:
        raise IntelligenceActivationApprovalDenied("bound plan crossed verified local-owner scope")
    artifact = _artifact_for(
        bound=bound,
        actor_ref=actor_ref,
        product_id=product_id,
        approved_at=request.approved_at,
    )
    approval = artifact.approval
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
        record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
        record_key=approval.receipt_ref,
        payload_contract=artifact.contract,
        payload=artifact.model_dump(mode="python"),
        as_of=approval.approved_at,
        available_at=approval.approved_at,
        processing_order=0,
    )
    try:
        await records.append(
            AppendOnlyTransactionRequestV1(
                product_id=product_id,
                record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
                transaction_key=approval.receipt_ref,
                records=(record,),
                submitted_at=approval.approved_at,
            )
        )
    except Exception as exc:
        raise IntelligenceActivationApprovalUnavailable("reviewed activation approval could not be recorded") from exc
    return IntelligenceActivationApprovalResultV1Alpha1(
        approval=approval,
        bound_plan_id=str(bound.bound_plan_id),
        bound_plan_digest=str(bound.bound_plan_digest),
        start_request=intelligence_activation_start_request(bound=bound, approval=approval),
    )


async def associate_intelligence_build_session(
    *,
    request: IntelligenceBuildSessionAssociateRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> IntelligenceBuildSessionAssociationResultV1Alpha1:
    """Durably revalidate one recorded approval and admit its Builder session.

    The correlation_id is the approval's own ``execution_request_id`` and the
    goal_ref is the reviewed plan's own ``outcome_id``; no second association
    record is written. Identical calls replay the existing session revision;
    any crossed bound plan, receipt, product, or actor fails closed.
    """

    actor_ref, product_id = verified_local_intelligence_owner(user)
    bound = request.bound_plan
    plan_request = bound.binding_request.plan.request
    spec = bound.activation_spec
    if plan_request.product_id != product_id or plan_request.actor_ref != actor_ref:
        raise IntelligenceActivationApprovalDenied("bound plan crossed verified local-owner scope")
    if (
        bound.bound_plan_id is None
        or bound.bound_plan_digest is None
        or bound.execution_request_id is None
        or bound.execution_request_digest is None
        or spec.spec_id is None
        or spec.spec_hash is None
    ):
        raise IntelligenceActivationApprovalConflict("bound activation plan is missing exact identity")

    storage_id = immutable_record_storage_id(
        product_id=product_id,
        record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
        record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
        record_key=request.approval_receipt_ref,
    )
    try:
        record = await records.load_record(
            storage_id,
            product_id=product_id,
            record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
            record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
        )
        if record is None:
            raise IntelligenceActivationApprovalDenied("reviewed activation approval is not recorded")
        artifact = ReviewedIntelligenceActivationApprovalV1Alpha1.model_validate(record.payload)
    except IntelligenceActivationApprovalError:
        raise
    except Exception as exc:
        raise IntelligenceActivationApprovalUnavailable("reviewed activation approval storage is unavailable") from exc

    if (
        record.payload_contract != INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION
        or record.record_key != request.approval_receipt_ref
        or artifact.approval.receipt_ref != request.approval_receipt_ref
        or artifact.product_id != product_id
        or artifact.actor_ref != actor_ref
        or artifact.bound_plan_id != bound.bound_plan_id
        or artifact.bound_plan_digest != bound.bound_plan_digest
        or artifact.execution_request_id != bound.execution_request_id
        or artifact.execution_request_digest != bound.execution_request_digest
        or artifact.activation_spec_id != spec.spec_id
        or artifact.activation_spec_digest != f"sha256:{spec.spec_hash}"
    ):
        raise IntelligenceActivationApprovalDenied(
            "reviewed activation approval crossed exact bound plan, execution, or spec identity"
        )

    try:
        admission = await IntelligenceBuilderSessionService(store=records).start(
            product_id=product_id,
            correlation_id=bound.execution_request_id,
            goal_ref=plan_request.outcome_id,
            actor_ref=actor_ref,
            occurred_at=artifact.approval.approved_at,
        )
    except IntelligenceBuilderSessionReplayConflict as exc:
        raise IntelligenceActivationApprovalConflict(
            "Builder session identity already binds different exact material"
        ) from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceActivationApprovalUnavailable("Builder session storage is unavailable") from exc
    except Exception as exc:
        raise IntelligenceActivationApprovalUnavailable("Builder session storage is unavailable") from exc

    return IntelligenceBuildSessionAssociationResultV1Alpha1(
        bound_plan_id=str(bound.bound_plan_id),
        bound_plan_digest=str(bound.bound_plan_digest),
        approval=artifact.approval,
        session=admission.revision,
        replayed=admission.replayed,
    )


async def retry_intelligence_build_session(
    *,
    request: IntelligenceBuildRetryRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> IntelligenceBuilderSessionRevisionV1:
    """Apply the existing blocked-to-retrying Builder transition exactly once."""

    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if (
        not isinstance(actor_ref, str)
        or not actor_ref
        or not isinstance(product_id, str)
        or not product_id
        or not isinstance(authorities, list)
        or "intelligence_build" not in authorities
    ):
        raise IntelligenceActivationApprovalDenied("verified caller lacks Intelligence build authority")
    if request.current.product_id != product_id:
        raise IntelligenceActivationApprovalDenied("blocked session crossed verified product scope")
    now = datetime.now(UTC)
    if request.requested_at > now + timedelta(minutes=5):
        raise IntelligenceActivationApprovalConflict("retry requested_at cannot be materially in the future")
    if request.requested_at < request.current.occurred_at:
        raise IntelligenceActivationApprovalConflict("retry cannot predate the blocked session revision")
    try:
        admission = await IntelligenceBuilderSessionService(store=records).retry(
            request.current,
            actor_ref=actor_ref,
            occurred_at=request.requested_at,
        )
        return admission.revision
    except IntelligenceBuilderSessionReplayConflict as exc:
        raise IntelligenceActivationApprovalConflict("blocked session is stale; reload before retrying") from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceActivationApprovalConflict(str(exc)) from exc
    except Exception as exc:
        raise IntelligenceActivationApprovalUnavailable("Builder retry storage is unavailable") from exc


__all__ = [
    "INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION",
    "INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND",
    "INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE",
    "IntelligenceActivationApprovalConflict",
    "IntelligenceActivationApprovalDenied",
    "IntelligenceActivationApprovalError",
    "IntelligenceActivationApprovalResultV1Alpha1",
    "IntelligenceActivationApprovalUnavailable",
    "IntelligenceActivationApproveRequestV1Alpha1",
    "IntelligenceBuildRetryRequestV1Alpha1",
    "IntelligenceBuildSessionAssociateRequestV1Alpha1",
    "IntelligenceBuildSessionAssociationResultV1Alpha1",
    "IntelligenceBuilderSessionRevisionV1",
    "RecordedIntelligenceActivationAuthority",
    "ReviewedIntelligenceActivationApprovalV1Alpha1",
    "approve_intelligence_activation",
    "associate_intelligence_build_session",
    "intelligence_activation_start_request",
    "retry_intelligence_build_session",
    "verified_local_intelligence_owner",
]
