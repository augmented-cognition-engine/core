"""Production coordinator: bridge the Builder's exact ``SOURCES_READY`` handoff
into the Ontology Agent's concept-model proposal and its separate exact
reviewed approval (PI13 addendum 9).

Per the frozen Builder-session progression addendum, concept-model proposal
and concept-model approval stay two explicit, bounded steps:

* **Proposal** reopens the exact current ``SOURCES_READY`` session and the
  exact current ``SourceProfileProposalV1`` handoff, then calls the existing
  ``OntologyAgent.propose`` (via ``SelectedConceptModelStrategy``) with the
  fixed transition actor ``agent:ontology``. This coordinator never calls
  ``sessions.advance``/``persist`` directly -- that stays the Agent port's
  job.
* **Approval** first records its own separate exact reviewed receipt through
  the existing ``approve_builder_concept_model`` (from
  ``intelligence_builder_disposition_authority``), then calls the existing
  ``OntologyAgent.approve`` with the recorded resolver and the fixed local
  owner actor. No grant is minted here; grant resolution delegates to the
  injected existing resolver only.

Both operations fail closed on stale/crossed session or proposal material,
selected-provider unavailable/conflict, agent blocking/low confidence,
approval mismatch, or persistence races -- and an identical retry of either
operation reopens the single durable outcome already produced without
calling the provider, ``approve_builder_concept_model``, or
``OntologyAgent.approve`` again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ace.application.intelligence_builder import (
    IntelligenceBuilderArtifactNotFoundError,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceProfileProposalV1,
)
from ace.application.ontology_agent import (
    ConceptModelApprovalAdmission,
    ConceptModelProposalAdmission,
    OntologyAgent,
    OntologyAgentAttributionError,
    OntologyAgentError,
    OntologyAgentStaleProposal,
)
from ace.application.ontology_agent_contracts import (
    ConceptModelDispositionV1,
    ConceptModelProposalV1,
    OrganizationTerminologyV1,
)
from ace.core.contracts import canonical_hash
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1, ResolvedAuthorityGrantV1
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    RecordedIntelligenceActivationAuthority,
    verified_local_intelligence_owner,
)
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderDispositionApprovalError,
    BuilderDispositionApprovalResultV1Alpha1,
    BuilderDispositionApprovalUnavailable,
    RecordedIntelligenceBuilderDispositionAuthority,
    approve_builder_concept_model,
)
from core.engine.core.intelligence_builder_strategies import SelectedConceptModelStrategy
from core.engine.core.llm import get_llm

# The Ontology Agent's own transition actor for its exact ``AGENT_PROPOSAL``
# handoff (PI13 addendum 9); the local owner is only ever the approving actor.
ONTOLOGY_AGENT_ACTOR_REF = "agent:ontology"

CONCEPT_MODEL_PROPOSAL_INTENT_VERSION = "ace.host.concept-model-proposal-intent/v1alpha1"

_PROPOSAL_INTENT_RECORD_SPACE = "intelligence_builder_concept_model_proposal_intent"
_PROPOSAL_INTENT_RECORD_KIND = "concept_model_proposal_intent"


# Host-local exact digest syntax. Mirrors the public contracts' ``sha256:<64-hex>``
# rule without reaching into the ``ace.intelligence`` bounded context.
_SHA256_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


def _validate_digest(value: str) -> str:
    if not _SHA256_DIGEST.fullmatch(value):
        raise ValueError("digest must use lowercase sha256:<64-hex> syntax")
    return value


class IntelligenceBuilderConceptProgressionError(RuntimeError):
    """Base failure bridging one exact SOURCES_READY handoff to the Ontology Agent."""


class IntelligenceBuilderConceptProgressionDenied(IntelligenceBuilderConceptProgressionError):
    """The verified caller cannot progress this exact concept-model handoff."""


class IntelligenceBuilderConceptProgressionConflict(IntelligenceBuilderConceptProgressionError):
    """Submitted or durable material crossed or changed exact reviewed bindings."""


class IntelligenceBuilderConceptProgressionUnavailable(IntelligenceBuilderConceptProgressionError):
    """A required durable store or selected provider could not be reached right now."""


def _verified_owner(user: dict) -> tuple[str, str]:
    try:
        return verified_local_intelligence_owner(user)
    except Exception as exc:
        raise IntelligenceBuilderConceptProgressionDenied(
            "verified caller is not the local Intelligence owner"
        ) from exc


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class ConceptModelProposeRequestV1Alpha1(BaseModel):
    """One explicit request to propose the concept model from the exact current
    ``SOURCES_READY`` handoff."""

    model_config = ConfigDict(extra="forbid")

    current: IntelligenceBuilderSessionRevisionV1
    source_profile: SourceProfileProposalV1
    user_intent: str = Field(min_length=1, max_length=2_000)
    organization_terminology: tuple[OrganizationTerminologyV1, ...] = ()
    proposed_at: datetime

    @field_validator("current", "source_profile", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = IntelligenceBuilderSessionRevisionV1 if info.field_name == "current" else SourceProfileProposalV1
            return model.model_validate(value, strict=False)
        return value

    @field_validator("proposed_at")
    @classmethod
    def _proposed_time(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")


class ConceptModelApprovalResultV1Alpha1(BaseModel):
    """The separate exact reviewed receipt plus the Ontology Agent's own approval admission."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    reviewed_approval: BuilderDispositionApprovalResultV1Alpha1
    approval: ConceptModelApprovalAdmission


