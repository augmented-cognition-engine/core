"""Production coordinator: bridge the Builder's exact ``CONCEPT_MODEL_APPROVED``
handoff into the Intelligence Agent's model propose/approve and the Briefing
Agent's first-Brief preparation (PI13 addendum 9).

Per the frozen Builder-session progression addendum, the intelligence-model
proposal and its separate exact reviewed approval stay two explicit, bounded
steps, followed by a separate first-Brief preparation step with no
approval of its own:

* **Proposal** reopens the exact current ``CONCEPT_MODEL_APPROVED`` session,
  derives/reopens the ``AuthorizedObservationSetV1`` through the existing
  ``admit_local_source_observations`` host adapter (never rereading sources
  directly), then calls the existing ``IntelligenceAgent.propose`` (via
  ``SelectedIntelligenceModelStrategy``) with the fixed transition actor
  ``agent:intelligence``. This coordinator never calls
  ``sessions.advance``/``persist`` directly -- that stays the Agent port's
  job.
* **Approval** first records its own separate exact reviewed receipt through
  the existing ``approve_builder_intelligence_model`` (from
  ``intelligence_builder_disposition_authority``), then calls the existing
  ``IntelligenceAgent.approve`` with the recorded resolver and the fixed
  local owner actor. No grant is minted here; grant resolution delegates to
  the injected existing resolver only.
* **First-Brief preparation** reopens the exact current
  ``INTELLIGENCE_MODEL_APPROVED`` session and calls the existing
  ``BriefingAgent.create_first_brief`` (via ``SelectedBriefingStrategy``)
  with the fixed transition actor ``agent:briefing``. There is no separate
  Brief approval; this step never fabricates or bundles one.

Every operation fails closed on stale/crossed session or proposal material,
selected-provider unavailable/conflict, agent blocking/low confidence,
attribution failure, approval mismatch, or persistence races -- and an
identical retry of any operation reopens the single durable outcome already
produced without calling the provider, ``admit_local_source_observations``,
``approve_builder_intelligence_model``, or the relevant Agent method again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ace.application.briefing_agent import (
    BriefingAgent,
    BriefingAgentAttributionError,
    BriefingAgentError,
    BriefingAgentStaleInput,
    FirstBriefingAdmission,
)
from ace.application.briefing_agent_contracts import FirstBriefingPreviewV1
from ace.application.intelligence_agent import (
    IntelligenceAgent,
    IntelligenceAgentAttributionError,
    IntelligenceAgentError,
    IntelligenceAgentStaleInput,
    IntelligenceModelApprovalAdmission,
    IntelligenceModelProposalAdmission,
)
from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
    ProposedCadence,
)
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
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
)
from ace.application.ontology_agent_contracts import ConceptModelDispositionV1, ConceptModelProposalV1
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
    BuilderDispositionApprovalError,
    BuilderDispositionApprovalResultV1Alpha1,
    BuilderDispositionApprovalUnavailable,
    BuilderIntelligenceModelApproveRequestV1Alpha1,
    RecordedIntelligenceBuilderDispositionAuthority,
    approve_builder_intelligence_model,
)
from core.engine.core.intelligence_builder_observation_admission import (
    ObservationAdmissionBoundError,
    ObservationAdmissionClosureError,
    ObservationAdmissionDenied,
    ObservationAdmissionError,
    ObservationAdmissionStaleInput,
    ObservationAdmissionUnavailable,
    admit_local_source_observations,
)
from core.engine.core.intelligence_builder_strategies import SelectedBriefingStrategy, SelectedIntelligenceModelStrategy
from core.engine.core.llm import get_llm
from core.engine.core.local_source_connect import (
    LocalSourceConnectRecordConflict,
    LocalSourceConnectRecordRepository,
    LocalSourceConnectRecordUnavailable,
)

# The Intelligence Agent's and Briefing Agent's own transition actors for
# their exact ``AGENT_PROPOSAL`` handoffs (PI13 addendum 9); the local owner
# is only ever the approving actor.
INTELLIGENCE_AGENT_ACTOR_REF = "agent:intelligence"
BRIEFING_AGENT_ACTOR_REF = "agent:briefing"

INTELLIGENCE_MODEL_PROPOSAL_INTENT_VERSION = "ace.host.intelligence-model-proposal-intent/v1alpha1"
FIRST_BRIEFING_INTENT_VERSION = "ace.host.first-briefing-intent/v1alpha1"

_PROPOSAL_INTENT_RECORD_SPACE = "intelligence_builder_intelligence_model_proposal_intent"
_PROPOSAL_INTENT_RECORD_KIND = "intelligence_model_proposal_intent"

_BRIEF_INTENT_RECORD_SPACE = "intelligence_builder_first_briefing_intent"
_BRIEF_INTENT_RECORD_KIND = "first_briefing_intent"


# Host-local exact identity syntax. Mirrors the public contracts' bounded
# reference and ``sha256:<64-hex>`` digest rules without reaching into the
# ``ace.intelligence`` bounded context.
_STABLE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SHA256_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


def _validate_reference(value: str) -> str:
    if not _STABLE_REFERENCE.fullmatch(value):
        raise ValueError("reference must be a bounded stable reference")
    return value


def _validate_digest(value: str) -> str:
    if not _SHA256_DIGEST.fullmatch(value):
        raise ValueError("digest must use lowercase sha256:<64-hex> syntax")
    return value


class IntelligenceBuilderIntelligenceProgressionError(RuntimeError):
    """Base failure bridging one exact CONCEPT_MODEL_APPROVED handoff onward."""


class IntelligenceBuilderIntelligenceProgressionDenied(IntelligenceBuilderIntelligenceProgressionError):
    """The verified caller cannot progress this exact handoff."""


class IntelligenceBuilderIntelligenceProgressionConflict(IntelligenceBuilderIntelligenceProgressionError):
    """Submitted or durable material crossed or changed exact reviewed bindings."""


class IntelligenceBuilderIntelligenceProgressionUnavailable(IntelligenceBuilderIntelligenceProgressionError):
    """A required durable store or selected provider could not be reached right now."""


def _verified_owner(user: dict) -> tuple[str, str]:
    try:
        return verified_local_intelligence_owner(user)
    except Exception as exc:
        raise IntelligenceBuilderIntelligenceProgressionDenied(
            "verified caller is not the local Intelligence owner"
        ) from exc


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _digest_of(values) -> str:
    digest = canonical_hash(list(values))
    return f"sha256:{digest}"


def _cadence_digest(values: tuple[ProposedCadence, ...]) -> str:
    digest = canonical_hash([item.value for item in values])
    return f"sha256:{digest}"


class IntelligenceModelProposeRequestV1Alpha1(BaseModel):
    """One explicit request to propose the intelligence model from the exact
    current ``CONCEPT_MODEL_APPROVED`` handoff."""

    model_config = ConfigDict(extra="forbid")

    current: IntelligenceBuilderSessionRevisionV1
    connect_request: LocalSourceConnectAuthorizationRequest
    connect_result: LocalSourceConnectAuthorizationResult
    source_profile: SourceProfileProposalV1
    concept_model: ConceptModelProposalV1
    concept_disposition: ConceptModelDispositionV1
    user_intent: str = Field(min_length=1, max_length=2_000)
    audience_constraints: tuple[str, ...] = ()
    cadence_constraints: tuple[ProposedCadence, ...] = ()
    proposed_at: datetime

    @field_validator(
        "current",
        "connect_request",
        "connect_result",
        "source_profile",
        "concept_model",
        "concept_disposition",
        mode="before",
    )
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = {
                "current": IntelligenceBuilderSessionRevisionV1,
                "connect_request": LocalSourceConnectAuthorizationRequest,
                "connect_result": LocalSourceConnectAuthorizationResult,
                "source_profile": SourceProfileProposalV1,
                "concept_model": ConceptModelProposalV1,
                "concept_disposition": ConceptModelDispositionV1,
            }[info.field_name]
            return model.model_validate(value, strict=False)
        return value

    @field_validator("proposed_at")
    @classmethod
    def _proposed_time(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @field_validator("audience_constraints", mode="before")
    @classmethod
    def _validate_audience_constraints(cls, value):
        if not isinstance(value, (list, tuple)):
            raise ValueError("audience_constraints must be an ordered collection")
        if len(value) > 64:
            raise ValueError("audience_constraints exceed the 64-item bound")
        result = tuple(value)
        for item in result:
            if not isinstance(item, str) or not item or len(item) > 240 or item != item.strip():
                raise ValueError("audience_constraints must be non-empty, trimmed, and at most 240 characters")
        if len(set(result)) != len(result):
            raise ValueError("audience_constraints must be unique")
        return result

    @field_validator("cadence_constraints", mode="before")
    @classmethod
    def _validate_cadence_constraints_collection(cls, value):
        if not isinstance(value, (list, tuple)):
            raise ValueError("cadence_constraints must be an ordered collection")
        if len(value) > 4:
            raise ValueError("cadence_constraints exceed the 4-item bound")
        return tuple(value)

    @field_validator("cadence_constraints")
    @classmethod
    def _validate_cadence_constraints_unique(cls, value: tuple[ProposedCadence, ...]) -> tuple[ProposedCadence, ...]:
        if len(set(value)) != len(value):
            raise ValueError("cadence_constraints must be unique")
        return value


class IntelligenceModelApprovalResultV1Alpha1(BaseModel):
    """The separate exact reviewed receipt plus the Intelligence Agent's own approval admission."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    reviewed_approval: BuilderDispositionApprovalResultV1Alpha1
    approval: IntelligenceModelApprovalAdmission


