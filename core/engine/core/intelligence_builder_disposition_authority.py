"""Durable single-owner approval evidence for the Builder progression's three
proposal dispositions: source-scope (Connection Agent), concept-model
(Ontology Agent), and intelligence-model (Intelligence Agent).

Per the frozen Builder-session progression addendum (PI13 addendum 9), these
three approvals stay separate, explicit, and exact: one request/record/receipt
per exact current proposal, never bundled. This host adapter mints and
resolves that reviewed evidence so the existing agents' unchanged
``CoreAuthorityResolver.resolve_approval`` calls can be satisfied durably. No
grant is minted here; grant resolution (if ever required through this
resolver) delegates explicitly to an injected existing resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ace.application.intelligence_agent_contracts import IntelligenceModelProposalV1
from ace.application.intelligence_builder import (
    IntelligenceBuilderArtifactNotFoundError,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingStage,
    SourceScopeProposalV1,
)
from ace.application.ontology_agent_contracts import ConceptModelProposalV1
from ace.core.contracts import canonical_hash
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.state import (
    CoreAuthorityResolver,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.intelligence_activation_authority import verified_local_intelligence_owner


class BuilderDispositionKind(StrEnum):
    SOURCE_SCOPE = "source_scope"
    CONCEPT_MODEL = "concept_model"
    INTELLIGENCE_MODEL = "intelligence_model"


REVIEWED_BUILDER_SOURCE_SCOPE_APPROVAL_VERSION = "ace.host.reviewed-builder-source-scope-approval/v1alpha1"
REVIEWED_BUILDER_CONCEPT_MODEL_APPROVAL_VERSION = "ace.host.reviewed-builder-concept-model-approval/v1alpha1"
REVIEWED_BUILDER_INTELLIGENCE_MODEL_APPROVAL_VERSION = "ace.host.reviewed-builder-intelligence-model-approval/v1alpha1"


@dataclass(frozen=True, slots=True)
class _DispositionKindConfig:
    kind: BuilderDispositionKind
    contract: str
    record_space: str
    record_kind: str
    receipt_prefix: str
    artifact_kind: OnboardingArtifactKind
    proposal_type: type
    required_stage: OnboardingStage


_KIND_CONFIG: dict[BuilderDispositionKind, _DispositionKindConfig] = {
    BuilderDispositionKind.SOURCE_SCOPE: _DispositionKindConfig(
        kind=BuilderDispositionKind.SOURCE_SCOPE,
        contract=REVIEWED_BUILDER_SOURCE_SCOPE_APPROVAL_VERSION,
        record_space="intelligence_builder_source_scope_approval",
        record_kind="reviewed_source_scope_approval",
        receipt_prefix="approval:builder-source-scope",
        artifact_kind=OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL,
        proposal_type=SourceScopeProposalV1,
        required_stage=OnboardingStage.SOURCES_CONNECTING,
    ),
    BuilderDispositionKind.CONCEPT_MODEL: _DispositionKindConfig(
        kind=BuilderDispositionKind.CONCEPT_MODEL,
        contract=REVIEWED_BUILDER_CONCEPT_MODEL_APPROVAL_VERSION,
        record_space="intelligence_builder_concept_model_approval",
        record_kind="reviewed_concept_model_approval",
        receipt_prefix="approval:builder-concept-model",
        artifact_kind=OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
        proposal_type=ConceptModelProposalV1,
        required_stage=OnboardingStage.CONCEPT_MODEL_PROPOSED,
    ),
    BuilderDispositionKind.INTELLIGENCE_MODEL: _DispositionKindConfig(
        kind=BuilderDispositionKind.INTELLIGENCE_MODEL,
        contract=REVIEWED_BUILDER_INTELLIGENCE_MODEL_APPROVAL_VERSION,
        record_space="intelligence_builder_intelligence_model_approval",
        record_kind="reviewed_intelligence_model_approval",
        receipt_prefix="approval:builder-intelligence-model",
        artifact_kind=OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL,
        proposal_type=IntelligenceModelProposalV1,
        required_stage=OnboardingStage.INTELLIGENCE_MODEL_PROPOSED,
    ),
}


def _verified_owner(user: dict) -> tuple[str, str]:
    try:
        return verified_local_intelligence_owner(user)
    except Exception as exc:
        raise BuilderDispositionApprovalDenied("verified caller is not the local Intelligence owner") from exc


def _config_for_receipt_ref(receipt_ref: str) -> _DispositionKindConfig | None:
    for config in _KIND_CONFIG.values():
        if receipt_ref.startswith(f"{config.receipt_prefix}:"):
            return config
    return None


class BuilderDispositionApprovalError(RuntimeError):
    """Base failure for exact reviewed Builder disposition approval."""


class BuilderDispositionApprovalDenied(BuilderDispositionApprovalError):
    """The verified caller cannot approve or resolve this exact disposition."""


class BuilderDispositionApprovalConflict(BuilderDispositionApprovalError):
    """Submitted or durable material crossed or changed exact reviewed bindings."""


class BuilderDispositionApprovalUnavailable(BuilderDispositionApprovalError):
    """Durable Builder disposition approval material cannot currently be resolved."""


class ReviewedBuilderDispositionApprovalV1Alpha1(BaseModel):
    """Append-only evidence binding an owner receipt to one exact current proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal[
        "ace.host.reviewed-builder-source-scope-approval/v1alpha1",
        "ace.host.reviewed-builder-concept-model-approval/v1alpha1",
        "ace.host.reviewed-builder-intelligence-model-approval/v1alpha1",
    ]
    product_id: str = Field(min_length=1, max_length=240)
    actor_ref: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    session_revision_id: str = Field(min_length=1, max_length=240)
    session_revision_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    proposal_kind: BuilderDispositionKind
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    approval: ResolvedApprovalReceiptV1

    @model_validator(mode="after")
    def _exact_receipt(self):
        config = _KIND_CONFIG.get(self.proposal_kind)
        if config is None or config.contract != self.contract:
            raise ValueError("reviewed builder approval crossed its exact proposal kind")
        if (
            self.approval.product_id != self.product_id
            or self.approval.actor_ref != self.actor_ref
            or self.approval.subject_ref != self.proposal_id
        ):
            raise ValueError("approval receipt crossed its exact reviewed disposition scope")
        material = self.model_dump(mode="json", exclude={"approval"})
        material["approved_at"] = self.approval.approved_at.isoformat().replace("+00:00", "Z")
        expected_hash = canonical_hash(material)
        expected_ref = f"{config.receipt_prefix}:{expected_hash[:32]}"
        if self.approval.receipt_hash != expected_hash or self.approval.receipt_ref != expected_ref:
            raise ValueError("approval receipt identity does not match exact reviewed material")
        return self


