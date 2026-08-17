"""Production seam: bind a FIRST_BRIEFING_READY session to canonical activation.

The v1alpha2 activation plan's approval is a distinct decision from the
reviewed activation specification's approval (``/approve``): compatibility
with canonical v1alpha1 activation explicitly requires the two receipts to
differ. This module owns that separate approval channel and the coordinator
calls that turn one exact durable Builder session and its inert 0.7D
handoff into a separately admitted plan, then drive
``IntelligenceBuilderActivationService.record_current_plan``/``.activate``.

No customer-facing route here accepts client-authored handoff, plan
approval, canonical revision, or authority material: every dependency is
durably reloaded and revalidated at point of use, and every action is gated
to the single fixed local Intelligence owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ace.application import (
    BoundIntelligenceBuildPlanV1Alpha1,
    BuilderActivationReceiptArtifactV1,
    DomainActivationAdmissionService,
    DomainActivationCommitReferenceV1Alpha2,
    DomainActivationCompatibilityService,
    DomainActivationPlanAdmissionError,
    DomainActivationPlanAdmissionService,
    DomainActivationPlanNotAdmittedError,
    InstalledCompiledPackArtifactResolver,
    IntelligenceActivationPlanV1Alpha2,
    IntelligenceBuilderActivationDependencyNotReadyError,
    IntelligenceBuilderActivationError,
    IntelligenceBuilderActivationPlanCoordinator,
    IntelligenceBuilderActivationService,
    IntelligenceBuilderSessionRevisionV1,
    IntelligenceBuilderSessionService,
    activation_commit_reference,
)
from ace.core import ImmutableRecordStore
from ace.core.contracts import canonical_hash
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1, immutable_record_storage_id
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateStore,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    RecordedIntelligenceActivationAuthority,
    _verified_local_owner,
)

INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE = "intelligence_activation_plan_approval"
INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_KIND = "reviewed_activation_plan_approval"
INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_ARTIFACT_VERSION = "ace.host.reviewed-domain-activation-plan-approval/v1alpha1"


class DomainActivationPlanCoordinationError(RuntimeError):
    """Base failure for the exact FIRST_BRIEFING_READY-to-activation seam."""


class DomainActivationPlanCoordinationDenied(DomainActivationPlanCoordinationError):
    """The verified caller cannot act on this exact activation plan."""


class DomainActivationPlanCoordinationNotFound(DomainActivationPlanCoordinationError):
    """A required exact durable prerequisite does not yet exist."""


class DomainActivationPlanCoordinationConflict(DomainActivationPlanCoordinationError):
    """Submitted or durable material crossed or changed exact reviewed bindings."""


class DomainActivationPlanCoordinationUnavailable(DomainActivationPlanCoordinationError):
    """Durable activation-plan material cannot currently be resolved."""


class ReviewedDomainActivationPlanApprovalV1Alpha1(BaseModel):
    """Append-only evidence binding an owner receipt to one exact v1alpha2 plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.reviewed-domain-activation-plan-approval/v1alpha1"] = (
        INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_ARTIFACT_VERSION
    )
    product_id: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    plan_id: str = Field(min_length=1, max_length=240)
    plan_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    approval: ResolvedApprovalReceiptV1

    @model_validator(mode="after")
    def _exact_receipt(self):
        if (
            self.approval.product_id != self.product_id
            or self.approval.actor_ref != self.actor_ref
            or self.approval.subject_ref != self.plan_id
        ):
            raise ValueError("approval receipt crossed its exact activation-plan scope")
        material = self.model_dump(mode="json", exclude={"approval"})
        material["approved_at"] = self.approval.approved_at.isoformat().replace("+00:00", "Z")
        expected_hash = canonical_hash(material)
        expected_ref = f"approval:domain-activation-plan:{expected_hash[:32]}"
        if self.approval.receipt_hash != expected_hash or self.approval.receipt_ref != expected_ref:
            raise ValueError("approval receipt identity does not match exact reviewed material")
        return self