class FirstBriefPrepareRequestV1Alpha1(BaseModel):
    """One explicit request to prepare the first Brief from the exact current
    ``INTELLIGENCE_MODEL_APPROVED`` handoff."""

    model_config = ConfigDict(extra="forbid")

    current: IntelligenceBuilderSessionRevisionV1
    concept_model: ConceptModelProposalV1
    concept_disposition: ConceptModelDispositionV1
    intelligence_model: IntelligenceModelProposalV1
    intelligence_disposition: IntelligenceModelDispositionV1
    observations: AuthorizedObservationSetV1
    generated_at: datetime

    @field_validator(
        "current",
        "concept_model",
        "concept_disposition",
        "intelligence_model",
        "intelligence_disposition",
        "observations",
        mode="before",
    )
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = {
                "current": IntelligenceBuilderSessionRevisionV1,
                "concept_model": ConceptModelProposalV1,
                "concept_disposition": ConceptModelDispositionV1,
                "intelligence_model": IntelligenceModelProposalV1,
                "intelligence_disposition": IntelligenceModelDispositionV1,
                "observations": AuthorizedObservationSetV1,
            }[info.field_name]
            return model.model_validate(value, strict=False)
        return value

    @field_validator("generated_at")
    @classmethod
    def _generated_time(cls, value: datetime) -> datetime:
        return _aware(value, name="generated_at")


class _IntelligenceModelProposalIntentV1Alpha1(BaseModel):
    """Append-only exclusive intent to propose an intelligence model from one
    exact prior revision.

    Keyed exclusively by ``(product_id, session_id, prior_revision_id,
    prior_revision_digest)`` -- never by request content -- so that this
    record itself is the exclusivity lock. It is persisted *after* the
    ``AuthorizedObservationSetV1`` has already been derived/reopened (that
    admission is idempotent and never itself calls a provider), but *before*
    the selected provider is ever called.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.intelligence-model-proposal-intent/v1alpha1"] = (
        INTELLIGENCE_MODEL_PROPOSAL_INTENT_VERSION
    )
    product_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    prior_revision_id: str = Field(min_length=1, max_length=240)
    prior_revision_digest: str = Field(min_length=1, max_length=240)
    connect_request_id: str = Field(min_length=1, max_length=240)
    connect_request_digest: str = Field(min_length=1, max_length=240)
    connect_result_id: str = Field(min_length=1, max_length=240)
    connect_result_digest: str = Field(min_length=1, max_length=240)
    source_profile_id: str = Field(min_length=1, max_length=240)
    source_profile_digest: str = Field(min_length=1, max_length=240)
    concept_model_id: str = Field(min_length=1, max_length=240)
    concept_model_digest: str = Field(min_length=1, max_length=240)
    concept_disposition_id: str = Field(min_length=1, max_length=240)
    concept_disposition_digest: str = Field(min_length=1, max_length=240)
    observation_set_id: str = Field(min_length=1, max_length=240)
    observation_set_digest: str = Field(min_length=1, max_length=240)
    user_intent: str = Field(min_length=1, max_length=2_000)
    audience_constraints_digest: str = Field(min_length=1, max_length=240)
    cadence_constraints_digest: str = Field(min_length=1, max_length=240)
    proposed_at: datetime
    request_material_digest: str = Field(min_length=1, max_length=240)

    @field_validator(
        "connect_request_id",
        "connect_result_id",
        "source_profile_id",
        "concept_model_id",
        "concept_disposition_id",
    )
    @classmethod
    def _validate_reference(cls, value: str) -> str:
        return _validate_reference(value)

    @field_validator(
        "connect_request_digest",
        "connect_result_digest",
        "source_profile_digest",
        "concept_model_digest",
        "concept_disposition_digest",
        "audience_constraints_digest",
        "cadence_constraints_digest",
        "request_material_digest",
    )
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        return _validate_digest(value)


class _FirstBriefingIntentV1Alpha1(BaseModel):
    """Append-only exclusive intent to prepare the first Brief from one exact
    prior revision.

    Keyed exclusively by ``(product_id, session_id, prior_revision_id,
    prior_revision_digest)`` -- never by request content.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.first-briefing-intent/v1alpha1"] = FIRST_BRIEFING_INTENT_VERSION
    product_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    prior_revision_id: str = Field(min_length=1, max_length=240)
    prior_revision_digest: str = Field(min_length=1, max_length=240)
    concept_model_id: str = Field(min_length=1, max_length=240)
    concept_model_digest: str = Field(min_length=1, max_length=240)
    concept_disposition_id: str = Field(min_length=1, max_length=240)
    concept_disposition_digest: str = Field(min_length=1, max_length=240)
    intelligence_model_proposal_id: str = Field(min_length=1, max_length=240)
    intelligence_model_proposal_digest: str = Field(min_length=1, max_length=240)
    intelligence_model_disposition_id: str = Field(min_length=1, max_length=240)
    intelligence_model_disposition_digest: str = Field(min_length=1, max_length=240)
    observation_set_id: str = Field(min_length=1, max_length=240)
    observation_set_digest: str = Field(min_length=1, max_length=240)
    generated_at: datetime
    request_material_digest: str = Field(min_length=1, max_length=240)

    @field_validator("concept_model_id", "concept_disposition_id")
    @classmethod
    def _validate_reference(cls, value: str) -> str:
        return _validate_reference(value)

    @field_validator(
        "concept_model_digest",
        "concept_disposition_digest",
        "request_material_digest",
    )
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        return _validate_digest(value)


