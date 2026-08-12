"""Application services for proposal-only Intelligence Builder onboarding.

The first executable slice implements only the Connection Agent. Connector
transport and credentials remain behind a host-supplied provider; Core ports own
opaque persistence and approval resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from ace.application.intelligence_builder_contracts import (
    ONBOARDING_SESSION_REVISION_VERSION,
    ConnectionEffect,
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceOptionCatalogV1,
    SourceProfileProposalV1,
    SourceSampleV1,
    SourceScopeProposalV1,
    SourceScopeSelectionV1,
)
from ace.application.ontology_agent_contracts import ConceptModelDispositionV1, ConceptModelProposalV1
from ace.core.contracts import canonical_hash
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1

INTELLIGENCE_BUILDER_RECORD_SPACE = "ace.application.intelligence-builder"
ONBOARDING_SESSION_REVISION_RECORD_KIND = "onboarding_session_revision"
ONBOARDING_ARTIFACT_RECORD_KIND = "onboarding_artifact"

OnboardingArtifact = (
    SourceScopeProposalV1
    | SourceProfileProposalV1
    | ConceptModelProposalV1
    | ConceptModelDispositionV1
)
OnboardingArtifactT = TypeVar(
    "OnboardingArtifactT",
    SourceScopeProposalV1,
    SourceProfileProposalV1,
    ConceptModelProposalV1,
    ConceptModelDispositionV1,
)


class IntelligenceBuilderSessionError(RuntimeError):
    """The onboarding session failed exact state, persistence, or replay checks."""


class IntelligenceBuilderSessionReplayConflict(IntelligenceBuilderSessionError):
    """One stable onboarding transition identity already binds other material."""


class ConnectionAgentError(RuntimeError):
    """The Connection Agent failed before a safe handoff could be produced."""


class ConnectionAgentStaleProposal(ConnectionAgentError):
    """A caller attempted to use a source proposal that is no longer current."""


class ConnectionAgentScopeViolation(ConnectionAgentError):
    """A host provider returned material outside the exact approved source scope."""


class RegisteredSourceOptionProvider(Protocol):
    """Host-owned seam for registered options and approved bounded test/sample effects.

    Implementations own credential and transport handling. Neither method may
    return credentials or persist authoritative connector configuration through
    these contracts.
    """

    async def catalog(self) -> SourceOptionCatalogV1: ...

    async def test_and_sample(self, proposal: SourceScopeProposalV1) -> tuple[SourceSampleV1, ...]: ...


@dataclass(frozen=True, slots=True)
class IntelligenceBuilderSessionAdmission:
    revision: IntelligenceBuilderSessionRevisionV1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class IntelligenceBuilderArtifactAdmission:
    artifact_id: str
    artifact_digest: str
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class ConnectionScopeAdmission:
    proposal: SourceScopeProposalV1
    proposal_admission: IntelligenceBuilderArtifactAdmission
    session: IntelligenceBuilderSessionAdmission


@dataclass(frozen=True, slots=True)
class ConnectionAgentOutcome:
    session: IntelligenceBuilderSessionAdmission
    profile: SourceProfileProposalV1 | None
    profile_admission: IntelligenceBuilderArtifactAdmission | None
    blocked_reason: OnboardingBlockReason | None

    @property
    def connected(self) -> bool:
        return self.profile is not None and self.blocked_reason is None


_PRIMARY_TRANSITIONS: dict[
    tuple[OnboardingStage, OnboardingStage],
    OnboardingTransitionAuthority,
] = {
    (OnboardingStage.GOAL_SELECTED, OnboardingStage.SOURCES_CONNECTING): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.SOURCES_CONNECTING, OnboardingStage.SOURCES_CONNECTING): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.SOURCES_CONNECTING, OnboardingStage.SOURCES_READY): (
        OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION
    ),
    (OnboardingStage.SOURCES_READY, OnboardingStage.CONCEPT_MODEL_PROPOSED): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.CONCEPT_MODEL_PROPOSED, OnboardingStage.CONCEPT_MODEL_PROPOSED): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.CONCEPT_MODEL_PROPOSED, OnboardingStage.CONCEPT_MODEL_APPROVED): (
        OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION
    ),
    (OnboardingStage.CONCEPT_MODEL_APPROVED, OnboardingStage.INTELLIGENCE_MODEL_PROPOSED): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.INTELLIGENCE_MODEL_PROPOSED, OnboardingStage.INTELLIGENCE_MODEL_APPROVED): (
        OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION
    ),
    (OnboardingStage.INTELLIGENCE_MODEL_APPROVED, OnboardingStage.FIRST_BRIEFING_READY): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.FIRST_BRIEFING_READY, OnboardingStage.ACTIVATION_PENDING): (
        OnboardingTransitionAuthority.AGENT_PROPOSAL
    ),
    (OnboardingStage.ACTIVATION_PENDING, OnboardingStage.ACTIVE): (
        OnboardingTransitionAuthority.CORE_ACTIVATION
    ),
}


def _transaction_key(session_id: str, sequence: int) -> str:
    return f"intelligence_builder_session:{canonical_hash([session_id, sequence])[:32]}"


def _artifact_transaction_key(product_id: str, artifact_id: str, artifact_digest: str) -> str:
    return f"intelligence_builder_artifact:{canonical_hash([product_id, artifact_id, artifact_digest])[:32]}"


def _session_record(revision: IntelligenceBuilderSessionRevisionV1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=revision.product_id,
        record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
        record_kind=ONBOARDING_SESSION_REVISION_RECORD_KIND,
        record_key=str(revision.revision_id),
        payload_contract=revision.contract,
        payload=revision.model_dump(mode="python"),
        as_of=revision.occurred_at,
        available_at=revision.occurred_at,
        processing_order=0,
    )


def _artifact_material(artifact: OnboardingArtifact) -> tuple[str, str, datetime]:
    if isinstance(artifact, SourceScopeProposalV1):
        return str(artifact.proposal_id), str(artifact.proposal_digest), artifact.created_at
    if isinstance(artifact, SourceProfileProposalV1):
        return str(artifact.proposal_id), str(artifact.proposal_digest), artifact.created_at
    if isinstance(artifact, ConceptModelProposalV1):
        return str(artifact.proposal_id), str(artifact.proposal_digest), artifact.created_at
    if isinstance(artifact, ConceptModelDispositionV1):
        return str(artifact.disposition_id), str(artifact.disposition_digest), artifact.approved_at
    raise TypeError("unsupported onboarding artifact contract")


def _artifact_kind(artifact: OnboardingArtifact) -> OnboardingArtifactKind:
    if isinstance(artifact, SourceScopeProposalV1):
        return OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL
    if isinstance(artifact, SourceProfileProposalV1):
        return OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL
    if isinstance(artifact, ConceptModelProposalV1):
        return OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL
    if isinstance(artifact, ConceptModelDispositionV1):
        return OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION
    raise TypeError("unsupported onboarding artifact contract")


def _artifact_record(*, product_id: str, artifact: OnboardingArtifact) -> ImmutableRecordV1:
    artifact_id, _, occurred_at = _artifact_material(artifact)
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
        record_kind=ONBOARDING_ARTIFACT_RECORD_KIND,
        record_key=artifact_id,
        payload_contract=artifact.contract,
        payload=artifact.model_dump(mode="python"),
        as_of=occurred_at,
        available_at=occurred_at,
        processing_order=0,
    )


def _artifact(
    kind: OnboardingArtifactKind,
    artifact_id: str,
    artifact_digest: str,
) -> OnboardingArtifactReferenceV1:
    return OnboardingArtifactReferenceV1(
        artifact_kind=kind,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
    )


def _replace_artifact(
    artifacts: tuple[OnboardingArtifactReferenceV1, ...],
    replacement: OnboardingArtifactReferenceV1,
    *,
    remove: tuple[OnboardingArtifactKind, ...] = (),
) -> tuple[OnboardingArtifactReferenceV1, ...]:
    removed = set(remove) | {replacement.artifact_kind}
    return tuple(item for item in artifacts if item.artifact_kind not in removed) + (replacement,)


class IntelligenceBuilderSessionService:
    """Persist and replay one exact append-only onboarding session chain."""

    def __init__(self, *, store: ImmutableRecordStore) -> None:
        self.store = store

    async def persist_artifact(
        self,
        *,
        product_id: str,
        artifact: OnboardingArtifact,
    ) -> IntelligenceBuilderArtifactAdmission:
        exact: OnboardingArtifact
        if isinstance(artifact, SourceScopeProposalV1):
            exact = SourceScopeProposalV1.model_validate(artifact.model_dump(mode="python"))
        elif isinstance(artifact, SourceProfileProposalV1):
            exact = SourceProfileProposalV1.model_validate(artifact.model_dump(mode="python"))
        elif isinstance(artifact, ConceptModelProposalV1):
            exact = ConceptModelProposalV1.model_validate(artifact.model_dump(mode="python"))
        elif isinstance(artifact, ConceptModelDispositionV1):
            exact = ConceptModelDispositionV1.model_validate(artifact.model_dump(mode="python"))
        else:
            raise IntelligenceBuilderSessionError("unsupported onboarding artifact failed closed")
        artifact_id, artifact_digest, occurred_at = _artifact_material(exact)
        record = _artifact_record(product_id=product_id, artifact=exact)
        request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
            transaction_key=_artifact_transaction_key(product_id, artifact_id, artifact_digest),
            records=(record,),
            submitted_at=occurred_at,
        )
        replayed = False
        try:
            receipt = await self.store.append(request)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            try:
                receipt = await self.store.load_transaction_receipt(
                    product_id=product_id,
                    record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                    transaction_key=request.transaction_key,
                )
            except Exception:
                raise IntelligenceBuilderSessionError(
                    "onboarding artifact replay failed closed"
                ) from None
            replayed = True
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding artifact failed atomic persistence") from None
        if receipt is None or receipt != request.receipt():
            raise IntelligenceBuilderSessionReplayConflict(
                "onboarding artifact identity already binds different exact material"
            )
        persisted = await self.load_artifact(
            product_id=product_id,
            reference=_artifact(_artifact_kind(exact), artifact_id, artifact_digest),
            artifact_type=type(exact),
            available_at=occurred_at,
        )
        if persisted != exact:
            raise IntelligenceBuilderSessionReplayConflict(
                "persisted onboarding artifact does not match exact submitted material"
            )
        return IntelligenceBuilderArtifactAdmission(
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
            transaction_receipt=receipt,
            replayed=replayed,
        )

    async def load_artifact(
        self,
        *,
        product_id: str,
        reference: OnboardingArtifactReferenceV1,
        artifact_type: type[OnboardingArtifactT],
        available_at: datetime,
    ) -> OnboardingArtifactT:
        try:
            records = await self.store.read_as_of(
                product_id=product_id,
                record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                record_kind=ONBOARDING_ARTIFACT_RECORD_KIND,
                available_at=available_at,
            )
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding artifact load failed closed") from None
        matches = [record for record in records if record.record_key == reference.artifact_id]
        if len(matches) != 1:
            raise IntelligenceBuilderSessionError("onboarding artifact is missing or has conflicting records")
        record = matches[0]
        try:
            artifact = artifact_type.model_validate(record.payload)
            artifact_id, artifact_digest, occurred_at = _artifact_material(artifact)
        except Exception:
            raise IntelligenceBuilderSessionError("persisted onboarding artifact failed revalidation") from None
        if (
            artifact_id != reference.artifact_id
            or artifact_digest != reference.artifact_digest
            or record.payload_contract != artifact.contract
            or record.as_of != occurred_at
            or record.available_at != occurred_at
        ):
            raise IntelligenceBuilderSessionError("persisted onboarding artifact crossed exact material")
        return artifact

    async def _replay(
        self,
        revision: IntelligenceBuilderSessionRevisionV1,
    ) -> IntelligenceBuilderSessionAdmission | None:
        transaction_key = _transaction_key(revision.session_id, revision.sequence)
        try:
            receipt = await self.store.load_transaction_receipt(
                product_id=revision.product_id,
                record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                transaction_key=transaction_key,
            )
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding transaction load failed closed") from None
        if receipt is None:
            return None
        if len(receipt.records) != 1:
            raise IntelligenceBuilderSessionError("onboarding transition must contain one exact session revision")
        reference = receipt.records[0]
        try:
            record = await self.store.load_record(
                reference.storage_id,
                product_id=revision.product_id,
                record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                record_kind=ONBOARDING_SESSION_REVISION_RECORD_KIND,
            )
            persisted = None if record is None else IntelligenceBuilderSessionRevisionV1.model_validate(record.payload)
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding replay failed exact record validation") from None
        if (
            record is None
            or persisted is None
            or record.reference() != reference
            or record.payload_contract != ONBOARDING_SESSION_REVISION_VERSION
            or record.record_key != persisted.revision_id
            or persisted != revision
        ):
            raise IntelligenceBuilderSessionReplayConflict(
                "onboarding transition identity already binds different exact material"
            )
        request = AppendOnlyTransactionRequestV1(
            product_id=revision.product_id,
            record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
            transaction_key=transaction_key,
            records=(record,),
            submitted_at=revision.occurred_at,
        )
        if receipt != request.receipt():
            raise IntelligenceBuilderSessionError("onboarding receipt does not bind the exact replayed revision")
        return IntelligenceBuilderSessionAdmission(
            revision=persisted,
            transaction_receipt=receipt,
            replayed=True,
        )

    async def _persist(
        self,
        revision: IntelligenceBuilderSessionRevisionV1,
    ) -> IntelligenceBuilderSessionAdmission:
        replay = await self._replay(revision)
        if replay is not None:
            return replay
        request = AppendOnlyTransactionRequestV1(
            product_id=revision.product_id,
            record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
            transaction_key=_transaction_key(revision.session_id, revision.sequence),
            records=(_session_record(revision),),
            submitted_at=revision.occurred_at,
        )
        try:
            receipt = await self.store.append(request)
        except ImmutableRecordReplayConflict:
            replay = await self._replay(revision)
            if replay is None:
                raise IntelligenceBuilderSessionReplayConflict(
                    "concurrent onboarding transition did not expose exact durable material"
                ) from None
            return replay
        except ImmutableRecordPersistenceError:
            replay = await self._replay(revision)
            if replay is None:
                raise IntelligenceBuilderSessionError("onboarding transition failed atomic persistence") from None
            return replay
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding transition failed atomic persistence") from None
        if receipt != request.receipt():
            raise IntelligenceBuilderSessionError("Core append receipt does not bind the exact onboarding revision")
        return IntelligenceBuilderSessionAdmission(
            revision=revision,
            transaction_receipt=receipt,
            replayed=False,
        )

    async def load_latest(
        self,
        *,
        product_id: str,
        session_id: str,
        available_at: datetime,
    ) -> IntelligenceBuilderSessionRevisionV1 | None:
        try:
            records = await self.store.read_as_of(
                product_id=product_id,
                record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                record_kind=ONBOARDING_SESSION_REVISION_RECORD_KIND,
                available_at=available_at,
            )
        except Exception:
            raise IntelligenceBuilderSessionError("onboarding session history load failed closed") from None
        revisions: list[IntelligenceBuilderSessionRevisionV1] = []
        for record in records:
            try:
                revision = IntelligenceBuilderSessionRevisionV1.model_validate(record.payload)
            except Exception:
                raise IntelligenceBuilderSessionError("persisted onboarding revision failed revalidation") from None
            if revision.session_id != session_id:
                continue
            if (
                revision.product_id != product_id
                or record.payload_contract != revision.contract
                or record.record_key != revision.revision_id
                or record.as_of != revision.occurred_at
                or record.available_at != revision.occurred_at
            ):
                raise IntelligenceBuilderSessionError("persisted onboarding envelope crossed exact session material")
            revisions.append(revision)
        if not revisions:
            return None
        revisions.sort(key=lambda item: item.sequence)
        if tuple(item.sequence for item in revisions) != tuple(range(1, len(revisions) + 1)):
            raise IntelligenceBuilderSessionError("onboarding session history is forked or has a sequence gap")
        first = revisions[0]
        for previous, current in zip(revisions[:-1], revisions[1:], strict=True):
            if (
                current.product_id != first.product_id
                or current.session_id != first.session_id
                or current.correlation_id != first.correlation_id
                or current.goal_ref != first.goal_ref
                or current.prior_revision_id != previous.revision_id
                or current.prior_revision_digest != previous.revision_digest
                or current.occurred_at < previous.occurred_at
            ):
                raise IntelligenceBuilderSessionError("onboarding session history lost exact chain continuity")
        return revisions[-1]

    async def start(
        self,
        *,
        product_id: str,
        correlation_id: str,
        goal_ref: str,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceBuilderSessionAdmission:
        session_id = f"intelligence_builder_session:{canonical_hash([product_id, correlation_id, goal_ref])[:32]}"
        revision = IntelligenceBuilderSessionRevisionV1(
            product_id=product_id,
            session_id=session_id,
            correlation_id=correlation_id,
            goal_ref=goal_ref,
            sequence=1,
            stage=OnboardingStage.GOAL_SELECTED,
            transition_authority=OnboardingTransitionAuthority.PRODUCT_INPUT,
            transition_actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
        return await self._persist(revision)

    async def advance(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        stage: OnboardingStage,
        authority: OnboardingTransitionAuthority,
        actor_ref: str,
        occurred_at: datetime,
        artifacts: tuple[OnboardingArtifactReferenceV1, ...] | None = None,
        approval_receipt_ref: str | None = None,
    ) -> IntelligenceBuilderSessionAdmission:
        validated = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        latest = await self.load_latest(
            product_id=validated.product_id,
            session_id=validated.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != validated.revision_id:
            raise IntelligenceBuilderSessionReplayConflict("onboarding transition started from a stale session revision")
        required = _PRIMARY_TRANSITIONS.get((validated.stage, stage))
        if required is None or required is not authority:
            raise IntelligenceBuilderSessionError(
                f"onboarding transition {validated.stage.value}->{stage.value} requires a different boundary"
            )
        next_revision = IntelligenceBuilderSessionRevisionV1(
            product_id=validated.product_id,
            session_id=validated.session_id,
            correlation_id=validated.correlation_id,
            goal_ref=validated.goal_ref,
            sequence=validated.sequence + 1,
            stage=stage,
            prior_revision_id=validated.revision_id,
            prior_revision_digest=validated.revision_digest,
            transition_authority=authority,
            transition_actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            artifacts=validated.artifacts if artifacts is None else artifacts,
            occurred_at=occurred_at,
        )
        return await self._persist(next_revision)

    async def block(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        reason: OnboardingBlockReason,
        actor_ref: str,
        safe_diagnostic: str,
        occurred_at: datetime,
    ) -> IntelligenceBuilderSessionAdmission:
        validated = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if validated.stage in {OnboardingStage.BLOCKED, OnboardingStage.RETRYING, OnboardingStage.ACTIVE}:
            raise IntelligenceBuilderSessionError("only a nonterminal primary stage can become blocked")
        latest = await self.load_latest(
            product_id=validated.product_id,
            session_id=validated.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != validated.revision_id:
            raise IntelligenceBuilderSessionReplayConflict("blocked transition started from a stale session revision")
        blocked = IntelligenceBuilderSessionRevisionV1(
            product_id=validated.product_id,
            session_id=validated.session_id,
            correlation_id=validated.correlation_id,
            goal_ref=validated.goal_ref,
            sequence=validated.sequence + 1,
            stage=OnboardingStage.BLOCKED,
            prior_revision_id=validated.revision_id,
            prior_revision_digest=validated.revision_digest,
            transition_authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            transition_actor_ref=actor_ref,
            artifacts=validated.artifacts,
            block_reason=reason,
            resume_stage=validated.stage,
            safe_diagnostic=safe_diagnostic,
            occurred_at=occurred_at,
        )
        return await self._persist(blocked)

    async def retry(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceBuilderSessionAdmission:
        validated = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if validated.stage is not OnboardingStage.BLOCKED:
            raise IntelligenceBuilderSessionError("only a blocked onboarding session can retry")
        latest = await self.load_latest(
            product_id=validated.product_id,
            session_id=validated.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != validated.revision_id:
            raise IntelligenceBuilderSessionReplayConflict("retry started from a stale session revision")
        retrying = IntelligenceBuilderSessionRevisionV1(
            product_id=validated.product_id,
            session_id=validated.session_id,
            correlation_id=validated.correlation_id,
            goal_ref=validated.goal_ref,
            sequence=validated.sequence + 1,
            stage=OnboardingStage.RETRYING,
            prior_revision_id=validated.revision_id,
            prior_revision_digest=validated.revision_digest,
            transition_authority=OnboardingTransitionAuthority.PRODUCT_INPUT,
            transition_actor_ref=actor_ref,
            artifacts=validated.artifacts,
            block_reason=validated.block_reason,
            resume_stage=validated.resume_stage,
            safe_diagnostic=validated.safe_diagnostic,
            occurred_at=occurred_at,
        )
        return await self._persist(retrying)

    async def resume(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        actor_ref: str,
        occurred_at: datetime,
    ) -> IntelligenceBuilderSessionAdmission:
        validated = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if validated.stage is not OnboardingStage.RETRYING or validated.resume_stage is None:
            raise IntelligenceBuilderSessionError("only a retrying onboarding session can resume")
        latest = await self.load_latest(
            product_id=validated.product_id,
            session_id=validated.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != validated.revision_id:
            raise IntelligenceBuilderSessionReplayConflict("resume started from a stale session revision")
        resumed = IntelligenceBuilderSessionRevisionV1(
            product_id=validated.product_id,
            session_id=validated.session_id,
            correlation_id=validated.correlation_id,
            goal_ref=validated.goal_ref,
            sequence=validated.sequence + 1,
            stage=validated.resume_stage,
            prior_revision_id=validated.revision_id,
            prior_revision_digest=validated.revision_digest,
            transition_authority=OnboardingTransitionAuthority.PRODUCT_INPUT,
            transition_actor_ref=actor_ref,
            artifacts=validated.artifacts,
            occurred_at=occurred_at,
        )
        return await self._persist(resumed)


class ConnectionAgent:
    """Propose and test exact source scope without owning connector effects."""

    def __init__(
        self,
        *,
        sessions: IntelligenceBuilderSessionService,
        authority: CoreAuthorityResolver,
        provider: RegisteredSourceOptionProvider,
    ) -> None:
        self.sessions = sessions
        self.authority = authority
        self.provider = provider

    async def discover(self) -> SourceOptionCatalogV1:
        try:
            raw = await self.provider.catalog()
            return SourceOptionCatalogV1.model_validate(raw.model_dump(mode="python"))
        except Exception:
            raise ConnectionAgentError("registered source option discovery failed closed") from None

    @staticmethod
    def _validate_selections(
        catalog: SourceOptionCatalogV1,
        selections: tuple[SourceScopeSelectionV1, ...],
    ) -> tuple[SourceScopeSelectionV1, ...]:
        try:
            exact = tuple(SourceScopeSelectionV1.model_validate(item.model_dump(mode="python")) for item in selections)
        except Exception:
            raise ConnectionAgentError("source scope selections failed exact validation") from None
        if not exact or len({item.option_id for item in exact}) != len(exact):
            raise ConnectionAgentError("source scope selections must be non-empty and unique")
        options = {item.option_id: item for item in catalog.options}
        for selection in exact:
            option = options.get(selection.option_id)
            if option is None:
                raise ConnectionAgentError("source scope proposal names an unavailable registered option")
            if not set(selection.permissions).issubset(option.permission_options):
                raise ConnectionAgentError("source scope proposal requests an unsupported permission")
            if not set(selection.scopes).issubset(option.scope_options):
                raise ConnectionAgentError("source scope proposal requests an unsupported scope")
            if not set(selection.effects).issubset(option.allowed_effects):
                raise ConnectionAgentError("source scope proposal requests a forbidden effect")
            if selection.sample_records > option.maximum_sample_records:
                raise ConnectionAgentError("source scope proposal exceeds the bounded sample limit")
        return tuple(sorted(exact, key=lambda item: item.option_id))

    async def propose_scope(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        catalog: SourceOptionCatalogV1,
        selections: tuple[SourceScopeSelectionV1, ...],
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConnectionScopeAdmission:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        if session.stage not in {OnboardingStage.GOAL_SELECTED, OnboardingStage.SOURCES_CONNECTING}:
            raise ConnectionAgentError("Connection Agent can propose scope only before sources are ready")
        exact_catalog = SourceOptionCatalogV1.model_validate(catalog.model_dump(mode="python"))
        current_catalog = await self.discover()
        if current_catalog.catalog_id != exact_catalog.catalog_id or current_catalog.catalog_digest != (
            exact_catalog.catalog_digest
        ):
            raise ConnectionAgentStaleProposal("source option catalog changed before scope proposal")
        exact_selections = self._validate_selections(exact_catalog, selections)
        proposal = SourceScopeProposalV1(
            session_id=session.session_id,
            goal_ref=session.goal_ref,
            catalog_id=str(exact_catalog.catalog_id),
            catalog_digest=str(exact_catalog.catalog_digest),
            selections=exact_selections,
            created_at=occurred_at,
        )
        proposal_admission = await self.sessions.persist_artifact(
            product_id=session.product_id,
            artifact=proposal,
        )
        artifact = _artifact(
            OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL,
            str(proposal.proposal_id),
            str(proposal.proposal_digest),
        )
        artifacts = _replace_artifact(
            session.artifacts,
            artifact,
            remove=(OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL,),
        )
        admission = await self.sessions.advance(
            session,
            stage=OnboardingStage.SOURCES_CONNECTING,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return ConnectionScopeAdmission(
            proposal=proposal,
            proposal_admission=proposal_admission,
            session=admission,
        )

    @staticmethod
    def _current_scope_artifact(
        session: IntelligenceBuilderSessionRevisionV1,
    ) -> OnboardingArtifactReferenceV1 | None:
        return next(
            (
                item
                for item in session.artifacts
                if item.artifact_kind is OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL
            ),
            None,
        )

    @staticmethod
    def _validate_approval(
        approval: ResolvedApprovalReceiptV1,
        *,
        proposal: SourceScopeProposalV1,
        product_id: str,
        actor_ref: str,
        approval_receipt_ref: str,
        occurred_at: datetime,
    ) -> None:
        if (
            approval.receipt_ref != approval_receipt_ref
            or approval.product_id != product_id
            or approval.subject_ref != proposal.proposal_id
            or approval.actor_ref != actor_ref
            or approval.approved_at > occurred_at
        ):
            raise ConnectionAgentScopeViolation("approval does not bind the exact current source scope")

    @staticmethod
    def _validate_samples(
        *,
        catalog: SourceOptionCatalogV1,
        proposal: SourceScopeProposalV1,
        samples: tuple[SourceSampleV1, ...],
    ) -> tuple[SourceSampleV1, ...]:
        try:
            exact = tuple(SourceSampleV1.model_validate(item.model_dump(mode="python")) for item in samples)
        except Exception:
            raise ConnectionAgentScopeViolation("source provider returned invalid or forbidden sample material") from None
        selections = {item.option_id: item for item in proposal.selections}
        options = {item.option_id: item for item in catalog.options}
        if set(item.option_id for item in exact) != set(selections) or len(exact) != len(selections):
            raise ConnectionAgentScopeViolation("source provider did not return one exact approved sample per option")
        for sample in exact:
            selection = selections[sample.option_id]
            option = options[sample.option_id]
            if (
                sample.connector_ref != option.connector_ref
                or sample.connector_digest != option.connector_digest
                or sample.source_ref != option.source_ref
                or sample.scope_proposal_id != proposal.proposal_id
                or sample.scope_proposal_digest != proposal.proposal_digest
                or sample.permissions != selection.permissions
                or sample.scopes != selection.scopes
                or sample.effects_performed != selection.effects
                or sample.sample_records > selection.sample_records
                or ConnectionEffect.BOUNDED_SAMPLE not in sample.effects_performed
            ):
                raise ConnectionAgentScopeViolation("source provider widened or changed the approved source scope")
        return tuple(sorted(exact, key=lambda item: item.option_id))

    async def _blocked(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
        *,
        reason: OnboardingBlockReason,
        diagnostic: str,
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConnectionAgentOutcome:
        admission = await self.sessions.block(
            session,
            reason=reason,
            actor_ref=actor_ref,
            safe_diagnostic=diagnostic,
            occurred_at=occurred_at,
        )
        return ConnectionAgentOutcome(
            session=admission,
            profile=None,
            profile_admission=None,
            blocked_reason=reason,
        )

    async def connect(
        self,
        current: IntelligenceBuilderSessionRevisionV1,
        *,
        proposal: SourceScopeProposalV1,
        approval_receipt_ref: str,
        actor_ref: str,
        occurred_at: datetime,
    ) -> ConnectionAgentOutcome:
        session = IntelligenceBuilderSessionRevisionV1.model_validate(current.model_dump(mode="python"))
        scope = SourceScopeProposalV1.model_validate(proposal.model_dump(mode="python"))
        if session.stage is not OnboardingStage.SOURCES_CONNECTING:
            raise ConnectionAgentError("Connection Agent can connect only from sources_connecting")
        artifact = self._current_scope_artifact(session)
        if (
            artifact is None
            or artifact.artifact_id != scope.proposal_id
            or artifact.artifact_digest != scope.proposal_digest
            or scope.session_id != session.session_id
            or scope.goal_ref != session.goal_ref
        ):
            raise ConnectionAgentStaleProposal("source scope proposal is not the current session handoff")
        persisted_scope = await self.sessions.load_artifact(
            product_id=session.product_id,
            reference=artifact,
            artifact_type=SourceScopeProposalV1,
            available_at=occurred_at,
        )
        if persisted_scope != scope:
            raise ConnectionAgentStaleProposal("source scope proposal differs from exact durable handoff")
        latest = await self.sessions.load_latest(
            product_id=session.product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
        if latest is None or latest.revision_id != session.revision_id:
            raise ConnectionAgentStaleProposal("source scope proposal belongs to a stale session revision")
        catalog = await self.discover()
        if catalog.catalog_id != scope.catalog_id or catalog.catalog_digest != scope.catalog_digest:
            raise ConnectionAgentStaleProposal("source option catalog changed before approved access")

        try:
            raw_approval = await self.authority.resolve_approval(
                receipt_ref=approval_receipt_ref,
                product_id=session.product_id,
                subject_ref=str(scope.proposal_id),
                actor_ref=actor_ref,
                effective_at=occurred_at,
            )
            approval = ResolvedApprovalReceiptV1.model_validate(raw_approval.model_dump(mode="python"))
            self._validate_approval(
                approval,
                proposal=scope,
                product_id=session.product_id,
                actor_ref=actor_ref,
                approval_receipt_ref=approval_receipt_ref,
                occurred_at=occurred_at,
            )
        except Exception:
            return await self._blocked(
                session,
                reason=OnboardingBlockReason.INSUFFICIENT_PERMISSION,
                diagnostic="source access was not approved for the exact current scope",
                actor_ref="agent:connection",
                occurred_at=occurred_at,
            )

        try:
            raw_samples = await self.provider.test_and_sample(scope)
        except Exception:
            return await self._blocked(
                session,
                reason=OnboardingBlockReason.FAILED_CONNECTOR,
                diagnostic="registered connector could not complete the approved bounded test and sample",
                actor_ref="agent:connection",
                occurred_at=occurred_at,
            )
        try:
            samples = self._validate_samples(catalog=catalog, proposal=scope, samples=raw_samples)
        except ConnectionAgentScopeViolation:
            return await self._blocked(
                session,
                reason=OnboardingBlockReason.INSUFFICIENT_PERMISSION,
                diagnostic="connector result changed or widened the approved source scope",
                actor_ref="agent:connection",
                occurred_at=occurred_at,
            )

        profile = SourceProfileProposalV1(
            session_id=session.session_id,
            scope_proposal_id=str(scope.proposal_id),
            scope_proposal_digest=str(scope.proposal_digest),
            samples=samples,
            limitations=(
                "bounded_shape_sample_only",
                "no_authoritative_connector_configuration_persisted",
            ),
            created_at=occurred_at,
        )
        profile_admission = await self.sessions.persist_artifact(
            product_id=session.product_id,
            artifact=profile,
        )
        profile_artifact = _artifact(
            OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL,
            str(profile.proposal_id),
            str(profile.proposal_digest),
        )
        artifacts = _replace_artifact(session.artifacts, profile_artifact)
        admission = await self.sessions.advance(
            session,
            stage=OnboardingStage.SOURCES_READY,
            authority=OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            actor_ref=actor_ref,
            approval_receipt_ref=approval_receipt_ref,
            occurred_at=occurred_at,
            artifacts=artifacts,
        )
        return ConnectionAgentOutcome(
            session=admission,
            profile=profile,
            profile_admission=profile_admission,
            blocked_reason=None,
        )


__all__ = [
    "ConnectionAgent",
    "ConnectionAgentError",
    "ConnectionAgentOutcome",
    "ConnectionAgentScopeViolation",
    "ConnectionAgentStaleProposal",
    "ConnectionScopeAdmission",
    "INTELLIGENCE_BUILDER_RECORD_SPACE",
    "IntelligenceBuilderArtifactAdmission",
    "IntelligenceBuilderSessionAdmission",
    "IntelligenceBuilderSessionError",
    "IntelligenceBuilderSessionReplayConflict",
    "IntelligenceBuilderSessionService",
    "ONBOARDING_SESSION_REVISION_RECORD_KIND",
    "ONBOARDING_ARTIFACT_RECORD_KIND",
    "RegisteredSourceOptionProvider",
]