class RecordedDomainActivationPlanAuthority(CoreAuthorityResolver):
    """Resolve the v1alpha2 activation plan's own distinct approval; delegate grants.

    Grant resolution reuses whatever authority already resolves grants for
    canonical activation (governed-state authority-grant heads) instead of a
    second grant framework; only approval resolution is genuinely separate,
    reading from its own record space so this receipt can never be confused
    with the reviewed activation specification's approval.
    """

    def __init__(self, *, records: ImmutableRecordStore, grants: CoreAuthorityResolver) -> None:
        self.records = records
        self._grants = grants

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
            record_space=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE,
            record_kind=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_KIND,
            record_key=receipt_ref,
        )
        try:
            record = await self.records.load_record(
                storage_id,
                product_id=product_id,
                record_space=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE,
                record_kind=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_KIND,
            )
            if record is None:
                raise DomainActivationPlanCoordinationDenied("reviewed activation-plan approval is not recorded")
            artifact = ReviewedDomainActivationPlanApprovalV1Alpha1.model_validate(record.payload)
        except DomainActivationPlanCoordinationError:
            raise
        except Exception as exc:
            raise DomainActivationPlanCoordinationUnavailable(
                "reviewed activation-plan approval storage is unavailable"
            ) from exc
        if (
            record.payload_contract != INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_ARTIFACT_VERSION
            or record.record_key != receipt_ref
            or artifact.approval.receipt_ref != receipt_ref
            or artifact.product_id != product_id
            or artifact.plan_id != subject_ref
            or artifact.actor_ref != actor_ref
            or artifact.approval.approved_at > effective_at
        ):
            raise DomainActivationPlanCoordinationDenied("reviewed activation-plan approval is stale or mismatched")
        return artifact.approval

    async def resolve_grant(
        self,
        *,
        grant_ref: str,
        product_id: str,
        authority: str,
        effective_at: datetime,
    ) -> ResolvedAuthorityGrantV1:
        return await self._grants.resolve_grant(
            grant_ref=grant_ref,
            product_id=product_id,
            authority=authority,
            effective_at=effective_at,
        )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class DomainActivationPlanPrepareRequestV1Alpha1(BaseModel):
    """One exact current session plus bound plan, previewed without any effect."""

    model_config = ConfigDict(extra="forbid")

    current: IntelligenceBuilderSessionRevisionV1
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1
    requested_at: datetime

    @field_validator("current", mode="before")
    @classmethod
    def _json_session(cls, value):
        if isinstance(value, dict):
            return IntelligenceBuilderSessionRevisionV1.model_validate(value, strict=False)
        return value

    @field_validator("bound_plan", mode="before")
    @classmethod
    def _json_bound_plan(cls, value):
        if isinstance(value, dict):
            return BoundIntelligenceBuildPlanV1Alpha1.model_validate(value, strict=False)
        return value

    @field_validator("requested_at")
    @classmethod
    def _requested_time(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")


class DomainActivationPlanApproveRequestV1Alpha1(BaseModel):
    """One explicit owner decision over the exact plan re-derived from durable material."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve"]
    current: IntelligenceBuilderSessionRevisionV1
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1
    approved_at: datetime

    @field_validator("current", mode="before")
    @classmethod
    def _json_session(cls, value):
        if isinstance(value, dict):
            return IntelligenceBuilderSessionRevisionV1.model_validate(value, strict=False)
        return value

    @field_validator("bound_plan", mode="before")
    @classmethod
    def _json_bound_plan(cls, value):
        if isinstance(value, dict):
            return BoundIntelligenceBuildPlanV1Alpha1.model_validate(value, strict=False)
        return value

    @field_validator("approved_at")
    @classmethod
    def _approved_time(cls, value: datetime) -> datetime:
        return _aware(value, name="approved_at")


class IntelligenceBuilderPlanActivateRequestV1Alpha1(BaseModel):
    """The exact bound plan, its recorded spec approval, and a stable request time only."""

    model_config = ConfigDict(extra="forbid")

    bound_plan: BoundIntelligenceBuildPlanV1Alpha1
    activation_approval_receipt_ref: str = Field(min_length=1, max_length=240)
    requested_at: datetime

    @field_validator("bound_plan", mode="before")
    @classmethod
    def _json_bound_plan(cls, value):
        if isinstance(value, dict):
            return BoundIntelligenceBuildPlanV1Alpha1.model_validate(value, strict=False)
        return value

    @field_validator("requested_at")
    @classmethod
    def _requested_time(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")


class IntelligenceBuilderActivationResultV1Alpha1(BaseModel):
    """Exact activation receipt returned after driving record_current_plan/.activate."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.intelligence-builder-activation-result/v1alpha1"] = (
        "ace.http.intelligence-builder-activation-result/v1alpha1"
    )
    receipt: BuilderActivationReceiptArtifactV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class IntelligenceBuilderActivationPlanRuntime:
    records: ImmutableRecordStore
    coordinator: IntelligenceBuilderActivationPlanCoordinator