@dataclass(frozen=True, slots=True)
class IntelligenceBuilderIntelligenceProgressionRuntime:
    """Production wiring for the Builder-to-Intelligence/Briefing-Agent progression."""

    records: ImmutableRecordStore
    grants: CoreAuthorityResolver
    repository: LocalSourceConnectRecordRepository
    provider: object | None = None
    provider_factory: Callable[[], object] = get_llm
    model: str | None = None
    max_tokens: int = 4096


def intelligence_builder_intelligence_progression_runtime() -> IntelligenceBuilderIntelligenceProgressionRuntime:
    """Build the production runtime over the primary durable stores and selected provider."""

    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceBuilderIntelligenceProgressionRuntime(
        records=records,
        grants=RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_state),
        repository=LocalSourceConnectRecordRepository(records),
    )


class _UnreachablePropositionAuthority(CoreAuthorityResolver):
    """Authority stand-in for intelligence-model proposal; ``propose`` never resolves approval or grants."""

    async def resolve_approval(self, **kwargs) -> ResolvedApprovalReceiptV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: intelligence-model proposal never resolves approval or grant evidence")

    async def resolve_grant(self, **kwargs) -> ResolvedAuthorityGrantV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: intelligence-model proposal never resolves approval or grant evidence")


_UNREACHABLE_PROPOSAL_AUTHORITY = _UnreachablePropositionAuthority()


class _UnreachableIntelligenceModelStrategy:
    """Strategy stand-in for intelligence-model approval; ``approve`` never proposes a new model."""

    async def propose(self, **kwargs):  # pragma: no cover - unreachable
        raise AssertionError("unreachable: intelligence-model approval never proposes a new intelligence model")


_UNREACHABLE_STRATEGY = _UnreachableIntelligenceModelStrategy()


def _proposal_intent_key(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
) -> str:
    material = {
        "product_id": product_id,
        "session_id": session.session_id,
        "prior_revision_id": session.revision_id,
        "prior_revision_digest": session.revision_digest,
    }
    digest = canonical_hash(material)
    return f"intelligence-proposal-intent:{digest[:32]}"


def _brief_intent_key(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
) -> str:
    material = {
        "product_id": product_id,
        "session_id": session.session_id,
        "prior_revision_id": session.revision_id,
        "prior_revision_digest": session.revision_digest,
    }
    digest = canonical_hash(material)
    return f"first-briefing-intent:{digest[:32]}"


def _expected_intent_record(
    *,
    product_id: str,
    record_space: str,
    record_kind: str,
    record_key: str,
    intent: BaseModel,
    intent_time: datetime,
) -> ImmutableRecordV1:
    """Rebuild the exact ``ImmutableRecordV1`` envelope one intent implies."""

    return ImmutableRecordV1(
        product_id=product_id,
        record_space=record_space,
        record_kind=record_kind,
        record_key=record_key,
        payload_contract=intent.contract,
        payload=intent.model_dump(mode="python"),
        as_of=intent_time,
        available_at=intent_time,
        processing_order=0,
    )


async def _load_raw_intent_record(
    *,
    records: ImmutableRecordStore,
    product_id: str,
    record_space: str,
    record_kind: str,
    record_key: str,
    unavailable_message: str,
) -> ImmutableRecordV1 | None:
    storage_id = immutable_record_storage_id(
        product_id=product_id,
        record_space=record_space,
        record_kind=record_kind,
        record_key=record_key,
    )
    try:
        return await records.load_record(
            storage_id,
            product_id=product_id,
            record_space=record_space,
            record_kind=record_kind,
        )
    except Exception as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(unavailable_message) from exc


def _require_exact_intent_envelope(
    *,
    loaded: ImmutableRecordV1 | None,
    expected: ImmutableRecordV1,
    conflict_message: str,
) -> ImmutableRecordV1:
    """Require the loaded record to match the expected envelope in full,
    including its derived ``storage_id``/``material_hash`` -- not just its
    payload."""

    if loaded is None or loaded != expected:
        raise IntelligenceBuilderIntelligenceProgressionConflict(conflict_message)
    return loaded


def _proposal_request_material(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    request: IntelligenceModelProposeRequestV1Alpha1,
    observation_set_id: str,
    observation_set_digest: str,
) -> dict:
    return {
        "session_id": session.session_id,
        "prior_revision_id": session.revision_id,
        "prior_revision_digest": session.revision_digest,
        "connect_request": request.connect_request.model_dump(mode="json"),
        "connect_result": request.connect_result.model_dump(mode="json"),
        "source_profile": request.source_profile.model_dump(mode="json"),
        "concept_model": request.concept_model.model_dump(mode="json"),
        "concept_disposition": request.concept_disposition.model_dump(mode="json"),
        "observation_set_id": observation_set_id,
        "observation_set_digest": observation_set_digest,
        "user_intent": request.user_intent,
        "audience_constraints": list(request.audience_constraints),
        "cadence_constraints": [item.value for item in request.cadence_constraints],
        "proposed_at": request.proposed_at.isoformat(),
    }


def _proposal_request_material_digest(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    request: IntelligenceModelProposeRequestV1Alpha1,
    observation_set_id: str,
    observation_set_digest: str,
) -> str:
    digest = canonical_hash(
        _proposal_request_material(
            session=session,
            request=request,
            observation_set_id=observation_set_id,
            observation_set_digest=observation_set_digest,
        )
    )
    return f"sha256:{digest}"


