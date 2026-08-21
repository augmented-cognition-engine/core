"""Production bridge: one exact authorized local Connect result into the
Builder's Connection Agent source-scope proposal and approved connect
transition (PI13 addendum 9).

This module closes exactly one seam: it never reads a filesystem or takes
another snapshot. It reopens one already-authorized, durably recorded
:class:`LocalSourceConnectAuthorizationResult` through
:class:`LocalSourceConnectRecordRepository`, requires the caller-supplied
result to match that recorded material exactly, and adapts only that exact
material into a :class:`RegisteredSourceOptionProvider` for the existing
:class:`ConnectionAgent`. Its catalog is not a universal connector catalog:
every option and sample it can ever produce is bounded to the captures
already recorded under one exact authorization, carries no credential,
remote source, scheduling, or write effect, and never becomes authoritative
connector configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from ace.application.intelligence_builder import (
    ConnectionAgent,
    ConnectionAgentError,
    ConnectionAgentOutcome,
    ConnectionAgentStaleProposal,
    ConnectionScopeAdmission,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingStage,
    OnboardingTransitionAuthority,
    SourceOptionCatalogV1,
    SourceProfileProposalV1,
    SourceScopeProposalV1,
    SourceScopeSelectionV1,
)
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectCapture,
)
from ace.core.records import ImmutableRecordStore
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1, ResolvedAuthorityGrantV1
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    RecordedIntelligenceActivationAuthority,
    verified_local_intelligence_owner,
)
from core.engine.core.intelligence_builder_disposition_authority import RecordedIntelligenceBuilderDispositionAuthority
from core.engine.core.intelligence_builder_local_source_provider import (
    RecordedLocalSourceOptionProvider,
    RecordedLocalSourceOptionProviderConflict,
    RecordedLocalSourceOptionProviderDenied,
    RecordedLocalSourceOptionProviderError,
)
from core.engine.core.local_source_connect import (
    LocalSourceConnectRecordConflict,
    LocalSourceConnectRecordRepository,
    LocalSourceConnectRecordUnavailable,
)

# Mirrors ``SourceScopeProposalV1.selections``' existing 32-item bound: this
# bridge proposes exactly one selection per recorded capture, so it must fail
# closed before the Builder contract would.
MAX_SOURCE_SCOPE_SELECTIONS = 32


class LocalSourceConnectSourceProgressionError(RuntimeError):
    """Base failure bridging one authorized local Connect result to the Builder."""


class LocalSourceConnectSourceProgressionDenied(LocalSourceConnectSourceProgressionError):
    """The verified caller or the recorded material cannot support this bridge."""


class LocalSourceConnectSourceProgressionConflict(LocalSourceConnectSourceProgressionError):
    """Submitted or durable material crossed or changed exact reviewed bindings."""


class LocalSourceConnectSourceProgressionNotFound(LocalSourceConnectSourceProgressionError):
    """No authorized local Connect result is durably recorded for this request."""


class LocalSourceConnectSourceProgressionUnavailable(LocalSourceConnectSourceProgressionError):
    """A required durable store could not be reached right now."""


def _verified_owner(user: dict) -> tuple[str, str]:
    try:
        return verified_local_intelligence_owner(user)
    except Exception as exc:
        raise LocalSourceConnectSourceProgressionDenied("verified caller is not the local Intelligence owner") from exc


def _captured_sources(result: LocalSourceConnectAuthorizationResult) -> tuple[LocalSourceConnectCapture, ...]:
    """Return the exact captures a source-scope proposal may bridge, or fail closed."""

    captures = result.captures
    if not captures:
        raise LocalSourceConnectSourceProgressionDenied(
            "no captured local sources are available for this exact authorization"
        )
    if len(captures) > MAX_SOURCE_SCOPE_SELECTIONS:
        raise LocalSourceConnectSourceProgressionDenied(
            f"recorded captures exceed the {MAX_SOURCE_SCOPE_SELECTIONS}-selection Builder bound"
        )
    if len({str(capture.capture_id) for capture in captures}) != len(captures):
        raise LocalSourceConnectSourceProgressionConflict("recorded captures do not carry unique exact identities")
    if len({str(capture.capture_id) for capture in captures}) < 2:
        raise LocalSourceConnectSourceProgressionDenied(
            "fewer than two distinct exact sources were captured for this authorization"
        )
    return captures


def _recorded_provider(
    result: LocalSourceConnectAuthorizationResult,
    *,
    authorized_at: datetime,
) -> RecordedLocalSourceOptionProvider:
    """Adapt one exact recorded result into the shared bounded source-option provider.

    This bridge never derives its own catalog or field-profile logic: it
    delegates entirely to ``RecordedLocalSourceOptionProvider`` (PI13 WS3),
    which is bounded to exactly the captures this recorded result carries and
    performs no I/O of its own.
    """

    _captured_sources(result)
    try:
        return RecordedLocalSourceOptionProvider(result=result, authorized_at=authorized_at)
    except RecordedLocalSourceOptionProviderDenied as exc:
        raise LocalSourceConnectSourceProgressionDenied(str(exc)) from exc
    except RecordedLocalSourceOptionProviderConflict as exc:
        raise LocalSourceConnectSourceProgressionConflict(str(exc)) from exc
    except RecordedLocalSourceOptionProviderError as exc:  # pragma: no cover - defensive
        raise LocalSourceConnectSourceProgressionDenied(str(exc)) from exc


async def _reopen_authorized_result(
    *,
    repository: LocalSourceConnectRecordRepository,
    request: LocalSourceConnectAuthorizationRequest,
    result: LocalSourceConnectAuthorizationResult,
) -> LocalSourceConnectAuthorizationResult:
    """Reopen the exact durable Connect result and require it match ``result``.

    This never touches the filesystem and never performs another snapshot or
    read: it only reopens what ``LocalSourceConnectRecordRepository`` already
    durably recorded for ``request``.
    """

    try:
        exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
        exact_result = LocalSourceConnectAuthorizationResult.model_validate(result.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "Connect authorization material failed exact revalidation"
        ) from exc

    try:
        reopened = await repository.replay(exact_request)
    except LocalSourceConnectRecordConflict as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "recorded Connect authorization crossed its exact identity"
        ) from exc
    except LocalSourceConnectRecordUnavailable as exc:
        raise LocalSourceConnectSourceProgressionUnavailable("Connect record storage is unavailable") from exc
    if reopened is None:
        raise LocalSourceConnectSourceProgressionNotFound(
            "no authorized local Connect result is durably recorded for this exact authorization"
        )
    if reopened != exact_result:
        raise LocalSourceConnectSourceProgressionConflict(
            "caller-supplied Connect result does not match the exact recorded material"
        )
    return reopened


class _UnreachableProposalApprovalAuthority(CoreAuthorityResolver):
    """Authority stand-in for scope proposal; ``propose_scope`` never resolves approval or grants."""

    async def resolve_approval(self, **kwargs) -> ResolvedApprovalReceiptV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: source-scope proposal never resolves approval or grant evidence")

    async def resolve_grant(self, **kwargs) -> ResolvedAuthorityGrantV1:  # pragma: no cover - unreachable
        raise AssertionError("unreachable: source-scope proposal never resolves approval or grant evidence")


_UNREACHABLE_PROPOSAL_AUTHORITY = _UnreachableProposalApprovalAuthority()


@dataclass(frozen=True, slots=True)
class LocalSourceConnectScopeProgressionRuntime:
    """Production wiring for the local Connect-to-Builder source-scope bridge."""

    records: ImmutableRecordStore
    repository: LocalSourceConnectRecordRepository
    grants: CoreAuthorityResolver


def local_source_connect_scope_progression_runtime() -> LocalSourceConnectScopeProgressionRuntime:
    """Build the production runtime over the primary durable stores."""

    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return LocalSourceConnectScopeProgressionRuntime(
        records=records,
        repository=LocalSourceConnectRecordRepository(records),
        grants=RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_state),
    )


def _current_artifact(
    session: IntelligenceBuilderSessionRevisionV1,
    kind: OnboardingArtifactKind,
):
    return next((item for item in session.artifacts if item.artifact_kind is kind), None)


async def _reconstruct_scope_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    product_id: str,
    actor_ref: str,
    catalog: SourceOptionCatalogV1,
    selections: tuple[SourceScopeSelectionV1, ...],
    occurred_at: datetime,
) -> ConnectionScopeAdmission:
    """Reopen the already-durable exact one-step propose result for a retry.

    Only reached when the current durable session revision proves this exact
    one-step transition already happened (its ``prior_revision`` fields match
    ``session`` exactly, and its stage/authority match what ``propose_scope``
    itself would have produced). It never calls ``sessions.advance`` again: it
    only reopens durable material through ``reload_admission``/``load_artifact``
    and reconfirms (via ``persist_artifact``'s own idempotent replay) that the
    exact same artifact identity is already bound.
    """

    reference = _current_artifact(latest, OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL)
    if reference is None:
        raise LocalSourceConnectSourceProgressionConflict(
            "Builder session advanced past this proposal without a durable source scope proposal"
        )
    try:
        persisted_proposal = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=SourceScopeProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable source scope proposal could not be exactly reopened"
        ) from exc
    expected_selections = tuple(sorted(selections, key=lambda item: item.option_id))
    if (
        persisted_proposal.session_id != session.session_id
        or persisted_proposal.goal_ref != session.goal_ref
        or persisted_proposal.catalog_id != str(catalog.catalog_id)
        or persisted_proposal.catalog_digest != str(catalog.catalog_digest)
        or persisted_proposal.selections != expected_selections
        or persisted_proposal.created_at != occurred_at
    ):
        raise LocalSourceConnectSourceProgressionConflict(
            "durable source scope proposal does not match this exact retried recorded material"
        )
    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != actor_ref
        or latest.product_id != product_id
        or latest.session_id != session.session_id
    ):
        raise LocalSourceConnectSourceProgressionConflict(
            "durable propose retry crossed its exact transition time, actor, or chain"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        proposal_admission = await sessions.persist_artifact(product_id=product_id, artifact=persisted_proposal)
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable propose retry could not be exactly reopened"
        ) from exc
    return ConnectionScopeAdmission(
        proposal=persisted_proposal,
        proposal_admission=proposal_admission,
        session=session_admission,
    )


async def _reconstruct_connect_retry(
    *,
    sessions: IntelligenceBuilderSessionService,
    latest: IntelligenceBuilderSessionRevisionV1,
    session: IntelligenceBuilderSessionRevisionV1,
    product_id: str,
    actor_ref: str,
    exact_result: LocalSourceConnectAuthorizationResult,
    request: LocalSourceConnectAuthorizationRequest,
    proposal: SourceScopeProposalV1,
    approval_receipt_ref: str,
    occurred_at: datetime,
) -> ConnectionAgentOutcome:
    """Reopen the already-durable exact one-step ``SOURCES_READY`` connect result.

    Only reached when the current durable session revision proves this exact
    one-step transition already happened: its ``prior_revision`` fields match
    ``session`` exactly, its stage is ``SOURCES_READY``, and its bound
    approval receipt matches. It never calls ``sessions.advance`` again and
    never resolves or mints another approval.
    """

    if latest.approval_receipt_ref != approval_receipt_ref:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable connect result is bound to a different approval receipt"
        )
    scope_reference = _current_artifact(session, OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL)
    if (
        scope_reference is None
        or scope_reference.artifact_id != proposal.proposal_id
        or scope_reference.artifact_digest != proposal.proposal_digest
    ):
        raise LocalSourceConnectSourceProgressionConflict(
            "supplied source scope proposal is not the exact current session handoff"
        )
    try:
        persisted_scope = await sessions.load_artifact(
            product_id=product_id,
            reference=scope_reference,
            artifact_type=SourceScopeProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable source scope proposal could not be exactly reopened"
        ) from exc
    if persisted_scope != proposal:
        raise LocalSourceConnectSourceProgressionConflict(
            "supplied source scope proposal differs from the exact durable handoff"
        )
    provider = _recorded_provider(exact_result, authorized_at=request.authorized_at)
    catalog = await provider.catalog()
    if proposal.catalog_id != str(catalog.catalog_id) or proposal.catalog_digest != str(catalog.catalog_digest):
        raise LocalSourceConnectSourceProgressionConflict(
            "supplied source scope proposal does not match the exact recorded source catalog"
        )
    reference = _current_artifact(latest, OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL)
    if reference is None:
        raise LocalSourceConnectSourceProgressionConflict(
            "Builder session advanced to sources_ready without a durable source profile proposal"
        )
    try:
        persisted_profile = await sessions.load_artifact(
            product_id=product_id,
            reference=reference,
            artifact_type=SourceProfileProposalV1,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable source profile proposal could not be exactly reopened"
        ) from exc
    if (
        persisted_profile.session_id != session.session_id
        or persisted_profile.scope_proposal_id != str(proposal.proposal_id)
        or persisted_profile.scope_proposal_digest != str(proposal.proposal_digest)
        or persisted_profile.created_at != occurred_at
    ):
        raise LocalSourceConnectSourceProgressionConflict(
            "durable source profile proposal does not match this exact retried recorded material"
        )
    if (
        latest.occurred_at != occurred_at
        or latest.transition_actor_ref != actor_ref
        or latest.product_id != product_id
        or latest.session_id != session.session_id
    ):
        raise LocalSourceConnectSourceProgressionConflict(
            "durable connect retry crossed its exact transition time, actor, or chain"
        )
    try:
        session_admission = await sessions.reload_admission(latest)
        profile_admission = await sessions.persist_artifact(product_id=product_id, artifact=persisted_profile)
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "durable connect retry could not be exactly reopened"
        ) from exc
    return ConnectionAgentOutcome(
        session=session_admission,
        profile=persisted_profile,
        profile_admission=profile_admission,
        blocked_reason=None,
    )


async def propose_local_source_connect_scope(
    *,
    request: LocalSourceConnectAuthorizationRequest,
    result: LocalSourceConnectAuthorizationResult,
    session: IntelligenceBuilderSessionRevisionV1,
    user: dict,
    runtime: LocalSourceConnectScopeProgressionRuntime,
    occurred_at: datetime,
) -> ConnectionScopeAdmission:
    """Propose the Connection Agent's source scope from one exact recorded Connect result.

    Reloads the exact current ``GOAL_SELECTED``/``SOURCES_CONNECTING`` Builder
    session, verifies the fixed local owner, and builds one read-only,
    bounded-sample selection per recorded capture before calling
    ``ConnectionAgent.propose_scope``. It never calls ``sessions.advance``
    directly.
    """

    actor_ref, product_id = _verified_owner(user)
    if session.product_id != product_id:
        raise LocalSourceConnectSourceProgressionDenied("Builder session crossed verified local-owner scope")

    exact_result = await _reopen_authorized_result(repository=runtime.repository, request=request, result=result)

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise LocalSourceConnectSourceProgressionConflict("Builder session is stale; reload before proposing scope")

    provider = _recorded_provider(exact_result, authorized_at=request.authorized_at)
    catalog = await provider.catalog()
    selections = tuple(
        SourceScopeSelectionV1(
            option_id=option.option_id,
            permissions=option.permission_options,
            scopes=option.scope_options,
            effects=option.allowed_effects,
            sample_records=option.maximum_sample_records,
        )
        for option in catalog.options
    )

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.SOURCES_CONNECTING
        and latest.transition_authority is OnboardingTransitionAuthority.AGENT_PROPOSAL
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_scope_retry(
            sessions=sessions,
            latest=latest,
            session=session,
            product_id=product_id,
            actor_ref=actor_ref,
            catalog=catalog,
            selections=selections,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise LocalSourceConnectSourceProgressionConflict("Builder session is stale; reload before proposing scope")
    if latest.stage not in {OnboardingStage.GOAL_SELECTED, OnboardingStage.SOURCES_CONNECTING}:
        raise LocalSourceConnectSourceProgressionConflict(
            "Builder session is not at the exact stage to propose source scope"
        )

    agent = ConnectionAgent(sessions=sessions, authority=_UNREACHABLE_PROPOSAL_AUTHORITY, provider=provider)

    try:
        return await agent.propose_scope(
            latest,
            catalog=catalog,
            selections=selections,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
    except ConnectionAgentStaleProposal as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "recorded source catalog changed before scope proposal"
        ) from exc
    except ConnectionAgentError as exc:
        raise LocalSourceConnectSourceProgressionConflict("source scope proposal failed exact validation") from exc


async def connect_local_source_connect_scope(
    *,
    request: LocalSourceConnectAuthorizationRequest,
    result: LocalSourceConnectAuthorizationResult,
    session: IntelligenceBuilderSessionRevisionV1,
    proposal: SourceScopeProposalV1,
    approval_receipt_ref: str,
    user: dict,
    runtime: LocalSourceConnectScopeProgressionRuntime,
    occurred_at: datetime,
) -> ConnectionAgentOutcome:
    """Approve-connect the exact current ``SOURCES_CONNECTING`` source scope.

    Reloads the exact current ``SOURCES_CONNECTING`` revision, uses
    ``RecordedIntelligenceBuilderDispositionAuthority`` plus the existing
    grant resolver to resolve the separately recorded approval receipt, and
    calls ``ConnectionAgent.connect``. This operation performs no snapshot or
    filesystem read of its own and never mints the approval it resolves.
    """

    actor_ref, product_id = _verified_owner(user)
    if session.product_id != product_id:
        raise LocalSourceConnectSourceProgressionDenied("Builder session crossed verified local-owner scope")

    exact_result = await _reopen_authorized_result(repository=runtime.repository, request=request, result=result)

    sessions = IntelligenceBuilderSessionService(store=runtime.records)
    try:
        latest = await sessions.load_latest(
            product_id=product_id,
            session_id=session.session_id,
            available_at=occurred_at,
        )
    except IntelligenceBuilderSessionError as exc:
        raise LocalSourceConnectSourceProgressionUnavailable("Builder session storage is unavailable") from exc
    if latest is None:
        raise LocalSourceConnectSourceProgressionConflict("Builder session is stale; reload before approved connect")

    is_exact_current = latest.revision_id == session.revision_id and latest.revision_digest == session.revision_digest
    is_exact_retry = (
        latest.prior_revision_id == session.revision_id
        and latest.prior_revision_digest == session.revision_digest
        and latest.stage is OnboardingStage.SOURCES_READY
        and latest.transition_authority is OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION
    )
    if is_exact_retry and not is_exact_current:
        return await _reconstruct_connect_retry(
            sessions=sessions,
            latest=latest,
            session=session,
            product_id=product_id,
            actor_ref=actor_ref,
            exact_result=exact_result,
            request=request,
            proposal=proposal,
            approval_receipt_ref=approval_receipt_ref,
            occurred_at=occurred_at,
        )
    if not is_exact_current:
        raise LocalSourceConnectSourceProgressionConflict("Builder session is stale; reload before approved connect")
    if latest.stage is not OnboardingStage.SOURCES_CONNECTING:
        raise LocalSourceConnectSourceProgressionConflict(
            "Builder session is not at the exact stage for approved connect"
        )

    provider = _recorded_provider(exact_result, authorized_at=request.authorized_at)
    authority = RecordedIntelligenceBuilderDispositionAuthority(records=runtime.records, grants=runtime.grants)
    agent = ConnectionAgent(sessions=sessions, authority=authority, provider=provider)

    try:
        return await agent.connect(
            latest,
            proposal=proposal,
            approval_receipt_ref=approval_receipt_ref,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
    except ConnectionAgentStaleProposal as exc:
        raise LocalSourceConnectSourceProgressionConflict(
            "source scope proposal is not the exact current session handoff"
        ) from exc
    except ConnectionAgentError as exc:
        raise LocalSourceConnectSourceProgressionConflict("approved connect failed exact validation") from exc


__all__ = [
    "MAX_SOURCE_SCOPE_SELECTIONS",
    "LocalSourceConnectScopeProgressionRuntime",
    "LocalSourceConnectSourceProgressionConflict",
    "LocalSourceConnectSourceProgressionDenied",
    "LocalSourceConnectSourceProgressionError",
    "LocalSourceConnectSourceProgressionNotFound",
    "LocalSourceConnectSourceProgressionUnavailable",
    "connect_local_source_connect_scope",
    "local_source_connect_scope_progression_runtime",
    "propose_local_source_connect_scope",
]