def intelligence_builder_activation_plan_runtime() -> IntelligenceBuilderActivationPlanRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state: GovernedStateStore = SurrealGovernedStateStore(pool)
    sessions = IntelligenceBuilderSessionService(store=records)
    packs = InstalledCompiledPackArtifactResolver.discover()
    spec_authority = RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_state)
    plan_authority = RecordedDomainActivationPlanAuthority(records=records, grants=spec_authority)
    plans = DomainActivationPlanAdmissionService(store=governed_state, authority=plan_authority)
    compatibility = DomainActivationCompatibilityService(authority=spec_authority)
    canonical = DomainActivationAdmissionService(store=governed_state, authority=spec_authority)
    activation = IntelligenceBuilderActivationService(
        sessions=sessions,
        plans=plans,
        compatibility=compatibility,
        canonical=canonical,
        packs=packs,
    )
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=sessions,
        plans=plans,
        packs=packs,
        activation=activation,
    )
    return IntelligenceBuilderActivationPlanRuntime(records=records, coordinator=coordinator)


def _plan_approval_artifact(
    *,
    plan: IntelligenceActivationPlanV1Alpha2,
    actor_ref: str,
    product_id: str,
    approved_at: datetime,
) -> ReviewedDomainActivationPlanApprovalV1Alpha1:
    if plan.plan_id is None or plan.plan_digest is None:
        raise DomainActivationPlanCoordinationConflict("prepared activation plan is missing exact identity")
    material = {
        "contract": INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_ARTIFACT_VERSION,
        "product_id": product_id,
        "actor_ref": actor_ref,
        "plan_id": plan.plan_id,
        "plan_digest": plan.plan_digest,
        "approved_at": approved_at.isoformat().replace("+00:00", "Z"),
    }
    receipt_hash = canonical_hash(material)
    approval = ResolvedApprovalReceiptV1(
        receipt_ref=f"approval:domain-activation-plan:{receipt_hash[:32]}",
        product_id=product_id,
        subject_ref=plan.plan_id,
        actor_ref=actor_ref,
        receipt_hash=receipt_hash,
        approved_at=approved_at,
    )
    return ReviewedDomainActivationPlanApprovalV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        approval=approval,
    )


def _verified_bound_scope(*, bound_plan: BoundIntelligenceBuildPlanV1Alpha1, product_id: str, actor_ref: str) -> None:
    plan_request = bound_plan.binding_request.plan.request
    if plan_request.product_id != product_id or plan_request.actor_ref != actor_ref:
        raise DomainActivationPlanCoordinationDenied("bound plan crossed verified local-owner scope")


def _verified_owner(user: dict) -> tuple[str, str]:
    try:
        return _verified_local_owner(user)
    except Exception as exc:
        raise DomainActivationPlanCoordinationDenied("verified caller is not the local Intelligence owner") from exc


async def prepare_domain_activation_plan(
    *,
    request: DomainActivationPlanPrepareRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderActivationPlanRuntime,
) -> IntelligenceActivationPlanV1Alpha2:
    """Side-effect-free preview: what the owner is about to separately approve."""

    actor_ref, product_id = _verified_owner(user)
    _verified_bound_scope(bound_plan=request.bound_plan, product_id=product_id, actor_ref=actor_ref)
    if request.current.product_id != product_id:
        raise DomainActivationPlanCoordinationDenied("Builder session crossed verified local-owner scope")
    now = datetime.now(UTC)
    if request.requested_at > now + timedelta(minutes=5):
        raise DomainActivationPlanCoordinationConflict("requested_at cannot be materially in the future")
    try:
        return await runtime.coordinator.prepare(
            product_id=product_id,
            session_id=request.current.session_id,
            bound=request.bound_plan,
            created_at=request.requested_at,
        )
    except IntelligenceBuilderActivationDependencyNotReadyError as exc:
        raise DomainActivationPlanCoordinationNotFound(str(exc)) from exc
    except IntelligenceBuilderActivationError as exc:
        raise DomainActivationPlanCoordinationConflict(str(exc)) from exc
    except DomainActivationPlanCoordinationError:
        raise
    except Exception as exc:
        raise DomainActivationPlanCoordinationUnavailable("activation-plan preview is unavailable") from exc


