"""Admit an ``AuthorizedObservationSetV1`` from recorded local Connect captures.

This host module derives one exact :class:`AuthorizedObservationSetV1` from the
already-recorded local Connect captures behind a ``CONCEPT_MODEL_APPROVED``
onboarding session, and admits it exclusively through the existing
:class:`~ace.application.intelligence_agent.IntelligenceAgent.admit_observations`
seam. It performs no persistence of its own beyond that one agent call, no
provider-model strategy work, no public API/activation/first-Brief handling.

Every caller-supplied input (Connect request/result, session, source profile,
concept model, concept disposition) is independently reopened and required to
equal the exact durable material before any observation is built, so a stale
or crossed handoff fails closed here rather than surfacing only inside the
agent's own re-verification.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ace.application.intelligence_agent import (
    AuthorizedObservationSetAdmission,
    IntelligenceAgent,
    IntelligenceAgentAttributionError,
    IntelligenceAgentStaleInput,
)
from ace.application.intelligence_agent_contracts import (
    AUTHORIZED_OBSERVATION_SET_VERSION,
    AuthorizedObservationSetV1,
    AuthorizedObservationV1,
    CanonicalJsonValueV1Alpha1,
    IntelligenceModelProposalV1,
)
from ace.application.intelligence_builder import (
    INTELLIGENCE_BUILDER_RECORD_SPACE,
    ONBOARDING_ARTIFACT_RECORD_KIND,
    IntelligenceBuilderArtifactNotFoundError,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionReplayConflict,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingStage,
    SourceProfileProposalV1,
    SourceSampleV1,
)
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectCapture,
)
from ace.application.ontology_agent_contracts import (
    ConceptEntityTypeV1,
    ConceptModelDispositionV1,
    ConceptModelProposalV1,
)
from ace.core.contracts import canonical_json
from ace.core.state import ResolvedApprovalReceiptV1
from core.engine.core.intelligence_activation_authority import verified_local_intelligence_owner
from core.engine.core.intelligence_builder_local_source_provider import (
    RecordedLocalSourceOptionProviderError,
    recorded_capture_json_leaves,
)
from core.engine.core.local_source_connect import (
    LocalSourceConnectRecordConflict,
    LocalSourceConnectRecordRepository,
    LocalSourceConnectRecordUnavailable,
)


class ObservationAdmissionError(RuntimeError):
    """Base failure deriving or admitting one exact authorized observation set."""


class ObservationAdmissionDenied(ObservationAdmissionError):
    """The caller is not the verified fixed local Intelligence owner."""


class ObservationAdmissionStaleInput(ObservationAdmissionError):
    """One caller-supplied input is not the exact current durable material."""


class ObservationAdmissionClosureError(ObservationAdmissionError):
    """Recorded captures and approved source-profile samples did not close 1:1."""


class ObservationAdmissionBoundError(ObservationAdmissionError):
    """One flattened observation attribute set exceeds the bounded canonical size."""


class ObservationAdmissionUnavailable(ObservationAdmissionError):
    """A required durable store could not be reached right now."""


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ObservationAdmissionStaleInput(f"{name} must include a timezone")
    return value.astimezone(UTC)


class _InertIntelligenceModelStrategy:
    """Structurally satisfies ``IntelligenceModelStrategy`` but must never run.

    ``IntelligenceAgent.admit_observations`` never calls ``strategy.propose``;
    this stub exists only to satisfy ``IntelligenceAgent.__init__``'s type and
    fails loudly if ever mistakenly invoked.
    """

    async def propose(self, **_: Any) -> IntelligenceModelProposalV1:
        raise AssertionError("admit_observations never calls the intelligence-model strategy")


class _InertCoreAuthorityResolver:
    """Structurally satisfies ``CoreAuthorityResolver`` but must never run.

    ``IntelligenceAgent.admit_observations`` never calls the authority
    resolver; this stub exists only to satisfy ``IntelligenceAgent.__init__``'s
    type and fails loudly if ever mistakenly invoked.
    """

    async def resolve_approval(self, **_: Any) -> ResolvedApprovalReceiptV1:
        raise AssertionError("admit_observations never resolves an approval receipt")

    async def resolve_grant(self, **_: Any) -> Any:
        raise AssertionError("admit_observations never resolves an authority grant")


def _current_reference(session: IntelligenceBuilderSessionRevisionV1, kind: OnboardingArtifactKind):
    return next((item for item in session.artifacts if item.artifact_kind is kind), None)


async def _require_current_session(
    sessions: IntelligenceBuilderSessionService,
    session: IntelligenceBuilderSessionRevisionV1,
    *,
    admitted_at: datetime,
) -> IntelligenceBuilderSessionRevisionV1:
    exact = IntelligenceBuilderSessionRevisionV1.model_validate(session.model_dump(mode="python"))
    try:
        latest = await sessions.load_latest(
            product_id=exact.product_id,
            session_id=exact.session_id,
            available_at=admitted_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise ObservationAdmissionUnavailable("Builder session storage is unavailable") from exc
    if latest is None or latest.revision_id != exact.revision_id or latest != exact:
        raise ObservationAdmissionStaleInput("onboarding session is not the exact current durable revision")
    return exact


async def _require_current_source_profile(
    sessions: IntelligenceBuilderSessionService,
    session: IntelligenceBuilderSessionRevisionV1,
    source_profile: SourceProfileProposalV1,
    *,
    admitted_at: datetime,
) -> SourceProfileProposalV1:
    exact = SourceProfileProposalV1.model_validate(source_profile.model_dump(mode="python"))
    reference = _current_reference(session, OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL)
    if (
        reference is None
        or reference.artifact_id != exact.proposal_id
        or reference.artifact_digest != exact.proposal_digest
        or exact.session_id != session.session_id
    ):
        raise ObservationAdmissionStaleInput("source-profile input is not the exact current session handoff")
    try:
        persisted = await sessions.load_artifact(
            product_id=session.product_id,
            reference=reference,
            artifact_type=SourceProfileProposalV1,
            available_at=admitted_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise ObservationAdmissionStaleInput("source-profile artifact is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise ObservationAdmissionUnavailable("Builder artifact storage is unavailable") from exc
    if persisted != exact:
        raise ObservationAdmissionStaleInput("source-profile body differs from exact durable material")
    return exact


async def _require_current_concept_context(
    sessions: IntelligenceBuilderSessionService,
    session: IntelligenceBuilderSessionRevisionV1,
    concept_model: ConceptModelProposalV1,
    concept_disposition: ConceptModelDispositionV1,
    *,
    admitted_at: datetime,
) -> tuple[ConceptModelProposalV1, ConceptModelDispositionV1]:
    model = ConceptModelProposalV1.model_validate(concept_model.model_dump(mode="python"))
    disposition = ConceptModelDispositionV1.model_validate(concept_disposition.model_dump(mode="python"))
    model_ref = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL)
    disposition_ref = _current_reference(session, OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION)
    if (
        model_ref is None
        or disposition_ref is None
        or model_ref.artifact_id != model.proposal_id
        or model_ref.artifact_digest != model.proposal_digest
        or disposition_ref.artifact_id != disposition.disposition_id
        or disposition_ref.artifact_digest != disposition.disposition_digest
        or disposition.proposal_id != model.proposal_id
        or disposition.proposal_digest != model.proposal_digest
        or model.session_id != session.session_id
        or model.correlation_id != session.correlation_id
    ):
        raise ObservationAdmissionStaleInput("concept-model input is not the exact current session handoff")
    try:
        persisted_model = await sessions.load_artifact(
            product_id=session.product_id,
            reference=model_ref,
            artifact_type=ConceptModelProposalV1,
            available_at=admitted_at,
        )
        persisted_disposition = await sessions.load_artifact(
            product_id=session.product_id,
            reference=disposition_ref,
            artifact_type=ConceptModelDispositionV1,
            available_at=admitted_at,
        )
    except IntelligenceBuilderArtifactNotFoundError as exc:
        raise ObservationAdmissionStaleInput("concept-model artifact is not durably present") from exc
    except IntelligenceBuilderSessionError as exc:
        raise ObservationAdmissionUnavailable("Builder artifact storage is unavailable") from exc
    if persisted_model != model or persisted_disposition != disposition:
        raise ObservationAdmissionStaleInput("concept-model body differs from exact durable material")
    return model, disposition


def _close_samples_to_captures(
    source_profile: SourceProfileProposalV1,
    result: LocalSourceConnectAuthorizationResult,
) -> tuple[tuple[SourceSampleV1, LocalSourceConnectCapture], ...]:
    """Bind every source sample to exactly one recorded capture, or fail closed.

    Matching uses only material already recorded on both sides: a sample's
    ``source_ref``/``evidence_digest`` are exactly a capture's
    ``source_uri``/``byte_digest`` (see ``RecordedLocalSourceOptionProvider``),
    so this never rereads a filesystem or calls a provider.
    """

    captures_by_key = {(capture.source_uri, capture.byte_digest): capture for capture in result.captures}
    if len(captures_by_key) != len(result.captures):
        raise ObservationAdmissionClosureError("recorded captures do not carry distinct exact source identities")

    pairs: list[tuple[SourceSampleV1, LocalSourceConnectCapture]] = []
    matched_captures: set[tuple[str, str]] = set()
    for sample in source_profile.samples:
        key = (sample.source_ref, sample.evidence_digest)
        capture = captures_by_key.get(key)
        if capture is None:
            raise ObservationAdmissionClosureError(
                "an approved source sample does not bind exactly one recorded capture"
            )
        if key in matched_captures:
            raise ObservationAdmissionClosureError("two approved source samples bind the same recorded capture")
        matched_captures.add(key)
        pairs.append((sample, capture))

    if len(matched_captures) != len(captures_by_key):
        raise ObservationAdmissionClosureError("recorded captures and approved source samples did not close one-to-one")
    if len({sample.source_ref for sample, _ in pairs}) < 2:
        raise ObservationAdmissionClosureError("observation admission requires at least two distinct sources")
    return tuple(pairs)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _parse_json_strict(value: str) -> Any:
    """Parse finite JSON while rejecting duplicate object keys (host-local, no
    ``ace.intelligence`` import)."""

    return json.loads(value, object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)


def _flattened_attributes(capture: LocalSourceConnectCapture) -> dict[str, Any]:
    try:
        payload = _parse_json_strict(capture.structured_payload_json)
    except ValueError as exc:
        raise ObservationAdmissionClosureError("recorded capture payload failed exact strict JSON parsing") from exc
    try:
        leaves = recorded_capture_json_leaves(payload)
    except RecordedLocalSourceOptionProviderError as exc:
        raise ObservationAdmissionBoundError(str(exc)) from exc
    attributes: dict[str, Any] = {}
    for pointer, value in leaves.items():
        key = pointer.removeprefix("/")
        attributes[key] = value
    if len(attributes) != len(leaves):
        raise ObservationAdmissionClosureError(
            "two distinct captured pointers collapsed onto the same stripped attribute key"
        )
    return attributes


def _canonical_attributes_value(attributes: dict[str, Any]) -> CanonicalJsonValueV1Alpha1:
    # The public value contract owns the bounded canonical size; the host never
    # restates that bound, it only names the fail-closed reason.
    try:
        return CanonicalJsonValueV1Alpha1(value_json=canonical_json(attributes))
    except ValueError as exc:
        raise ObservationAdmissionBoundError(
            "flattened observation attributes exceed the bounded canonical size"
        ) from exc


def _require_admitted_at_not_before_captures(
    admitted_at: datetime,
    pairs: tuple[tuple[SourceSampleV1, LocalSourceConnectCapture], ...],
) -> None:
    for _, capture in pairs:
        observed_at = _aware(capture.selection.observed_at, name="capture observed_at")
        if admitted_at < observed_at:
            raise ObservationAdmissionStaleInput("admitted_at is before one recorded capture's observed_at")


_MAX_UTC_READ_CUTOFF = datetime.max.replace(tzinfo=UTC)


async def _existing_observation_set(
    sessions: IntelligenceBuilderSessionService,
    session: IntelligenceBuilderSessionRevisionV1,
) -> AuthorizedObservationSetV1 | None:
    """Read-only singleton check: is an initial observation set already durable?

    Scans the Builder artifact record space directly rather than
    ``session.artifacts``, because admitting observations never advances the
    session's stage/artifact list. The scan reads every currently durable
    Builder observation artifact for this session as of the maximum UTC
    cutoff -- never the caller's proposed ``admitted_at`` -- so a retry whose
    admitted_at is earlier than an already-durable set's admitted_at still
    observes that durable set instead of racing past it into a second one.
    Zero matches permits creation; exactly one exact match is a replay the
    caller reopens through the agent; more than one match fails closed as a
    durable conflict this host adapter must never silently ignore.
    """

    try:
        records = await sessions.store.read_as_of(
            product_id=session.product_id,
            record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
            record_kind=ONBOARDING_ARTIFACT_RECORD_KIND,
            available_at=_MAX_UTC_READ_CUTOFF,
        )
    except Exception as exc:
        raise ObservationAdmissionUnavailable("Builder artifact storage is unavailable") from exc

    matches: list[AuthorizedObservationSetV1] = []
    for record in records:
        if (
            record.product_id != session.product_id
            or record.record_space != INTELLIGENCE_BUILDER_RECORD_SPACE
            or record.record_kind != ONBOARDING_ARTIFACT_RECORD_KIND
            or record.payload_contract != AUTHORIZED_OBSERVATION_SET_VERSION
        ):
            continue
        if record.payload.get("session_id") != session.session_id:
            continue
        try:
            candidate = AuthorizedObservationSetV1.model_validate(record.payload, strict=False)
        except ValidationError as exc:
            raise ObservationAdmissionUnavailable(
                "a persisted initial observation set failed exact revalidation"
            ) from exc
        artifact_id = str(candidate.observation_set_id)
        artifact_digest = str(candidate.observation_set_digest)
        if (
            record.record_key != artifact_id
            or record.as_of != candidate.admitted_at
            or record.available_at != candidate.admitted_at
        ):
            raise ObservationAdmissionUnavailable(
                "a persisted initial observation set failed exact envelope verification"
            )
        reference = OnboardingArtifactReferenceV1(
            artifact_kind=OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
        )
        try:
            reopened = await sessions.load_artifact(
                product_id=session.product_id,
                reference=reference,
                artifact_type=AuthorizedObservationSetV1,
                available_at=candidate.admitted_at,
            )
        except IntelligenceBuilderArtifactNotFoundError as exc:
            raise ObservationAdmissionUnavailable(
                "a persisted initial observation set is not durably reopenable"
            ) from exc
        except IntelligenceBuilderSessionError as exc:
            raise ObservationAdmissionUnavailable("Builder artifact storage is unavailable") from exc
        if reopened != candidate:
            raise ObservationAdmissionUnavailable(
                "a persisted initial observation set failed exact envelope revalidation"
            )
        matches.append(reopened)
    if len(matches) > 1:
        raise ObservationAdmissionClosureError(
            "more than one initial observation set is already recorded for this session"
        )
    return matches[0] if matches else None


def _chosen_entity_type(concept_model: ConceptModelProposalV1) -> ConceptEntityTypeV1:
    """Deterministically pick one declared entity type for every observation.

    Rule: the lexicographically smallest ``type_id`` among
    ``concept_model.entity_types`` (already sorted ascending by ``type_id`` by
    the contract's own validator, so this is simply the first entry). This
    bounded slice does not infer a different entity type per sample.
    """

    return concept_model.entity_types[0]


def _build_observation(
    *,
    sample: SourceSampleV1,
    capture: LocalSourceConnectCapture,
    source_profile: SourceProfileProposalV1,
    entity_type: ConceptEntityTypeV1,
    admitted_at: datetime,
) -> AuthorizedObservationV1:
    attributes = _flattened_attributes(capture)
    declared_attribute_ids = {attribute.attribute_id for attribute in entity_type.attributes}
    unknown_fields = tuple(sorted(declared_attribute_ids - set(attributes)))
    try:
        return AuthorizedObservationV1(
            source_profile_proposal_id=str(source_profile.proposal_id),
            source_profile_proposal_digest=str(source_profile.proposal_digest),
            source_sample_id=str(sample.sample_id),
            source_sample_digest=str(sample.sample_digest),
            source_ref=sample.source_ref,
            evidence_digest=sample.evidence_digest,
            subject_ref=capture.selection.entity_ref,
            entity_type_id=entity_type.type_id,
            attributes=_canonical_attributes_value(attributes),
            observed_at=capture.selection.observed_at,
            admitted_at=admitted_at,
            as_of=admitted_at,
            confidence=1.0,
            disagrees_with_observation_ids=(),
            unknown_fields=unknown_fields,
        )
    except ValidationError as exc:
        raise ObservationAdmissionClosureError("one derived observation failed exact contract validation") from exc


async def admit_local_source_observations(
    *,
    request: LocalSourceConnectAuthorizationRequest,
    result: LocalSourceConnectAuthorizationResult,
    session: IntelligenceBuilderSessionRevisionV1,
    source_profile: SourceProfileProposalV1,
    concept_model: ConceptModelProposalV1,
    concept_disposition: ConceptModelDispositionV1,
    user: dict,
    admitted_at: datetime,
    repository: LocalSourceConnectRecordRepository,
    sessions: IntelligenceBuilderSessionService,
) -> AuthorizedObservationSetAdmission:
    """Derive and admit one exact ``AuthorizedObservationSetV1`` from recorded Connect captures.

    Persistence happens exclusively inside
    :meth:`IntelligenceAgent.admit_observations`; this function never writes
    an artifact directly. Every input is independently reopened and required
    to equal exact durable material before any observation is built.
    """

    try:
        _, product_id = verified_local_intelligence_owner(user)
    except Exception as exc:
        raise ObservationAdmissionDenied("verified caller is not the local Intelligence owner") from exc
    if product_id != session.product_id:
        raise ObservationAdmissionDenied("verified local owner does not match the exact current session product")

    admitted_at = _aware(admitted_at, name="admitted_at")

    exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
    exact_result = LocalSourceConnectAuthorizationResult.model_validate(result.model_dump(mode="python"))
    try:
        replayed = await repository.replay(exact_request)
    except LocalSourceConnectRecordConflict as exc:
        raise ObservationAdmissionStaleInput("recorded Connect authorization crossed its exact identity") from exc
    except LocalSourceConnectRecordUnavailable as exc:
        raise ObservationAdmissionUnavailable("Connect record storage is unavailable") from exc
    if replayed is None or replayed != exact_result:
        raise ObservationAdmissionStaleInput("recorded Connect transaction did not reopen the exact submitted result")

    exact_session = await _require_current_session(sessions, session, admitted_at=admitted_at)
    if exact_session.stage is not OnboardingStage.CONCEPT_MODEL_APPROVED:
        raise ObservationAdmissionStaleInput("onboarding session is not at the exact concept_model_approved stage")
    exact_profile = await _require_current_source_profile(
        sessions, exact_session, source_profile, admitted_at=admitted_at
    )
    exact_model, exact_disposition = await _require_current_concept_context(
        sessions, exact_session, concept_model, concept_disposition, admitted_at=admitted_at
    )

    pairs = _close_samples_to_captures(exact_profile, exact_result)
    _require_admitted_at_not_before_captures(admitted_at, pairs)
    entity_type = _chosen_entity_type(exact_model)
    observations = tuple(
        _build_observation(
            sample=sample,
            capture=capture,
            source_profile=exact_profile,
            entity_type=entity_type,
            admitted_at=admitted_at,
        )
        for sample, capture in pairs
    )

    try:
        observation_set = AuthorizedObservationSetV1(
            session_id=exact_session.session_id,
            correlation_id=exact_session.correlation_id,
            source_profile_proposal_id=str(exact_profile.proposal_id),
            source_profile_proposal_digest=str(exact_profile.proposal_digest),
            observations=observations,
            closure_complete=True,
            admitted_at=admitted_at,
        )
    except ValidationError as exc:
        raise ObservationAdmissionClosureError(
            "the derived initial observation set failed exact contract validation"
        ) from exc

    existing = await _existing_observation_set(sessions, exact_session)
    if existing is not None and existing != observation_set:
        raise ObservationAdmissionClosureError(
            "a different initial observation set is already durably recorded for this session"
        )

    agent = IntelligenceAgent(
        sessions=sessions,
        authority=_InertCoreAuthorityResolver(),
        strategy=_InertIntelligenceModelStrategy(),
    )
    try:
        return await agent.admit_observations(
            exact_session,
            concept_model=exact_model,
            concept_disposition=exact_disposition,
            source_profile=exact_profile,
            observations=observation_set,
            occurred_at=admitted_at,
        )
    except IntelligenceAgentAttributionError as exc:
        # Preserved distinctly, not weakened: this is IntelligenceAgent's own
        # attribution re-verification failing closed, wrapped only so callers
        # of this host adapter see one consistent exception hierarchy.
        raise ObservationAdmissionClosureError(str(exc)) from exc
    except IntelligenceAgentStaleInput as exc:
        raise ObservationAdmissionStaleInput(str(exc)) from exc
    except IntelligenceBuilderSessionReplayConflict as exc:
        raise ObservationAdmissionClosureError(
            "initial observation set identity already binds different exact material"
        ) from exc
    except IntelligenceBuilderSessionError as exc:
        raise ObservationAdmissionUnavailable("Builder artifact storage is unavailable") from exc


__all__ = [
    "ObservationAdmissionBoundError",
    "ObservationAdmissionClosureError",
    "ObservationAdmissionDenied",
    "ObservationAdmissionError",
    "ObservationAdmissionStaleInput",
    "ObservationAdmissionUnavailable",
    "admit_local_source_observations",
]