def _build_proposal_intent(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
    request: IntelligenceModelProposeRequestV1Alpha1,
    observations: AuthorizedObservationSetV1,
) -> _IntelligenceModelProposalIntentV1Alpha1:
    observation_set_id = str(observations.observation_set_id)
    observation_set_digest = str(observations.observation_set_digest)
    return _IntelligenceModelProposalIntentV1Alpha1(
        product_id=product_id,
        session_id=session.session_id,
        prior_revision_id=str(session.revision_id),
        prior_revision_digest=str(session.revision_digest),
        connect_request_id=str(request.connect_request.authorization_id),
        connect_request_digest=str(request.connect_request.authorization_digest),
        connect_result_id=str(request.connect_result.result_id),
        connect_result_digest=str(request.connect_result.result_digest),
        source_profile_id=str(request.source_profile.proposal_id),
        source_profile_digest=str(request.source_profile.proposal_digest),
        concept_model_id=str(request.concept_model.proposal_id),
        concept_model_digest=str(request.concept_model.proposal_digest),
        concept_disposition_id=str(request.concept_disposition.disposition_id),
        concept_disposition_digest=str(request.concept_disposition.disposition_digest),
        observation_set_id=observation_set_id,
        observation_set_digest=observation_set_digest,
        user_intent=request.user_intent,
        audience_constraints_digest=_digest_of(request.audience_constraints),
        cadence_constraints_digest=_cadence_digest(request.cadence_constraints),
        proposed_at=request.proposed_at,
        request_material_digest=_proposal_request_material_digest(
            session=session,
            request=request,
            observation_set_id=observation_set_id,
            observation_set_digest=observation_set_digest,
        ),
    )


async def _persist_proposal_intent(
    *,
    records: ImmutableRecordStore,
    intent_key: str,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
    request: IntelligenceModelProposeRequestV1Alpha1,
    observations: AuthorizedObservationSetV1,
) -> _IntelligenceModelProposalIntentV1Alpha1:
    """Persist the exclusive proposal intent before any provider call.

    On a replay conflict, the existing record is reloaded and compared
    field-by-field. An exact match means this is a benign concurrent
    duplicate; any mismatch fails closed before ever calling the provider.
    """

    intent = _build_proposal_intent(product_id=product_id, session=session, request=request, observations=observations)
    record = _expected_intent_record(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.proposed_at,
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
        return await _matching_existing_proposal_intent(
            records=records,
            intent_key=intent_key,
            product_id=product_id,
            intent=intent,
        )
    except Exception as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model proposal intent could not be recorded"
        ) from exc
    if receipt != txn.receipt():
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model proposal intent receipt does not match the exact append request"
        )
    return intent


async def _matching_existing_proposal_intent(
    *,
    records: ImmutableRecordStore,
    intent_key: str,
    product_id: str,
    intent: _IntelligenceModelProposalIntentV1Alpha1,
) -> _IntelligenceModelProposalIntentV1Alpha1:
    expected = _expected_intent_record(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.proposed_at,
    )
    existing = await _load_raw_intent_record(
        records=records,
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        unavailable_message="intelligence-model proposal intent storage is unavailable",
    )
    _require_exact_intent_envelope(
        loaded=existing,
        expected=expected,
        conflict_message="intelligence-model proposal intent already recorded different exact material",
    )
    return intent


async def _reopen_typed_artifact(
    *,
    sessions: IntelligenceBuilderSessionService,
    product_id: str,
    artifacts: tuple,
    artifact_kind: OnboardingArtifactKind,
    artifact_type: type,
    available_at: datetime,
    missing_message: str,
    unavailable_message: str,
):
    reference = next((item for item in artifacts if item.artifact_kind is artifact_kind), None)
    if reference is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(missing_message)
    try:
        return await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=artifact_type,
            available_at=available_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(missing_message) from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(unavailable_message) from exc


async def _reconstruct_proposal_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    records: ImmutableRecordStore,
    repository: LocalSourceConnectRecordRepository,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    product_id: str,
    request: IntelligenceModelProposeRequestV1Alpha1,
    occurred_at: datetime,
) -> IntelligenceModelProposalAdmission:
    """Reopen the already-durable exact one-step proposal outcome for a retry.

    Never calls ``admit_local_source_observations``, the selected provider,
    or ``IntelligenceAgent.propose`` again: it only verifies this exact
    retried request against the recorded exclusive intent, then reopens
    durable material directly from ``latest``'s own artifact reference.
    """

    intent_key = _proposal_intent_key(product_id=product_id, session=session)
    record = await _load_raw_intent_record(
        records=records,
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        unavailable_message="intelligence-model proposal intent storage is unavailable",
    )
    if record is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced without any recorded proposal intent for this prior revision"
        )
    try:
        intent = _IntelligenceModelProposalIntentV1Alpha1.model_validate(record.payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model proposal intent failed exact revalidation"
        ) from exc
    expected = _expected_intent_record(
        product_id=product_id,
        record_space=_PROPOSAL_INTENT_RECORD_SPACE,
        record_kind=_PROPOSAL_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.proposed_at,
    )
    _require_exact_intent_envelope(
        loaded=record,
        expected=expected,
        conflict_message="intelligence-model proposal intent does not match this exact prior revision",
    )
    if (
        intent.product_id != product_id
        or intent.session_id != session.session_id
        or intent.prior_revision_id != session.revision_id
        or intent.prior_revision_digest != session.revision_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "intelligence-model proposal intent does not match this exact prior revision"
        )
    retried_material_digest = _proposal_request_material_digest(
        session=session,
        request=request,
        observation_set_id=intent.observation_set_id,
        observation_set_digest=intent.observation_set_digest,
    )
    if (
        intent.connect_request_id != str(request.connect_request.authorization_id)
        or intent.connect_request_digest != str(request.connect_request.authorization_digest)
        or intent.connect_result_id != str(request.connect_result.result_id)
        or intent.connect_result_digest != str(request.connect_result.result_digest)
        or intent.source_profile_id != str(request.source_profile.proposal_id)
        or intent.source_profile_digest != str(request.source_profile.proposal_digest)
        or intent.concept_model_id != str(request.concept_model.proposal_id)
        or intent.concept_model_digest != str(request.concept_model.proposal_digest)
        or intent.concept_disposition_id != str(request.concept_disposition.disposition_id)
        or intent.concept_disposition_digest != str(request.concept_disposition.disposition_digest)
        or intent.user_intent != request.user_intent
        or intent.audience_constraints_digest != _digest_of(request.audience_constraints)
        or intent.cadence_constraints_digest != _cadence_digest(request.cadence_constraints)
        or intent.proposed_at != request.proposed_at
        or intent.request_material_digest != retried_material_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "a different request collided with the exact proposal intent already admitted for this prior revision"
        )

    # Reopen the recorded Connect transaction without any external read: the
    # retried request/intent's copied connect fields are never trusted alone.
    try:
        replayed_connect = await repository.replay(request.connect_request)
    except LocalSourceConnectRecordConflict as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's Connect transaction does not match this exact prior revision"
        ) from exc
    except LocalSourceConnectRecordUnavailable as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "Connect transaction storage is unavailable"
        ) from exc
    if replayed_connect is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's Connect transaction is not durably recorded"
        )
    if (
        replayed_connect != request.connect_result
        or str(replayed_connect.result_id) != intent.connect_result_id
        or str(replayed_connect.result_digest) != intent.connect_result_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's Connect transaction does not match this exact retried request"
        )

    # Reopen the exact durable artifacts this proposal was bound to -- not
    # just the recorded intent's copied ids -- and require them to still
    # correspond to the supplied request material.
    source_profile = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL,
        artifact_type=SourceProfileProposalV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this proposal without a durable source-profile artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(source_profile.proposal_id) != str(request.source_profile.proposal_id)
        or str(source_profile.proposal_digest) != str(request.source_profile.proposal_digest)
        or str(source_profile.proposal_id) != intent.source_profile_id
        or str(source_profile.proposal_digest) != intent.source_profile_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's source profile does not match this exact retried request"
        )

    concept_model = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
        artifact_type=ConceptModelProposalV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this proposal without a durable concept-model artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(concept_model.proposal_id) != str(request.concept_model.proposal_id)
        or str(concept_model.proposal_digest) != str(request.concept_model.proposal_digest)
        or str(concept_model.proposal_id) != intent.concept_model_id
        or str(concept_model.proposal_digest) != intent.concept_model_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's concept model does not match this exact retried request"
        )

    concept_disposition = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,
        artifact_type=ConceptModelDispositionV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this proposal without a durable concept-disposition artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(concept_disposition.disposition_id) != str(request.concept_disposition.disposition_id)
        or str(concept_disposition.disposition_digest) != str(request.concept_disposition.disposition_digest)
        or str(concept_disposition.disposition_id) != intent.concept_disposition_id
        or str(concept_disposition.disposition_digest) != intent.concept_disposition_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's concept disposition does not match this exact retried request"
        )

    observation_set = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
        artifact_type=AuthorizedObservationSetV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this proposal without a durable authorized-observation-set artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(observation_set.observation_set_id) != intent.observation_set_id
        or str(observation_set.observation_set_digest) != intent.observation_set_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's authorized observation set does not match this exact retried request"
        )
    if observation_set.source_profile_proposal_id != str(
        source_profile.proposal_id
    ) or observation_set.source_profile_proposal_digest != str(source_profile.proposal_digest):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's authorized observation set does not point at this exact reopened source profile"
        )

    reference = next(
        (item for item in latest.artifacts if item.artifact_kind is OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL),
        None,
    )
    if reference is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced past this proposal without a durable artifact reference"
        )
    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != INTELLIGENCE_AGENT_ACTOR_REF
        or latest.product_id != product_id
        or latest.session_id != session.session_id
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry crossed its exact transition time, actor, or chain"
        )
    try:
        persisted_proposal = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=IntelligenceModelProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict("proposal is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder artifact storage is unavailable") from exc
    if (
        str(persisted_proposal.concept_model_proposal_id) != str(concept_model.proposal_id)
        or str(persisted_proposal.concept_model_proposal_digest) != str(concept_model.proposal_digest)
        or str(persisted_proposal.concept_model_disposition_id) != str(concept_disposition.disposition_id)
        or str(persisted_proposal.concept_model_disposition_digest) != str(concept_disposition.disposition_digest)
        or str(persisted_proposal.observation_set_id) != str(observation_set.observation_set_id)
        or str(persisted_proposal.observation_set_digest) != str(observation_set.observation_set_digest)
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry's proposal is not exactly bound to its durable source profile, concept "
            "model, concept disposition, or authorized observation set"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        proposal_admission = await sessions.persist_artifact(product_id=product_id, artifact=persisted_proposal)
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable propose retry could not be exactly reopened"
        ) from exc
    return IntelligenceModelProposalAdmission(
        proposal=persisted_proposal,
        proposal_admission=proposal_admission,
        session=session_admission,
    )