class BuilderDispositionApprovalResultV1Alpha1(BaseModel):
    """Exact recorded approval plus the durable coordinates it binds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.http.builder-disposition-approval-result/v1alpha1"] = (
        "ace.http.builder-disposition-approval-result/v1alpha1"
    )
    approval: ResolvedApprovalReceiptV1
    session_revision_id: str
    session_revision_digest: str
    proposal_id: str
    proposal_digest: str


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class BuilderSourceScopeApproveRequestV1Alpha1(BaseModel):
    """One explicit owner decision over the exact current source-scope proposal."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve"]
    current: IntelligenceBuilderSessionRevisionV1
    proposal: SourceScopeProposalV1
    approved_at: datetime

    @field_validator("current", "proposal", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = IntelligenceBuilderSessionRevisionV1 if info.field_name == "current" else SourceScopeProposalV1
            return model.model_validate(value, strict=False)
        return value

    @field_validator("approved_at")
    @classmethod
    def _approved_time(cls, value: datetime) -> datetime:
        return _aware(value, name="approved_at")


class BuilderConceptModelApproveRequestV1Alpha1(BaseModel):
    """One explicit owner decision over the exact current concept-model proposal."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve"]
    current: IntelligenceBuilderSessionRevisionV1
    proposal: ConceptModelProposalV1
    approved_at: datetime

    @field_validator("current", "proposal", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = IntelligenceBuilderSessionRevisionV1 if info.field_name == "current" else ConceptModelProposalV1
            return model.model_validate(value, strict=False)
        return value

    @field_validator("approved_at")
    @classmethod
    def _approved_time(cls, value: datetime) -> datetime:
        return _aware(value, name="approved_at")


class BuilderIntelligenceModelApproveRequestV1Alpha1(BaseModel):
    """One explicit owner decision over the exact current intelligence-model proposal."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve"]
    current: IntelligenceBuilderSessionRevisionV1
    proposal: IntelligenceModelProposalV1
    approved_at: datetime

    @field_validator("current", "proposal", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = (
                IntelligenceBuilderSessionRevisionV1 if info.field_name == "current" else IntelligenceModelProposalV1
            )
            return model.model_validate(value, strict=False)
        return value

    @field_validator("approved_at")
    @classmethod
    def _approved_time(cls, value: datetime) -> datetime:
        return _aware(value, name="approved_at")


class RecordedIntelligenceBuilderDispositionAuthority(CoreAuthorityResolver):
    """Resolve reviewed Builder disposition approvals; delegate grant resolution.

    Grant resolution is not owned here: the three Builder agents' governed
    calls that need it already resolve grants elsewhere, so any grant lookup
    reaching this resolver delegates explicitly to the injected existing
    resolver rather than minting or inventing one.
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
        config = _config_for_receipt_ref(receipt_ref)
        if config is None:
            raise BuilderDispositionApprovalDenied("reviewed builder approval kind is unrecognized")
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=config.record_space,
            record_kind=config.record_kind,
            record_key=receipt_ref,
        )
        try:
            record = await self.records.load_record(
                storage_id,
                product_id=product_id,
                record_space=config.record_space,
                record_kind=config.record_kind,
            )
            if record is None:
                raise BuilderDispositionApprovalDenied("reviewed builder approval is not recorded")
            artifact = ReviewedBuilderDispositionApprovalV1Alpha1.model_validate(record.payload)
        except BuilderDispositionApprovalError:
            raise
        except Exception as exc:
            raise BuilderDispositionApprovalUnavailable("reviewed builder approval storage is unavailable") from exc
        if (
            record.product_id != product_id
            or record.record_space != config.record_space
            or record.record_kind != config.record_kind
            or record.record_key != receipt_ref
            or record.payload_contract != config.contract
            or record.as_of != artifact.approval.approved_at
            or record.available_at != artifact.approval.approved_at
            or artifact.proposal_kind != config.kind
            or artifact.approval.receipt_ref != receipt_ref
            or artifact.product_id != product_id
            or artifact.proposal_id != subject_ref
            or artifact.actor_ref != actor_ref
            or artifact.approval.approved_at > effective_at
        ):
            raise BuilderDispositionApprovalDenied("reviewed builder approval is stale or mismatched")
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


class _UnreachableGrantAuthority:
    """Grant delegate stand-in for reopening approval evidence; never invoked here."""

    async def resolve_approval(self, **kwargs) -> ResolvedApprovalReceiptV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: approval reopen must resolve approval, not grant, evidence")

    async def resolve_grant(self, **kwargs) -> ResolvedAuthorityGrantV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: reopening approval evidence never resolves a grant")


_UNUSED_GRANT_AUTHORITY = _UnreachableGrantAuthority()


async def _approve_builder_disposition(
    *,
    kind: BuilderDispositionKind,
    records: ImmutableRecordStore,
    user: dict,
    current: IntelligenceBuilderSessionRevisionV1,
    proposal,
    approved_at: datetime,
) -> BuilderDispositionApprovalResultV1Alpha1:
    config = _KIND_CONFIG[kind]
    actor_ref, product_id = _verified_owner(user)
    now = datetime.now(UTC)
    if approved_at > now + timedelta(minutes=5):
        raise BuilderDispositionApprovalConflict("approved_at cannot be materially in the future")
    if current.product_id != product_id:
        raise BuilderDispositionApprovalDenied("Builder session crossed verified local-owner scope")

    sessions = IntelligenceBuilderSessionService(store=records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=current.session_id,
            available_at=approved_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise BuilderDispositionApprovalUnavailable("Builder session storage is unavailable") from exc
    if latest is None or latest.revision_id != current.revision_id or latest.revision_digest != current.revision_digest:
        raise BuilderDispositionApprovalConflict("Builder session is stale; reload before approving")
    if latest.stage is not config.required_stage:
        raise BuilderDispositionApprovalConflict("Builder session is not at the exact stage for this disposition")

    reference = next(
        (item for item in latest.artifacts if item.artifact_kind is config.artifact_kind),
        None,
    )
    if (
        reference is None
        or reference.artifact_id != proposal.proposal_id
        or reference.artifact_digest != proposal.proposal_digest
        or proposal.session_id != latest.session_id
    ):
        raise BuilderDispositionApprovalConflict("proposal is not the exact current session handoff")

    try:
        persisted = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=config.proposal_type,
            available_at=approved_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise BuilderDispositionApprovalDenied("proposal is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise BuilderDispositionApprovalUnavailable("Builder artifact storage is unavailable") from exc

    exact_proposal = config.proposal_type.model_validate(proposal.model_dump(mode="python"))
    if persisted != exact_proposal:
        raise BuilderDispositionApprovalConflict("proposal differs from exact durable material")

    material = {
        "contract": config.contract,
        "product_id": product_id,
        "actor_ref": actor_ref,
        "session_id": latest.session_id,
        "session_revision_id": str(latest.revision_id),
        "session_revision_digest": str(latest.revision_digest),
        "proposal_kind": kind.value,
        "proposal_id": str(exact_proposal.proposal_id),
        "proposal_digest": str(exact_proposal.proposal_digest),
        "approved_at": approved_at.isoformat().replace("+00:00", "Z"),
    }
    receipt_hash = canonical_hash(material)
    approval = ResolvedApprovalReceiptV1(
        receipt_ref=f"{config.receipt_prefix}:{receipt_hash[:32]}",
        product_id=product_id,
        subject_ref=str(exact_proposal.proposal_id),
        actor_ref=actor_ref,
        receipt_hash=receipt_hash,
        approved_at=approved_at,
    )
    artifact = ReviewedBuilderDispositionApprovalV1Alpha1(
        contract=config.contract,
        product_id=product_id,
        actor_ref=actor_ref,
        session_id=latest.session_id,
        session_revision_id=str(latest.revision_id),
        session_revision_digest=str(latest.revision_digest),
        proposal_kind=kind,
        proposal_id=str(exact_proposal.proposal_id),
        proposal_digest=str(exact_proposal.proposal_digest),
        approval=approval,
    )
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=config.record_space,
        record_kind=config.record_kind,
        record_key=approval.receipt_ref,
        payload_contract=artifact.contract,
        payload=artifact.model_dump(mode="python"),
        as_of=approval.approved_at,
        available_at=approval.approved_at,
        processing_order=0,
    )
    request = AppendOnlyTransactionRequestV1(
        product_id=product_id,
        record_space=config.record_space,
        transaction_key=approval.receipt_ref,
        records=(record,),
        submitted_at=approval.approved_at,
    )
    try:
        receipt = await records.append(request)
    except ImmutableRecordReplayConflict as exc:
        raise BuilderDispositionApprovalConflict(
            "reviewed builder approval identity already binds different exact material"
        ) from exc
    except Exception as exc:
        raise BuilderDispositionApprovalUnavailable("reviewed builder approval could not be recorded") from exc

    if receipt != request.receipt():
        raise BuilderDispositionApprovalUnavailable(
            "reviewed builder approval receipt does not match the exact append request"
        )

    reopened = await RecordedIntelligenceBuilderDispositionAuthority(
        records=records, grants=_UNUSED_GRANT_AUTHORITY
    ).resolve_approval(
        receipt_ref=approval.receipt_ref,
        product_id=product_id,
        subject_ref=approval.subject_ref,
        actor_ref=actor_ref,
        effective_at=approval.approved_at,
    )
    if reopened != approval:
        raise BuilderDispositionApprovalUnavailable(
            "reviewed builder approval could not be reopened through the production resolver"
        )

    return BuilderDispositionApprovalResultV1Alpha1(
        approval=reopened,
        session_revision_id=str(latest.revision_id),
        session_revision_digest=str(latest.revision_digest),
        proposal_id=str(exact_proposal.proposal_id),
        proposal_digest=str(exact_proposal.proposal_digest),
    )


async def approve_builder_source_scope(
    *,
    request: BuilderSourceScopeApproveRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> BuilderDispositionApprovalResultV1Alpha1:
    """Record an explicit local-owner approval for one exact current source-scope proposal."""

    return await _approve_builder_disposition(
        kind=BuilderDispositionKind.SOURCE_SCOPE,
        records=records,
        user=user,
        current=request.current,
        proposal=request.proposal,
        approved_at=request.approved_at,
    )


async def approve_builder_concept_model(
    *,
    request: BuilderConceptModelApproveRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> BuilderDispositionApprovalResultV1Alpha1:
    """Record an explicit local-owner approval for one exact current concept-model proposal."""

    return await _approve_builder_disposition(
        kind=BuilderDispositionKind.CONCEPT_MODEL,
        records=records,
        user=user,
        current=request.current,
        proposal=request.proposal,
        approved_at=request.approved_at,
    )


async def approve_builder_intelligence_model(
    *,
    request: BuilderIntelligenceModelApproveRequestV1Alpha1,
    user: dict,
    records: ImmutableRecordStore,
) -> BuilderDispositionApprovalResultV1Alpha1:
    """Record an explicit local-owner approval for one exact current intelligence-model proposal."""

    return await _approve_builder_disposition(
        kind=BuilderDispositionKind.INTELLIGENCE_MODEL,
        records=records,
        user=user,
        current=request.current,
        proposal=request.proposal,
        approved_at=request.approved_at,
    )


__all__ = [
    "REVIEWED_BUILDER_CONCEPT_MODEL_APPROVAL_VERSION",
    "REVIEWED_BUILDER_INTELLIGENCE_MODEL_APPROVAL_VERSION",
    "REVIEWED_BUILDER_SOURCE_SCOPE_APPROVAL_VERSION",
    "BuilderConceptModelApproveRequestV1Alpha1",
    "BuilderDispositionApprovalConflict",
    "BuilderDispositionApprovalDenied",
    "BuilderDispositionApprovalError",
    "BuilderDispositionApprovalResultV1Alpha1",
    "BuilderDispositionApprovalUnavailable",
    "BuilderDispositionKind",
    "BuilderIntelligenceModelApproveRequestV1Alpha1",
    "BuilderSourceScopeApproveRequestV1Alpha1",
    "RecordedIntelligenceBuilderDispositionAuthority",
    "ReviewedBuilderDispositionApprovalV1Alpha1",
    "approve_builder_concept_model",
    "approve_builder_intelligence_model",
    "approve_builder_source_scope",
]