async def approve_domain_activation_plan(
    *,
    request: DomainActivationPlanApproveRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderActivationPlanRuntime,
) -> DomainActivationCommitReferenceV1Alpha2:
    """Record the plan's own distinct approval, then durably admit it."""

    actor_ref, product_id = _verified_owner(user)
    _verified_bound_scope(bound_plan=request.bound_plan, product_id=product_id, actor_ref=actor_ref)
    if request.current.product_id != product_id:
        raise DomainActivationPlanCoordinationDenied("Builder session crossed verified local-owner scope")
    now = datetime.now(UTC)
    if request.approved_at > now + timedelta(minutes=5):
        raise DomainActivationPlanCoordinationConflict("approved_at cannot be materially in the future")
    try:
        plan = await runtime.coordinator.prepare(
            product_id=product_id,
            session_id=request.current.session_id,
            bound=request.bound_plan,
            created_at=request.approved_at,
        )
        artifact = _plan_approval_artifact(
            plan=plan,
            actor_ref=actor_ref,
            product_id=product_id,
            approved_at=request.approved_at,
        )
        record = ImmutableRecordV1(
            product_id=product_id,
            record_space=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE,
            record_kind=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_KIND,
            record_key=artifact.approval.receipt_ref,
            payload_contract=artifact.contract,
            payload=artifact.model_dump(mode="python"),
            as_of=artifact.approval.approved_at,
            available_at=artifact.approval.approved_at,
            processing_order=0,
        )
        try:
            await runtime.records.append(
                AppendOnlyTransactionRequestV1(
                    product_id=product_id,
                    record_space=INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE,
                    transaction_key=artifact.approval.receipt_ref,
                    records=(record,),
                    submitted_at=artifact.approval.approved_at,
                )
            )
        except Exception as exc:
            raise DomainActivationPlanCoordinationUnavailable(
                "reviewed activation-plan approval could not be recorded"
            ) from exc
        committed = await runtime.coordinator.admit(
            product_id=product_id,
            session_id=request.current.session_id,
            bound=request.bound_plan,
            actor_ref=actor_ref,
            approval_receipt_ref=artifact.approval.receipt_ref,
            created_at=request.approved_at,
            committed_at=request.approved_at,
        )
        return activation_commit_reference(committed)
    except IntelligenceBuilderActivationDependencyNotReadyError as exc:
        raise DomainActivationPlanCoordinationNotFound(str(exc)) from exc
    except (IntelligenceBuilderActivationError, DomainActivationPlanAdmissionError) as exc:
        raise DomainActivationPlanCoordinationConflict(str(exc)) from exc
    except DomainActivationPlanCoordinationError:
        raise
    except Exception as exc:
        raise DomainActivationPlanCoordinationUnavailable("activation-plan approval is unavailable") from exc


async def activate_intelligence_builder_plan(
    *,
    request: IntelligenceBuilderPlanActivateRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderActivationPlanRuntime,
) -> IntelligenceBuilderActivationResultV1Alpha1:
    """Derive the session from the admitted plan and crash-safely drive activation."""

    actor_ref, product_id = _verified_owner(user)
    _verified_bound_scope(bound_plan=request.bound_plan, product_id=product_id, actor_ref=actor_ref)
    now = datetime.now(UTC)
    if request.requested_at > now + timedelta(minutes=5):
        raise DomainActivationPlanCoordinationConflict("requested_at cannot be materially in the future")
    try:
        outcome = await runtime.coordinator.activate(
            product_id=product_id,
            bound=request.bound_plan,
            activation_approval_receipt_ref=request.activation_approval_receipt_ref,
            requested_at=request.requested_at,
        )
        return IntelligenceBuilderActivationResultV1Alpha1(
            receipt=outcome.receipt_artifact,
            replayed=outcome.replayed,
        )
    except (DomainActivationPlanNotAdmittedError, IntelligenceBuilderActivationDependencyNotReadyError) as exc:
        raise DomainActivationPlanCoordinationNotFound(str(exc)) from exc
    except IntelligenceBuilderActivationError as exc:
        raise DomainActivationPlanCoordinationConflict(str(exc)) from exc
    except DomainActivationPlanCoordinationError:
        raise
    except Exception as exc:
        raise DomainActivationPlanCoordinationUnavailable("activation is unavailable") from exc


__all__ = [
    "INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_ARTIFACT_VERSION",
    "INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_KIND",
    "INTELLIGENCE_ACTIVATION_PLAN_APPROVAL_RECORD_SPACE",
    "DomainActivationPlanApproveRequestV1Alpha1",
    "DomainActivationPlanCoordinationConflict",
    "DomainActivationPlanCoordinationDenied",
    "DomainActivationPlanCoordinationError",
    "DomainActivationPlanCoordinationNotFound",
    "DomainActivationPlanCoordinationUnavailable",
    "DomainActivationPlanPrepareRequestV1Alpha1",
    "DomainActivationCommitReferenceV1Alpha2",
    "IntelligenceActivationPlanV1Alpha2",
    "IntelligenceBuilderActivationPlanRuntime",
    "IntelligenceBuilderActivationResultV1Alpha1",
    "IntelligenceBuilderPlanActivateRequestV1Alpha1",
    "RecordedDomainActivationPlanAuthority",
    "ReviewedDomainActivationPlanApprovalV1Alpha1",
    "activate_intelligence_builder_plan",
    "approve_domain_activation_plan",
    "intelligence_builder_activation_plan_runtime",
    "prepare_domain_activation_plan",
]