async def propose_intelligence_builder_intelligence_model(
    *,
    request: IntelligenceModelProposeRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime,
) -> IntelligenceModelProposalAdmission:
    """Propose the Intelligence Agent's model from the exact current CONCEPT_MODEL_APPROVED handoff.

    Reloads the exact current session, verifies the fixed local owner, derives
    or reopens the ``AuthorizedObservationSetV1`` through
    ``admit_local_source_observations``, and calls ``IntelligenceAgent.propose``
    through ``SelectedIntelligenceModelStrategy`` with the fixed transition
    actor ``agent:intelligence``.
    """

    actor_ref, product_id = _verified_owner(user)
    session = request.current
    if session.product_id != product_id:
        raise IntelligenceBuilderIntelligenceProgressionDenied("Builder session crossed verified local-owner scope")
    occurred_at = request.proposed_at

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before proposing")

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.INTELLIGENCE_MODEL_PROPOSED
        and latest.transition_authority is OnboardingTransitionAuthority.AGENT_PROPOSAL
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_proposal_retry(
            sessions=sessions,
            records=runtime.records,
            repository=runtime.repository,
            latest=latest,
            session=session,
            product_id=product_id,
            request=request,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before proposing")
    if latest.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session is not at the exact stage to propose an intelligence model"
        )

    try:
        admission = await admit_local_source_observations(
            request=request.connect_request,
            result=request.connect_result,
            session=session,
            source_profile=request.source_profile,
            concept_model=request.concept_model,
            concept_disposition=request.concept_disposition,
            user=user,
            admitted_at=occurred_at,
            repository=runtime.repository,
            sessions=sessions,
        )
    except ObservationAdmissionDenied as exc:
        raise IntelligenceBuilderIntelligenceProgressionDenied(
            "verified caller could not admit the exact authorized observation set"
        ) from exc
    except ObservationAdmissionUnavailable as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "authorized observation admission storage is unavailable"
        ) from exc
    except (ObservationAdmissionStaleInput, ObservationAdmissionClosureError, ObservationAdmissionBoundError) as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "authorized observation admission could not admit the exact current handoff"
        ) from exc
    except ObservationAdmissionError as exc:  # pragma: no cover - defensive catch-all
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "authorized observation admission failed before a safe result"
        ) from exc
    observations = admission.observation_set

    intent_key = _proposal_intent_key(product_id=product_id, session=session)
    await _persist_proposal_intent(
        records=runtime.records,
        intent_key=intent_key,
        product_id=product_id,
        session=session,
        request=request,
        observations=observations,
    )

    # Race recheck: another request may have admitted its own intent for this
    # same prior revision and already advanced the session between our
    # `load_latest` above and our intent admission just now.
    try:
        recheck = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder session storage is unavailable") from exc
    if (
        recheck is None
        or recheck.revision_id != session.revision_id
        or recheck.revision_digest != session.revision_digest
        or recheck.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced past this proposal intent from a different exact request"
        )

    strategy = SelectedIntelligenceModelStrategy(
        provider=runtime.provider,
        provider_factory=runtime.provider_factory,
        model=runtime.model,
        max_tokens=runtime.max_tokens,
    )
    agent = IntelligenceAgent(sessions=sessions, authority=_UNREACHABLE_PROPOSAL_AUTHORITY, strategy=strategy)

    try:
        outcome = await agent.propose(
            latest,
            concept_model=request.concept_model,
            concept_disposition=request.concept_disposition,
            observations=observations,
            user_intent=request.user_intent,
            audience_constraints=request.audience_constraints,
            cadence_constraints=request.cadence_constraints,
            actor_ref=INTELLIGENCE_AGENT_ACTOR_REF,
            occurred_at=occurred_at,
        )
    except IntelligenceAgentAttributionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "intelligence-model proposal lost exact evidence attribution"
        ) from exc
    except IntelligenceAgentStaleInput as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "intelligence-model proposal started from stale session or evidence material"
        ) from exc
    except IntelligenceAgentError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model strategy failed before a safe proposal"
        ) from exc

    if outcome.proposal is None:
        raise IntelligenceBuilderIntelligenceProgressionDenied(
            f"intelligence-model proposal was blocked: {outcome.blocked_reason}"
        )

    return outcome.proposal