class _ConceptModelProposalIntentV1Alpha1(BaseModel):
    """Append-only exclusive intent to propose a concept model from one exact prior revision.

    Keyed exclusively by ``(product_id, session_id, prior_revision_id,
    prior_revision_digest)`` -- never by request content -- so that this
    record itself is the exclusivity lock: only one request per prior
    revision can ever have its intent durably admitted. It is persisted
    *before* the selected provider is ever called, and it never carries any
    provider-authored outcome (no proposal id/digest, no resulting session
    revision), since none of that is known yet at intent-persist time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.concept-model-proposal-intent/v1alpha1"] = CONCEPT_MODEL_PROPOSAL_INTENT_VERSION
    product_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    prior_revision_id: str = Field(min_length=1, max_length=240)
    prior_revision_digest: str = Field(min_length=1, max_length=240)
    source_profile_proposal_id: str = Field(min_length=1, max_length=240)
    source_profile_proposal_digest: str = Field(min_length=1, max_length=240)
    user_intent: str = Field(min_length=1, max_length=2_000)
    organization_terminology_digest: str = Field(min_length=1, max_length=240)
    proposed_at: datetime

    @field_validator("organization_terminology_digest")
    @classmethod
    def _validate_organization_terminology_digest(cls, value: str) -> str:
        return _validate_digest(value)


@dataclass(frozen=True, slots=True)
class IntelligenceBuilderConceptProgressionRuntime:
    """Production wiring for the Builder-to-Ontology-Agent concept progression."""

    records: ImmutableRecordStore
    grants: CoreAuthorityResolver
    provider: object | None = None
    provider_factory: Callable[[], object] = get_llm
    model: str | None = None
    max_tokens: int = 4096


def intelligence_builder_concept_progression_runtime() -> IntelligenceBuilderConceptProgressionRuntime:
    """Build the production runtime over the primary durable stores and selected provider."""

    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceBuilderConceptProgressionRuntime(
        records=records,
        grants=RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_state),
    )


class _UnreachablePropositionAuthority(CoreAuthorityResolver):
    """Authority stand-in for concept proposal; ``propose`` never resolves approval or grants."""

    async def resolve_approval(self, **kwargs) -> ResolvedApprovalReceiptV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: concept-model proposal never resolves approval or grant evidence")

    async def resolve_grant(self, **kwargs) -> ResolvedAuthorityGrantV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: concept-model proposal never resolves approval or grant evidence")


_UNREACHABLE_PROPOSAL_AUTHORITY = _UnreachablePropositionAuthority()


class _UnreachableConceptModelStrategy:
    """Strategy stand-in for concept approval; ``approve`` never proposes a new concept model."""

    async def propose(self, **kwargs):  # pragma: no cover - unreachable
        raise AssertionError("unreachable: concept-model approval never proposes a new concept model")


_UNREACHABLE_STRATEGY = _UnreachableConceptModelStrategy()


def _proposal_intent_key(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
) -> str:
    """Return the exclusive intent key for one prior SOURCES_READY revision.

    Deliberately derived only from ``(product_id, session_id,
    prior_revision_id, prior_revision_digest)`` -- never from request
    content -- so the key itself acts as an exclusivity lock: any two
    requests against the same prior revision collide on the same key,
    regardless of differing ``proposed_at``/``user_intent``/terminology.
    """

    material = {
        "product_id": product_id,
        "session_id": session.session_id,
        "prior_revision_id": session.revision_id,
        "prior_revision_digest": session.revision_digest,
    }
    digest = canonical_hash(material)
    return f"concept-proposal-intent:{digest[:32]}"


def _organization_terminology_digest(organization_terminology: tuple[OrganizationTerminologyV1, ...]) -> str:
    digest = canonical_hash([item.model_dump(mode="json") for item in organization_terminology])
    return f"sha256:{digest}"


def _build_proposal_intent(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
    request: ConceptModelProposeRequestV1Alpha1,
) -> _ConceptModelProposalIntentV1Alpha1:
    return _ConceptModelProposalIntentV1Alpha1(
        product_id=product_id,
        session_id=session.session_id,
        prior_revision_id=str(session.revision_id),
        prior_revision_digest=str(session.revision_digest),
        source_profile_proposal_id=str(request.source_profile.proposal_id),
        source_profile_proposal_digest=str(request.source_profile.proposal_digest),
        user_intent=request.user_intent,
        organization_terminology_digest=_organization_terminology_digest(request.organization_terminology),
        proposed_at=request.proposed_at,
    )


async def _persist_proposal_intent(
    *,
    records: ImmutableRecordStore,
    intent_key: str,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
    request: ConceptModelProposeRequestV1Alpha1,
) -> _ConceptModelProposalIntentV1Alpha1:
    """Persist the exclusive proposal intent before any provider call.

    On a replay conflict (a different intent already durably admitted for
    this exact same prior revision), the existing record is reloaded and
    compared field-by-field against what this call tried to persist. An
    exact match means this is a benign concurrent duplicate of the same
    request, and the already-admitted intent is returned instead. Any
    mismatch means a genuinely different request collided on the same
    prior revision, and it fails closed before ever calling the provider.
    """

    intent = _build_proposal_intent(product_id=product_id, session=session, request=request)
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        payload_contract=intent.contract,
        payload=intent.model_dump(mode="python"),
        as_of=request.proposed_at,
        available_at=request.proposed_at,
        processing_order=0,
    )
    txn = AppendOnlyTransactionRequestV1(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        transaction_key=intent_key,
        records=(record,),
        submitted_at=request.proposed_at,
    )
    try:
        receipt = await records.append(txn)
    except ImmutableRecordReplayConflict:
        return await _matching_existing_intent(
            records=records,
            intent_key=intent_key,
            product_id=product_id,
            intent=intent,
        )
    except Exception as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent could not be recorded"
        ) from exc
    if receipt != txn.receipt():
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent receipt does not match the exact append request"
        )
    return intent


async def _matching_existing_intent(
    *,
    records: ImmutableRecordStore,
    intent_key: str,
    product_id: str,
    intent: _ConceptModelProposalIntentV1Alpha1,
) -> _ConceptModelProposalIntentV1Alpha1:
    storage_id = immutable_record_storage_id(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
    )
    try:
        existing = await records.load_record(
            storage_id,
            product_id=product_id,
            record_space=_PROPOSAL_INTENT_RECORD_SPACE,
            record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        )
    except Exception as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent storage is unavailable"
        ) from exc
    if existing is None or existing.record_key != intent_key or existing.product_id != product_id:
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept-model proposal intent already recorded different exact material"
        )
    try:
        existing_intent = _ConceptModelProposalIntentV1Alpha1.model_validate(existing.payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent failed exact revalidation"
        ) from exc
    if existing_intent != intent:
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept-model proposal intent already recorded different exact material"
        )
    return existing_intent


async def _reconstruct_proposal_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    records: ImmutableRecordStore,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    product_id: str,
    request: ConceptModelProposeRequestV1Alpha1,
    occurred_at: datetime,
) -> ConceptModelProposalAdmission:
    """Reopen the already-durable exact one-step proposal outcome for a retry.

    Only reached when the current durable session revision proves this exact
    one-step transition already happened. It never calls the selected
    provider or ``OntologyAgent.propose`` again: it only verifies this exact
    retried request against the recorded exclusive intent, then reopens
    durable material directly from ``latest``'s own artifact reference via
    ``load_artifact``/``persist_artifact``'s own idempotent replay.
    """

    intent_key = _proposal_intent_key(product_id=product_id, session=session)
    storage_id = immutable_record_storage_id(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
    )
    try:
        record = await records.load_record(
            storage_id,
            product_id=product_id,
            record_space=_PROPOSAL_INTENT_RECORD_SPACE,
            record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        )
    except Exception as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent storage is unavailable"
        ) from exc
    if record is None:
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session advanced without any recorded proposal intent for this prior revision"
        )
    try:
        intent = _ConceptModelProposalIntentV1Alpha1.model_validate(record.payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model proposal intent failed exact revalidation"
        ) from exc
    if (
        record.product_id != product_id
        or record.record_key != intent_key
        or record.record_space != _PROPOSAL_INTENT_RECORD_SPACE
        or record.record_kind != _PROPOSAL_INTENT_RECORD_KIND
        or record.payload_contract != intent.contract
        or record.as_of != intent.proposed_at
        or record.available_at != intent.proposed_at
        or intent.product_id != product_id
        or intent.session_id != session.session_id
        or intent.prior_revision_id != session.revision_id
        or intent.prior_revision_digest != session.revision_digest
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept-model proposal intent does not match this exact prior revision"
        )
    if (
        intent.user_intent != request.user_intent
        or intent.source_profile_proposal_id != str(request.source_profile.proposal_id)
        or intent.source_profile_proposal_digest != str(request.source_profile.proposal_digest)
        or intent.organization_terminology_digest != _organization_terminology_digest(request.organization_terminology)
        or intent.proposed_at != request.proposed_at
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "a different request collided with the exact proposal intent already admitted for this prior revision"
        )

    reference = next(
        (item for item in latest.artifacts if item.artifact_kind is OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL),
        None,
    )
    if reference is None:
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session advanced past this proposal without a durable artifact reference"
        )
    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != ONTOLOGY_AGENT_ACTOR_REF
        or latest.product_id != product_id
        or latest.session_id != session.session_id
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable propose retry crossed its exact transition time, actor, or chain"
        )
    try:
        persisted_proposal = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise IntelligenceBuilderConceptProgressionConflict("proposal is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable("Builder artifact storage is unavailable") from exc
    try:
        session_admission = await sessions.reload_admission(latest)
        proposal_admission = await sessions.persist_artifact(product_id=product_id, artifact=persisted_proposal)
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable propose retry could not be exactly reopened"
        ) from exc
    return ConceptModelProposalAdmission(
        proposal=persisted_proposal,
        proposal_admission=proposal_admission,
        session=session_admission,
    )


async def propose_intelligence_builder_concept_model(
    *,
    request: ConceptModelProposeRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderConceptProgressionRuntime,
) -> ConceptModelProposalAdmission:
    """Propose the Ontology Agent's concept model from the exact current SOURCES_READY handoff.

    Reloads the exact current ``SOURCES_READY`` Builder session, verifies the
    fixed local owner, and calls ``OntologyAgent.propose`` through
    ``SelectedConceptModelStrategy`` with the fixed transition actor
    ``agent:ontology``. It never calls ``sessions.advance``/``persist``
    directly -- that stays the Agent port's job.
    """

    actor_ref, product_id = _verified_owner(user)
    session = request.current
    if session.product_id != product_id:
        raise IntelligenceBuilderConceptProgressionDenied("Builder session crossed verified local-owner scope")
    occurred_at = request.proposed_at

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise IntelligenceBuilderConceptProgressionConflict("Builder session is stale; reload before proposing")

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.CONCEPT_MODEL_PROPOSED
        and latest.transition_authority is OnboardingTransitionAuthority.AGENT_PROPOSAL
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_proposal_retry(
            sessions=sessions,
            records=runtime.records,
            latest=latest,
            session=session,
            product_id=product_id,
            request=request,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise IntelligenceBuilderConceptProgressionConflict("Builder session is stale; reload before proposing")
    if latest.stage is not OnboardingStage.SOURCES_READY:
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session is not at the exact stage to propose a concept model"
        )

    intent_key = _proposal_intent_key(product_id=product_id, session=session)
    await _persist_proposal_intent(
        records=runtime.records,
        intent_key=intent_key,
        product_id=product_id,
        session=session,
        request=request,
    )

    # Race recheck: another request may have admitted its own intent for this
    # same prior revision and already advanced the session between our
    # `load_latest` above and our intent admission just now. Reload and
    # verify the session is still exactly where we started before ever
    # calling the provider.
    try:
        recheck = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable("Builder session storage is unavailable") from exc
    if (
        recheck is None
        or recheck.revision_id != session.revision_id
        or recheck.revision_digest != session.revision_digest
        or recheck.stage is not OnboardingStage.SOURCES_READY
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session advanced past this proposal intent from a different exact request"
        )

    strategy = SelectedConceptModelStrategy(
        provider=runtime.provider,
        provider_factory=runtime.provider_factory,
        model=runtime.model,
        max_tokens=runtime.max_tokens,
    )
    agent = OntologyAgent(sessions=sessions, authority=_UNREACHABLE_PROPOSAL_AUTHORITY, strategy=strategy)

    try:
        outcome = await agent.propose(
            latest,
            source_profile=request.source_profile,
            user_intent=request.user_intent,
            organization_terminology=request.organization_terminology,
            actor_ref=ONTOLOGY_AGENT_ACTOR_REF,
            occurred_at=occurred_at,
        )
    except OntologyAgentAttributionError as exc:
        raise IntelligenceBuilderConceptProgressionConflict("concept proposal lost exact source attribution") from exc
    except OntologyAgentStaleProposal as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept proposal started from stale session or source-profile material"
        ) from exc
    except OntologyAgentError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model strategy failed before a safe proposal"
        ) from exc

    if outcome.proposal is None:
        raise IntelligenceBuilderConceptProgressionDenied(
            f"concept-model proposal was blocked: {outcome.blocked_reason}"
        )

    # The exclusive intent already durably exists (persisted before this
    # provider call), so it is sufficient -- together with the durable
    # session/artifact chain the agent itself just produced -- to reconstruct
    # this outcome on any later retry. No post-outcome binding is recorded.
    return outcome.proposal


async def _reconstruct_approval_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    authority: RecordedIntelligenceBuilderDispositionAuthority,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    proposal: ConceptModelProposalV1,
    actor_ref: str,
    occurred_at: datetime,
) -> ConceptModelApprovalResultV1Alpha1:
    """Reopen the already-durable exact one-step CONCEPT_MODEL_APPROVED outcome for a retry.

    Only reached when the current durable session revision proves this exact
    one-step transition already happened: its ``prior_revision`` fields match
    ``session`` exactly, its stage is ``CONCEPT_MODEL_APPROVED``, and it
    carries a bound approval receipt. It never calls
    ``approve_builder_concept_model`` or ``OntologyAgent.approve`` again and
    never resolves or mints another approval receipt.
    """

    if latest.approval_receipt_ref is None:
        raise IntelligenceBuilderConceptProgressionConflict("durable approval retry lost its exact approval receipt")

    exact_proposal = ConceptModelProposalV1.model_validate(proposal.model_dump(mode="python"))
    proposal_reference = next(
        (item for item in session.artifacts if item.artifact_kind is OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL),
        None,
    )
    if (
        proposal_reference is None
        or proposal_reference.artifact_id != exact_proposal.proposal_id
        or proposal_reference.artifact_digest != exact_proposal.proposal_digest
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "supplied concept-model proposal is not the exact current session handoff"
        )
    try:
        persisted_proposal = await sessions.load_artifact(
            product_id=session.product_id,
            reference=proposal_reference,
            artifact_type=ConceptModelProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable concept-model proposal could not be exactly reopened"
        ) from exc
    if persisted_proposal != exact_proposal:
        raise IntelligenceBuilderConceptProgressionConflict(
            "supplied concept-model proposal differs from the exact durable handoff"
        )

    disposition_reference = next(
        (item for item in latest.artifacts if item.artifact_kind is OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION),
        None,
    )
    if disposition_reference is None:
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session advanced to concept_model_approved without a durable disposition"
        )
    try:
        disposition = await sessions.load_artifact(
            product_id=session.product_id,
            reference=disposition_reference,
            artifact_type=ConceptModelDispositionV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable concept-model disposition could not be exactly reopened"
        ) from exc
    if (
        disposition.session_id != session.session_id
        or disposition.proposal_id != str(exact_proposal.proposal_id)
        or disposition.proposal_digest != str(exact_proposal.proposal_digest)
        or disposition.actor_ref != actor_ref
        or disposition.approval_receipt_ref != latest.approval_receipt_ref
        or disposition.approved_at != occurred_at
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable concept-model disposition does not match this exact retried approval"
        )

    try:
        resolved = await authority.resolve_approval(
            receipt_ref=latest.approval_receipt_ref,
            product_id=session.product_id,
            subject_ref=str(exact_proposal.proposal_id),
            actor_ref=actor_ref,
            effective_at=occurred_at,
        )
    except Exception as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable reviewed concept-model approval could not be exactly reopened"
        ) from exc
    if (
        resolved.receipt_ref != latest.approval_receipt_ref
        or resolved.product_id != session.product_id
        or resolved.subject_ref != exact_proposal.proposal_id
        or resolved.actor_ref != actor_ref
        or resolved.approved_at != occurred_at
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable reviewed concept-model approval does not match this exact retried approval"
        )
    reviewed = BuilderDispositionApprovalResultV1Alpha1(
        approval=resolved,
        session_revision_id=str(session.revision_id),
        session_revision_digest=str(session.revision_digest),
        proposal_id=str(exact_proposal.proposal_id),
        proposal_digest=str(exact_proposal.proposal_digest),
    )

    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != actor_ref
        or latest.product_id != session.product_id
        or latest.session_id != session.session_id
    ):
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable approval retry crossed its exact transition time, actor, or chain"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        disposition_admission = await sessions.persist_artifact(product_id=session.product_id, artifact=disposition)
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "durable approval retry could not be exactly reopened"
        ) from exc

    approval = ConceptModelApprovalAdmission(
        proposal=exact_proposal,
        disposition=disposition,
        disposition_admission=disposition_admission,
        session=session_admission,
    )
    return ConceptModelApprovalResultV1Alpha1(reviewed_approval=reviewed, approval=approval)


async def approve_intelligence_builder_concept_model(
    *,
    request: BuilderConceptModelApproveRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderConceptProgressionRuntime,
) -> ConceptModelApprovalResultV1Alpha1:
    """Approve the exact current CONCEPT_MODEL_PROPOSED concept model.

    First records a separate exact reviewed receipt through the existing
    ``approve_builder_concept_model``, then calls the existing
    ``OntologyAgent.approve`` with ``RecordedIntelligenceBuilderDispositionAuthority``
    and the fixed local-owner actor. Only ``decision='approve'`` is
    supported; this coordinator never fabricates or bundles any other
    approval, and never mints a grant of its own.
    """

    actor_ref, product_id = _verified_owner(user)
    session = request.current
    if session.product_id != product_id:
        raise IntelligenceBuilderConceptProgressionDenied("Builder session crossed verified local-owner scope")
    occurred_at = request.approved_at

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise IntelligenceBuilderConceptProgressionConflict("Builder session is stale; reload before approving")

    authority = RecordedIntelligenceBuilderDispositionAuthority(records=runtime.records, grants=runtime.grants)

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.CONCEPT_MODEL_APPROVED
        and latest.transition_authority is OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_approval_retry(
            sessions=sessions,
            authority=authority,
            latest=latest,
            session=session,
            proposal=request.proposal,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise IntelligenceBuilderConceptProgressionConflict("Builder session is stale; reload before approving")
    if latest.stage is not OnboardingStage.CONCEPT_MODEL_PROPOSED:
        raise IntelligenceBuilderConceptProgressionConflict(
            "Builder session is not at the exact stage for concept-model approval"
        )

    try:
        reviewed = await approve_builder_concept_model(request=request, user=user, records=runtime.records)
    except BuilderDispositionApprovalUnavailable as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model reviewed approval storage is unavailable"
        ) from exc
    except BuilderDispositionApprovalError as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept-model reviewed approval could not be exactly recorded"
        ) from exc

    agent = OntologyAgent(sessions=sessions, authority=authority, strategy=_UNREACHABLE_STRATEGY)
    try:
        approval = await agent.approve(
            latest,
            proposal=request.proposal,
            approval_receipt_ref=reviewed.approval.receipt_ref,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
    except OntologyAgentStaleProposal as exc:
        raise IntelligenceBuilderConceptProgressionConflict(
            "concept-model approval started from stale session or proposal material"
        ) from exc
    except OntologyAgentError as exc:
        raise IntelligenceBuilderConceptProgressionUnavailable(
            "concept-model approval failed exact Core resolution"
        ) from exc

    return ConceptModelApprovalResultV1Alpha1(reviewed_approval=reviewed, approval=approval)


__all__ = [
    "CONCEPT_MODEL_PROPOSAL_INTENT_VERSION",
    "ONTOLOGY_AGENT_ACTOR_REF",
    "ConceptModelApprovalResultV1Alpha1",
    "ConceptModelProposeRequestV1Alpha1",
    "IntelligenceBuilderConceptProgressionConflict",
    "IntelligenceBuilderConceptProgressionDenied",
    "IntelligenceBuilderConceptProgressionError",
    "IntelligenceBuilderConceptProgressionRuntime",
    "IntelligenceBuilderConceptProgressionUnavailable",
    "approve_intelligence_builder_concept_model",
    "intelligence_builder_concept_progression_runtime",
    "propose_intelligence_builder_concept_model",
]