async def _reconstruct_approval_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    authority: RecordedIntelligenceBuilderDispositionAuthority,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    proposal: IntelligenceModelProposalV1,
    actor_ref: str,
    occurred_at: datetime,
) -> IntelligenceModelApprovalResultV1Alpha1:
    """Reopen the already-durable exact one-step INTELLIGENCE_MODEL_APPROVED outcome for a retry."""

    if latest.approval_receipt_ref is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable approval retry lost its exact approval receipt"
        )

    exact_proposal = IntelligenceModelProposalV1.model_validate(proposal.model_dump(mode="python"))
    proposal_reference = next(
        (
            item
            for item in session.artifacts
            if item.artifact_kind is OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL
        ),
        None,
    )
    if (
        proposal_reference is None
        or proposal_reference.artifact_id != exact_proposal.proposal_id
        or proposal_reference.artifact_digest != exact_proposal.proposal_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "supplied intelligence-model proposal is not the exact current session handoff"
        )
    try:
        persisted_proposal = await sessions.load_artifact(
            product_id=session.product_id,
            reference=proposal_reference,
            artifact_type=IntelligenceModelProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable intelligence-model proposal could not be exactly reopened"
        ) from exc
    if persisted_proposal != exact_proposal:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "supplied intelligence-model proposal differs from the exact durable handoff"
        )

    disposition_reference = next(
        (
            item
            for item in latest.artifacts
            if item.artifact_kind is OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION
        ),
        None,
    )
    if disposition_reference is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced to intelligence_model_approved without a durable disposition"
        )
    try:
        disposition = await sessions.load_artifact(
            product_id=session.product_id,
            reference=disposition_reference,
            artifact_type=IntelligenceModelDispositionV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable intelligence-model disposition could not be exactly reopened"
        ) from exc
    if (
        disposition.session_id != session.session_id
        or disposition.proposal_id != str(exact_proposal.proposal_id)
        or disposition.proposal_digest != str(exact_proposal.proposal_digest)
        or disposition.actor_ref != actor_ref
        or disposition.approval_receipt_ref != latest.approval_receipt_ref
        or disposition.approved_at != occurred_at
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable intelligence-model disposition does not match this exact retried approval"
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
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable reviewed intelligence-model approval could not be exactly reopened"
        ) from exc
    if (
        resolved.receipt_ref != latest.approval_receipt_ref
        or resolved.product_id != session.product_id
        or resolved.subject_ref != exact_proposal.proposal_id
        or resolved.actor_ref != actor_ref
        or resolved.approved_at != occurred_at
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable reviewed intelligence-model approval does not match this exact retried approval"
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
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable approval retry crossed its exact transition time, actor, or chain"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        disposition_admission = await sessions.persist_artifact(product_id=session.product_id, artifact=disposition)
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable approval retry could not be exactly reopened"
        ) from exc

    approval = IntelligenceModelApprovalAdmission(
        proposal=exact_proposal,
        disposition=disposition,
        disposition_admission=disposition_admission,
        session=session_admission,
    )
    return IntelligenceModelApprovalResultV1Alpha1(reviewed_approval=reviewed, approval=approval)


async def approve_intelligence_builder_intelligence_model(
    *,
    request: BuilderIntelligenceModelApproveRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime,
) -> IntelligenceModelApprovalResultV1Alpha1:
    """Approve the exact current INTELLIGENCE_MODEL_PROPOSED intelligence model.

    First records a separate exact reviewed receipt through the existing
    ``approve_builder_intelligence_model``, then calls the existing
    ``IntelligenceAgent.approve`` with
    ``RecordedIntelligenceBuilderDispositionAuthority`` and the fixed
    local-owner actor. Only ``decision='approve'`` is supported; this
    coordinator never fabricates or bundles any other approval, and never
    mints a grant of its own.
    """

    actor_ref, product_id = _verified_owner(user)
    session = request.current
    if session.product_id != product_id:
        raise IntelligenceBuilderIntelligenceProgressionDenied("Builder session crossed verified local-owner scope")
    occurred_at = request.approved_at

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before approving")

    authority = RecordedIntelligenceBuilderDispositionAuthority(records=runtime.records, grants=runtime.grants)

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.INTELLIGENCE_MODEL_APPROVED
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
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before approving")
    if latest.stage is not OnboardingStage.INTELLIGENCE_MODEL_PROPOSED:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session is not at the exact stage for intelligence-model approval"
        )

    try:
        reviewed = await approve_builder_intelligence_model(request=request, user=user, records=runtime.records)
    except BuilderDispositionApprovalUnavailable as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model reviewed approval storage is unavailable"
        ) from exc
    except BuilderDispositionApprovalError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "intelligence-model reviewed approval could not be exactly recorded"
        ) from exc

    agent = IntelligenceAgent(sessions=sessions, authority=authority, strategy=_UNREACHABLE_STRATEGY)
    try:
        approval = await agent.approve(
            latest,
            proposal=request.proposal,
            approval_receipt_ref=reviewed.approval.receipt_ref,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
    except IntelligenceAgentStaleInput as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "intelligence-model approval started from stale session or proposal material"
        ) from exc
    except IntelligenceAgentError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "intelligence-model approval failed exact Core resolution"
        ) from exc

    return IntelligenceModelApprovalResultV1Alpha1(reviewed_approval=reviewed, approval=approval)


def _brief_request_material(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    request: FirstBriefPrepareRequestV1Alpha1,
) -> dict:
    return {
        "session_id": session.session_id,
        "prior_revision_id": session.revision_id,
        "prior_revision_digest": session.revision_digest,
        "concept_model": request.concept_model.model_dump(mode="json"),
        "concept_disposition": request.concept_disposition.model_dump(mode="json"),
        "intelligence_model": request.intelligence_model.model_dump(mode="json"),
        "intelligence_disposition": request.intelligence_disposition.model_dump(mode="json"),
        "observation_set_id": str(request.observations.observation_set_id),
        "observation_set_digest": str(request.observations.observation_set_digest),
        "generated_at": request.generated_at.isoformat(),
    }


def _brief_request_material_digest(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    request: FirstBriefPrepareRequestV1Alpha1,
) -> str:
    digest = canonical_hash(_brief_request_material(session=session, request=request))
    return f"sha256:{digest}"


def _build_first_briefing_intent(
    *,
    product_id: str,
    session: IntelligenceBuilderSessionRevisionV1,
    request: FirstBriefPrepareRequestV1Alpha1,
) -> _FirstBriefingIntentV1Alpha1:
    return _FirstBriefingIntentV1Alpha1(
        product_id=product_id,
        session_id=session.session_id,
        prior_revision_id=str(session.revision_id),
        prior_revision_digest=str(session.revision_digest),
        concept_model_id=str(request.concept_model.proposal_id),
        concept_model_digest=str(request.concept_model.proposal_digest),
        concept_disposition_id=str(request.concept_disposition.disposition_id),
        concept_disposition_digest=str(request.concept_disposition.disposition_digest),
        intelligence_model_proposal_id=str(request.intelligence_model.proposal_id),
        intelligence_model_proposal_digest=str(request.intelligence_model.proposal_digest),
        intelligence_model_disposition_id=str(request.intelligence_disposition.disposition_id),
        intelligence_model_disposition_digest=str(request.intelligence_disposition.disposition_digest),
        observation_set_id=str(request.observations.observation_set_id),
        observation_set_digest=str(request.observations.observation_set_digest),
        generated_at=request.generated_at,
        request_material_digest=_brief_request_material_digest(session=session, request=request),
    )


async def _matching_existing_brief_intent(
    *,
    records: ImmutableRecordStore,
    intent_key: str,
    product_id: str,
    intent: _FirstBriefingIntentV1Alpha1,
) -> _FirstBriefingIntentV1Alpha1:
    expected = _expected_intent_record(
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.generated_at,
    )
    existing = await _load_raw_intent_record(
        records=records,
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=intent_key,
        unavailable_message="first-Brief intent storage is unavailable",
    )
    _require_exact_intent_envelope(
        loaded=existing,
        expected=expected,
        conflict_message="first-Brief intent already recorded different exact material",
    )
    return intent


async def _reconstruct_first_briefing_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    records: ImmutableRecordStore,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    product_id: str,
    request: FirstBriefPrepareRequestV1Alpha1,
    occurred_at: datetime,
) -> FirstBriefingAdmission:
    """Reopen the already-durable exact one-step FIRST_BRIEFING_READY outcome for a retry.

    Never calls the selected provider or ``BriefingAgent.create_first_brief``
    again.
    """

    intent_key = _brief_intent_key(product_id=product_id, session=session)
    record = await _load_raw_intent_record(
        records=records,
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=intent_key,
        unavailable_message="first-Brief intent storage is unavailable",
    )
    if record is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced without any recorded first-Brief intent for this prior revision"
        )
    try:
        intent = _FirstBriefingIntentV1Alpha1.model_validate(record.payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "first-Brief intent failed exact revalidation"
        ) from exc
    expected = _expected_intent_record(
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.generated_at,
    )
    _require_exact_intent_envelope(
        loaded=record,
        expected=expected,
        conflict_message="first-Brief intent does not match this exact prior revision",
    )
    if (
        intent.product_id != product_id
        or intent.session_id != session.session_id
        or intent.prior_revision_id != session.revision_id
        or intent.prior_revision_digest != session.revision_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "first-Brief intent does not match this exact prior revision"
        )
    retried_material_digest = _brief_request_material_digest(session=session, request=request)
    if (
        intent.concept_model_id != str(request.concept_model.proposal_id)
        or intent.concept_model_digest != str(request.concept_model.proposal_digest)
        or intent.concept_disposition_id != str(request.concept_disposition.disposition_id)
        or intent.concept_disposition_digest != str(request.concept_disposition.disposition_digest)
        or intent.intelligence_model_proposal_id != str(request.intelligence_model.proposal_id)
        or intent.intelligence_model_proposal_digest != str(request.intelligence_model.proposal_digest)
        or intent.intelligence_model_disposition_id != str(request.intelligence_disposition.disposition_id)
        or intent.intelligence_model_disposition_digest != str(request.intelligence_disposition.disposition_digest)
        or intent.observation_set_id != str(request.observations.observation_set_id)
        or intent.observation_set_digest != str(request.observations.observation_set_digest)
        or intent.generated_at != request.generated_at
        or intent.request_material_digest != retried_material_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "a different request collided with the exact first-Brief intent already admitted for this prior revision"
        )

    # Reopen the exact durable input artifacts this first Brief was bound to
    # -- not just the recorded intent's copied ids -- and require them to
    # still correspond to the supplied request material.
    concept_model = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
        artifact_type=ConceptModelProposalV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this first Brief without a durable concept-model artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(concept_model.proposal_id) != str(request.concept_model.proposal_id)
        or str(concept_model.proposal_digest) != str(request.concept_model.proposal_digest)
        or str(concept_model.proposal_id) != intent.concept_model_id
        or str(concept_model.proposal_digest) != intent.concept_model_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's concept model does not match this exact retried request"
        )

    concept_disposition = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,
        artifact_type=ConceptModelDispositionV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this first Brief without a durable concept-disposition artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(concept_disposition.disposition_id) != str(request.concept_disposition.disposition_id)
        or str(concept_disposition.disposition_digest) != str(request.concept_disposition.disposition_digest)
        or str(concept_disposition.disposition_id) != intent.concept_disposition_id
        or str(concept_disposition.disposition_digest) != intent.concept_disposition_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's concept disposition does not match this exact retried request"
        )

    intelligence_model = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL,
        artifact_type=IntelligenceModelProposalV1,
        available_at=occurred_at,
        missing_message="Builder session advanced past this first Brief without a durable intelligence-model artifact",
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(intelligence_model.proposal_id) != str(request.intelligence_model.proposal_id)
        or str(intelligence_model.proposal_digest) != str(request.intelligence_model.proposal_digest)
        or str(intelligence_model.proposal_id) != intent.intelligence_model_proposal_id
        or str(intelligence_model.proposal_digest) != intent.intelligence_model_proposal_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's intelligence model does not match this exact retried request"
        )

    intelligence_disposition = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION,
        artifact_type=IntelligenceModelDispositionV1,
        available_at=occurred_at,
        missing_message=(
            "Builder session advanced past this first Brief without a durable intelligence-disposition artifact"
        ),
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(intelligence_disposition.disposition_id) != str(request.intelligence_disposition.disposition_id)
        or str(intelligence_disposition.disposition_digest) != str(request.intelligence_disposition.disposition_digest)
        or str(intelligence_disposition.disposition_id) != intent.intelligence_model_disposition_id
        or str(intelligence_disposition.disposition_digest) != intent.intelligence_model_disposition_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's intelligence disposition does not match this exact retried request"
        )

    observation_set = await _reopen_typed_artifact(
        sessions=sessions,
        product_id=product_id,
        artifacts=latest.artifacts,
        artifact_kind=OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
        artifact_type=AuthorizedObservationSetV1,
        available_at=occurred_at,
        missing_message=(
            "Builder session advanced past this first Brief without a durable authorized-observation-set artifact"
        ),
        unavailable_message="Builder artifact storage is unavailable",
    )
    if (
        str(observation_set.observation_set_id) != str(request.observations.observation_set_id)
        or str(observation_set.observation_set_digest) != str(request.observations.observation_set_digest)
        or str(observation_set.observation_set_id) != intent.observation_set_id
        or str(observation_set.observation_set_digest) != intent.observation_set_digest
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's authorized observation set does not match this exact retried request"
        )

    reference = next(
        (item for item in latest.artifacts if item.artifact_kind is OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW),
        None,
    )
    if reference is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced past this first Brief without a durable artifact reference"
        )
    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != BRIEFING_AGENT_ACTOR_REF
        or latest.product_id != product_id
        or latest.session_id != session.session_id
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry crossed its exact transition time, actor, or chain"
        )
    try:
        persisted_brief = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=FirstBriefingPreviewV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict("first Brief is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder artifact storage is unavailable") from exc
    derivation = persisted_brief.derivation
    if (
        str(derivation.concept_model_proposal_id) != str(concept_model.proposal_id)
        or str(derivation.concept_model_proposal_digest) != str(concept_model.proposal_digest)
        or str(derivation.concept_model_disposition_id) != str(concept_disposition.disposition_id)
        or str(derivation.concept_model_disposition_digest) != str(concept_disposition.disposition_digest)
        or str(derivation.intelligence_model_proposal_id) != str(intelligence_model.proposal_id)
        or str(derivation.intelligence_model_proposal_digest) != str(intelligence_model.proposal_digest)
        or str(derivation.intelligence_model_disposition_id) != str(intelligence_disposition.disposition_id)
        or str(derivation.intelligence_model_disposition_digest) != str(intelligence_disposition.disposition_digest)
        or str(derivation.observation_set_id) != str(observation_set.observation_set_id)
        or str(derivation.observation_set_digest) != str(observation_set.observation_set_digest)
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry's brief is not exactly bound to its durable concept model, concept "
            "disposition, intelligence model, intelligence disposition, or authorized observation set"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        brief_admission = await sessions.persist_artifact(product_id=product_id, artifact=persisted_brief)
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "durable first-Brief retry could not be exactly reopened"
        ) from exc
    return FirstBriefingAdmission(
        brief=persisted_brief,
        brief_admission=brief_admission,
        session=session_admission,
    )


async def prepare_intelligence_builder_first_brief(
    *,
    request: FirstBriefPrepareRequestV1Alpha1,
    user: dict,
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime,
) -> FirstBriefingAdmission:
    """Prepare the first Brief from the exact current INTELLIGENCE_MODEL_APPROVED handoff.

    Calls the existing ``BriefingAgent.create_first_brief`` through
    ``SelectedBriefingStrategy`` with the fixed transition actor
    ``agent:briefing``. There is no separate Brief approval; this
    coordinator never fabricates or bundles one.
    """

    actor_ref, product_id = _verified_owner(user)
    session = request.current
    if session.product_id != product_id:
        raise IntelligenceBuilderIntelligenceProgressionDenied("Builder session crossed verified local-owner scope")
    occurred_at = request.generated_at

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before preparing")

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.FIRST_BRIEFING_READY
        and latest.transition_authority is OnboardingTransitionAuthority.AGENT_PROPOSAL
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_first_briefing_retry(
            sessions=sessions,
            records=runtime.records,
            latest=latest,
            session=session,
            product_id=product_id,
            request=request,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise IntelligenceBuilderIntelligenceProgressionConflict("Builder session is stale; reload before preparing")
    if latest.stage is not OnboardingStage.INTELLIGENCE_MODEL_APPROVED:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session is not at the exact stage to prepare the first Brief"
        )

    intent_key = _brief_intent_key(product_id=product_id, session=session)
    intent = _build_first_briefing_intent(product_id=product_id, session=session, request=request)
    record = _expected_intent_record(
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        record_kind=_BRIEF_INTENT_RECORD_KIND,
        record_key=intent_key,
        intent=intent,
        intent_time=intent.generated_at,
    )
    txn = AppendOnlyTransactionRequestV1(
        product_id=product_id,
        record_space=_BRIEF_INTENT_RECORD_SPACE,
        transaction_key=intent_key,
        records=(record,),
        submitted_at=request.generated_at,
    )
    try:
        receipt = await runtime.records.append(txn)
    except ImmutableRecordReplayConflict:
        await _matching_existing_brief_intent(
            records=runtime.records,
            intent_key=intent_key,
            product_id=product_id,
            intent=intent,
        )
    except Exception as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("first-Brief intent could not be recorded") from exc
    else:
        if receipt != txn.receipt():
            raise IntelligenceBuilderIntelligenceProgressionUnavailable(
                "first-Brief intent receipt does not match the exact append request"
            )

    # Race recheck: another request may have admitted its own intent for this
    # same prior revision and already advanced the session.
    try:
        recheck = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable("Builder session storage is unavailable") from exc
    if (
        recheck is None
        or recheck.revision_id != session.revision_id
        or recheck.revision_digest != session.revision_digest
        or recheck.stage is not OnboardingStage.INTELLIGENCE_MODEL_APPROVED
    ):
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "Builder session advanced past this first-Brief intent from a different exact request"
        )

    strategy = SelectedBriefingStrategy(
        provider=runtime.provider,
        provider_factory=runtime.provider_factory,
        model=runtime.model,
        max_tokens=runtime.max_tokens,
    )
    agent = BriefingAgent(sessions=sessions, strategy=strategy)

    try:
        outcome = await agent.create_first_brief(
            latest,
            concept_model=request.concept_model,
            concept_disposition=request.concept_disposition,
            intelligence_model=request.intelligence_model,
            intelligence_disposition=request.intelligence_disposition,
            observations=request.observations,
            actor_ref=BRIEFING_AGENT_ACTOR_REF,
            occurred_at=occurred_at,
        )
    except BriefingAgentAttributionError as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "first-Brief synthesis lost exact evidence attribution"
        ) from exc
    except BriefingAgentStaleInput as exc:
        raise IntelligenceBuilderIntelligenceProgressionConflict(
            "first-Brief synthesis started from stale session or approved material"
        ) from exc
    except BriefingAgentError as exc:
        raise IntelligenceBuilderIntelligenceProgressionUnavailable(
            "first-Brief strategy failed before a safe synthesis"
        ) from exc

    if outcome.briefing is None:
        raise IntelligenceBuilderIntelligenceProgressionDenied(
            f"first-Brief preparation was blocked: {outcome.blocked_reason}"
        )

    return outcome.briefing


__all__ = [
    "BRIEFING_AGENT_ACTOR_REF",
    "FIRST_BRIEFING_INTENT_VERSION",
    "INTELLIGENCE_AGENT_ACTOR_REF",
    "INTELLIGENCE_MODEL_PROPOSAL_INTENT_VERSION",
    "FirstBriefPrepareRequestV1Alpha1",
    "IntelligenceBuilderIntelligenceProgressionConflict",
    "IntelligenceBuilderIntelligenceProgressionDenied",
    "IntelligenceBuilderIntelligenceProgressionError",
    "IntelligenceBuilderIntelligenceProgressionRuntime",
    "IntelligenceBuilderIntelligenceProgressionUnavailable",
    "IntelligenceModelApprovalResultV1Alpha1",
    "IntelligenceModelProposeRequestV1Alpha1",
    "approve_intelligence_builder_intelligence_model",
    "intelligence_builder_intelligence_progression_runtime",
    "prepare_intelligence_builder_first_brief",
    "propose_intelligence_builder_intelligence_model",
]
