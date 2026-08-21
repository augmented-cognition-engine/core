"""HTTP transport for preparing and starting one personal Intelligence build."""

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    IntelligenceActivationApprovalConflict,
    IntelligenceActivationApprovalDenied,
    IntelligenceActivationApprovalResultV1Alpha1,
    IntelligenceActivationApprovalUnavailable,
    IntelligenceActivationApproveRequestV1Alpha1,
    IntelligenceBuilderSessionRevisionV1,
    IntelligenceBuildRetryRequestV1Alpha1,
    IntelligenceBuildSessionAssociateRequestV1Alpha1,
    IntelligenceBuildSessionAssociationResultV1Alpha1,
    approve_intelligence_activation,
    associate_intelligence_build_session,
    retry_intelligence_build_session,
)
from core.engine.core.intelligence_build import (
    IntelligenceBuildContractConflict,
    IntelligenceBuildDenied,
    IntelligenceBuildHttpRuntime,
    IntelligenceBuildResultV1,
    IntelligenceBuildStartV1Alpha2,
    IntelligenceBuildUnauthenticated,
    IntelligenceBuildUnavailable,
    intelligence_build_runtime,
    start_intelligence_build,
)
from core.engine.core.intelligence_build_plan import (
    BoundIntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanBindRequestV1Alpha1,
    IntelligenceBuildPlanConflict,
    IntelligenceBuildPlanHttpRuntime,
    IntelligenceBuildPlanNotFound,
    IntelligenceBuildPlanPrepareV1Alpha2,
    IntelligenceBuildPlanUnauthenticated,
    IntelligenceBuildPlanUnavailable,
    IntelligenceBuildPlanV1Alpha3,
    IntelligenceBuildProjectionRequestV1,
    IntelligenceSystemProjectionV1Alpha1,
    bind_intelligence_build_plan,
    intelligence_build_plan_runtime,
    prepare_intelligence_build_plan,
    project_intelligence_build_plan,
)
from core.engine.core.intelligence_build_resource_state import (
    IntelligenceBuildResourceStateConflict,
    IntelligenceBuildResourceStateDenied,
    IntelligenceBuildResourceStateNotFound,
    IntelligenceBuildResourceStateRequestV1,
    IntelligenceBuildResourceStateRuntime,
    IntelligenceBuildResourceStateUnauthenticated,
    IntelligenceBuildResourceStateUnavailable,
    intelligence_build_resource_state_runtime,
    project_intelligence_build_resource_state,
)
from core.engine.core.intelligence_builder_activation_plan import (
    DomainActivationCommitReferenceV1Alpha2,
    DomainActivationPlanApproveRequestV1Alpha1,
    DomainActivationPlanCoordinationConflict,
    DomainActivationPlanCoordinationDenied,
    DomainActivationPlanCoordinationNotFound,
    DomainActivationPlanCoordinationUnavailable,
    DomainActivationPlanPrepareRequestV1Alpha1,
    IntelligenceActivationPlanV1Alpha2,
    IntelligenceBuilderActivationPlanRuntime,
    IntelligenceBuilderActivationResultV1Alpha1,
    IntelligenceBuilderPlanActivateRequestV1Alpha1,
    activate_intelligence_builder_plan,
    approve_domain_activation_plan,
    intelligence_builder_activation_plan_runtime,
    prepare_domain_activation_plan,
)
from core.engine.core.intelligence_builder_concept_progression import (
    ConceptModelProposeRequestV1Alpha1,
    IntelligenceBuilderConceptProgressionConflict,
    IntelligenceBuilderConceptProgressionDenied,
    IntelligenceBuilderConceptProgressionRuntime,
    IntelligenceBuilderConceptProgressionUnavailable,
    approve_intelligence_builder_concept_model,
    intelligence_builder_concept_progression_runtime,
    propose_intelligence_builder_concept_model,
)
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderDispositionApprovalConflict,
    BuilderDispositionApprovalDenied,
    BuilderDispositionApprovalUnavailable,
    BuilderIntelligenceModelApproveRequestV1Alpha1,
    approve_builder_source_scope,
)
from core.engine.core.intelligence_builder_host_contracts import (
    BuilderConceptModelApproveResultV1Alpha1,
    BuilderConceptModelProposeResultV1Alpha1,
    BuilderFirstBriefPrepareResultV1Alpha1,
    BuilderIntelligenceModelApproveResultV1Alpha1,
    BuilderIntelligenceModelProposeResultV1Alpha1,
    BuilderSourceScopeApproveConnectRequestV1Alpha1,
    BuilderSourceScopeApproveConnectResultV1Alpha1,
    BuilderSourceScopeProposeRequestV1Alpha1,
    BuilderSourceScopeProposeResultV1Alpha1,
)
from core.engine.core.intelligence_builder_intelligence_progression import (
    FirstBriefPrepareRequestV1Alpha1,
    IntelligenceBuilderIntelligenceProgressionConflict,
    IntelligenceBuilderIntelligenceProgressionDenied,
    IntelligenceBuilderIntelligenceProgressionRuntime,
    IntelligenceBuilderIntelligenceProgressionUnavailable,
    IntelligenceModelProposeRequestV1Alpha1,
    approve_intelligence_builder_intelligence_model,
    intelligence_builder_intelligence_progression_runtime,
    prepare_intelligence_builder_first_brief,
    propose_intelligence_builder_intelligence_model,
)
from core.engine.core.local_first_run_bootstrap import (
    LocalFirstRunAuthorityMissing,
    LocalFirstRunBootstrapConflict,
    LocalFirstRunBootstrapDenied,
    LocalFirstRunBootstrapRuntime,
    LocalFirstRunBootstrapUnavailable,
    LocalFirstRunBuildAuthorityV1Alpha1,
    bootstrap_local_first_run_build_authority,
    local_first_run_bootstrap_runtime,
)
from core.engine.core.local_source_connect import (
    LocalSourceConnectAuthorizationHostRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectHostConflict,
    LocalSourceConnectHostDenied,
    LocalSourceConnectHostNotFound,
    LocalSourceConnectHostRuntime,
    LocalSourceConnectHostUnauthenticated,
    LocalSourceConnectHostUnavailable,
    LocalSourceConnectPreview,
    LocalSourceConnectPreviewHostRequest,
    LocalSourceConnectPreviewRuntime,
    authorize_local_source_connect_host,
    local_source_connect_host_runtime,
    local_source_connect_preview_runtime,
    preview_local_source_connect_host,
)
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    LocalSourceConnectSourceProgressionConflict,
    LocalSourceConnectSourceProgressionDenied,
    LocalSourceConnectSourceProgressionNotFound,
    LocalSourceConnectSourceProgressionUnavailable,
    connect_local_source_connect_scope,
    local_source_connect_scope_progression_runtime,
    propose_local_source_connect_scope,
)

router = APIRouter(prefix="/v1/intelligence/builds", tags=["intelligence-builds"])


def intelligence_activation_approval_records() -> SurrealImmutableRecordStore:
    return SurrealImmutableRecordStore(pool)


@router.post("/prepare", response_model=IntelligenceBuildPlanV1Alpha3)
async def prepare_build(
    request: IntelligenceBuildPlanPrepareV1Alpha2,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildPlanHttpRuntime = Depends(intelligence_build_plan_runtime),
) -> IntelligenceBuildPlanV1Alpha3:
    try:
        return await prepare_intelligence_build_plan(request=request, user=user, runtime=runtime)
    except IntelligenceBuildPlanUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks product scope"
        ) from exc
    except IntelligenceBuildPlanNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IntelligenceBuildPlanConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuildPlanUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/bind", response_model=BoundIntelligenceBuildPlanV1Alpha1)
async def bind_build_plan(
    request: IntelligenceBuildPlanBindRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildPlanHttpRuntime = Depends(intelligence_build_plan_runtime),
) -> BoundIntelligenceBuildPlanV1Alpha1:
    try:
        return await bind_intelligence_build_plan(request=request, user=user, runtime=runtime)
    except IntelligenceBuildPlanUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks exact plan scope"
        ) from exc
    except IntelligenceBuildPlanNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IntelligenceBuildPlanConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuildPlanUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/projection", response_model=IntelligenceSystemProjectionV1Alpha1)
async def project_build_plan(
    request: IntelligenceBuildProjectionRequestV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildPlanHttpRuntime = Depends(intelligence_build_plan_runtime),
) -> IntelligenceSystemProjectionV1Alpha1:
    try:
        plan = request.exact_plan()
        return await project_intelligence_build_plan(plan=plan, user=user, runtime=runtime)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid reviewed plan") from exc
    except IntelligenceBuildPlanUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks exact plan scope"
        ) from exc
    except IntelligenceBuildPlanNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IntelligenceBuildPlanConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuildPlanUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/projection/resource-state", response_model=IntelligenceSystemProjectionV1Alpha1)
async def project_build_resource_state(
    request: IntelligenceBuildResourceStateRequestV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildResourceStateRuntime = Depends(intelligence_build_resource_state_runtime),
) -> IntelligenceSystemProjectionV1Alpha1:
    """Enrich one exact bound plan's projection with a truthful live/proposal resource read.

    The request carries only the exact bound plan, its activation approval
    receipt reference, and the existing resource selector — no client-authored
    health, coverage, or mode value. ``mode`` becomes ``live`` only when that
    reviewed activation is durably approved and durably active through the
    actual current prepare -> bind -> approve -> start path (the same durable
    Builder-artifact bootstrap ``/start`` uses), and the authorized resource
    page fully closes.
    """

    try:
        return await project_intelligence_build_resource_state(request=request, user=user, runtime=runtime)
    except IntelligenceBuildResourceStateUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks exact bound-plan scope"
        ) from exc
    except IntelligenceBuildResourceStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IntelligenceBuildResourceStateDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence resource read denied") from exc
    except IntelligenceBuildResourceStateConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuildResourceStateUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/start", response_model=IntelligenceBuildResultV1)
async def start_build(
    request: IntelligenceBuildStartV1Alpha2,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildHttpRuntime = Depends(intelligence_build_runtime),
) -> IntelligenceBuildResultV1:
    try:
        return await start_intelligence_build(request=request, user=user, runtime=runtime)
    except IntelligenceBuildUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks product scope"
        ) from exc
    except IntelligenceBuildDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence build denied") from exc
    except IntelligenceBuildContractConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Intelligence build contract conflict"
        ) from exc
    except IntelligenceBuildUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/connect/preview", response_model=LocalSourceConnectPreview)
async def preview_connect_host(
    request: LocalSourceConnectPreviewHostRequest,
    user: dict = Depends(get_current_user),
    runtime: LocalSourceConnectPreviewRuntime = Depends(local_source_connect_preview_runtime),
) -> LocalSourceConnectPreview:
    try:
        return await preview_local_source_connect_host(request=request, user=user, runtime=runtime)
    except LocalSourceConnectHostUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks an exact local actor and product"
        ) from exc
    except LocalSourceConnectHostDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LocalSourceConnectHostNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalSourceConnectHostConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LocalSourceConnectHostUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/connect/authorize", response_model=LocalSourceConnectAuthorizationResult)
async def authorize_connect_host(
    request: LocalSourceConnectAuthorizationHostRequest,
    user: dict = Depends(get_current_user),
    runtime: LocalSourceConnectHostRuntime = Depends(local_source_connect_host_runtime),
) -> LocalSourceConnectAuthorizationResult:
    try:
        exact_request = request.exact_request()
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid Connect authorization request"
        ) from exc
    try:
        return await authorize_local_source_connect_host(request=exact_request, user=user, runtime=runtime)
    except LocalSourceConnectHostUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks an exact local actor and product"
        ) from exc
    except LocalSourceConnectHostDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LocalSourceConnectHostNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalSourceConnectHostConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LocalSourceConnectHostUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/approve", response_model=IntelligenceActivationApprovalResultV1Alpha1)
async def approve_build_activation(
    request: IntelligenceActivationApproveRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    records=Depends(intelligence_activation_approval_records),
) -> IntelligenceActivationApprovalResultV1Alpha1:
    """Persist an explicit local-owner approval for one exact bound activation."""

    try:
        return await approve_intelligence_activation(
            request=request,
            user=user,
            records=records,
        )
    except IntelligenceActivationApprovalDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceActivationApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceActivationApprovalUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/bootstrap/local-first-run", response_model=LocalFirstRunBuildAuthorityV1Alpha1)
async def bootstrap_local_first_run(
    request: IntelligenceActivationApproveRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: LocalFirstRunBootstrapRuntime = Depends(local_first_run_bootstrap_runtime),
) -> LocalFirstRunBuildAuthorityV1Alpha1:
    """Obtain or exactly resume the fixed local owner's first-run build authority.

    The request is the existing exact bound-plan ``/approve`` shape; no client
    value carries authority. ``/approve`` semantics are unchanged — the first
    call mints the durable reviewed activation approval through the same
    service, and every later identical call resumes the recorded receipt and
    start request (``resumed`` is true). Missing setup grants, a foreign or
    stale grant binding, a wrong actor or product, and a crossed bound plan
    all fail closed with their exact names. The request's ``approved_at``
    stamps only a newly minted approval; authority is always evaluated at
    server-now, so no client value can pin resolution to a pre-revocation time.
    """

    try:
        return await bootstrap_local_first_run_build_authority(
            bound_plan=request.bound_plan,
            user=user,
            runtime=runtime,
            approved_at=request.approved_at,
        )
    except LocalFirstRunBootstrapDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LocalFirstRunAuthorityMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalFirstRunBootstrapConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LocalFirstRunBootstrapUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/session/associate", response_model=IntelligenceBuildSessionAssociationResultV1Alpha1)
async def associate_build_session(
    request: IntelligenceBuildSessionAssociateRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    records=Depends(intelligence_activation_approval_records),
) -> IntelligenceBuildSessionAssociationResultV1Alpha1:
    """Admit the Builder session for one exact bound plan's recorded approval.

    The server durably reloads and revalidates the full reviewed activation
    approval artifact against the exact bound plan, execution, and spec
    identity and the verified local-owner product/actor scope, then derives
    the session's correlation_id from the approval's own execution_request_id
    and its goal_ref from the reviewed plan's own outcome_id. No client value
    is trusted for either. Safe to retry: an identical call replays the
    existing GOAL_SELECTED session revision instead of repeating it.
    """

    try:
        return await associate_intelligence_build_session(
            request=request,
            user=user,
            records=records,
        )
    except IntelligenceActivationApprovalDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceActivationApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceActivationApprovalUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/activation-plan/prepare", response_model=IntelligenceActivationPlanV1Alpha2)
async def prepare_activation_plan(
    request: DomainActivationPlanPrepareRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderActivationPlanRuntime = Depends(intelligence_builder_activation_plan_runtime),
) -> IntelligenceActivationPlanV1Alpha2:
    """Side-effect-free preview of the exact v1alpha2 plan the owner is about to approve.

    Reloads the exact current ``FIRST_BRIEFING_READY`` Builder session and its
    0.7D handoff durably; the reviewed activation specification's own
    approval (``/approve``) is never treated as this plan's approval.
    """

    try:
        return await prepare_domain_activation_plan(request=request, user=user, runtime=runtime)
    except DomainActivationPlanCoordinationDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/activation-plan/approve", response_model=DomainActivationCommitReferenceV1Alpha2)
async def approve_activation_plan(
    request: DomainActivationPlanApproveRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderActivationPlanRuntime = Depends(intelligence_builder_activation_plan_runtime),
) -> DomainActivationCommitReferenceV1Alpha2:
    """Record the plan's own distinct owner approval, then durably admit it.

    This approval is separate from ``/approve``'s reviewed-specification
    receipt; compatibility with canonical v1alpha1 activation requires the
    two receipts to differ. Returns opaque historical coordinates that grant
    no present runtime authority.
    """

    try:
        return await approve_domain_activation_plan(request=request, user=user, runtime=runtime)
    except DomainActivationPlanCoordinationDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/activation-plan/activate", response_model=IntelligenceBuilderActivationResultV1Alpha1)
async def activate_activation_plan(
    request: IntelligenceBuilderPlanActivateRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderActivationPlanRuntime = Depends(intelligence_builder_activation_plan_runtime),
) -> IntelligenceBuilderActivationResultV1Alpha1:
    """Drive record_current_plan/.activate from only the bound plan, its spec
    approval receipt, and a stable request time. The server derives the
    Builder session from the already-admitted v1alpha2 plan's own handoff
    and independently reloads every other dependency; it never accepts a
    client-authored handoff, plan approval, or canonical revision. Safe to
    retry: a crash between recording the plan and activating it resumes from
    the durable ``ACTIVATION_PENDING`` state instead of repeating it, and an
    already-``ACTIVE`` session replays its identical durable receipt.
    """

    try:
        return await activate_intelligence_builder_plan(request=request, user=user, runtime=runtime)
    except DomainActivationPlanCoordinationDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainActivationPlanCoordinationUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/retry", response_model=IntelligenceBuilderSessionRevisionV1)
async def retry_build_session(
    request: IntelligenceBuildRetryRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    records=Depends(intelligence_activation_approval_records),
) -> IntelligenceBuilderSessionRevisionV1:
    """Retry one exact current blocked Builder session through its existing state machine."""

    try:
        return await retry_intelligence_build_session(
            request=request,
            user=user,
            records=records,
        )
    except IntelligenceActivationApprovalDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceActivationApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceActivationApprovalUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/builder/source/propose", response_model=BuilderSourceScopeProposeResultV1Alpha1)
async def propose_builder_source_scope(
    request: BuilderSourceScopeProposeRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: LocalSourceConnectScopeProgressionRuntime = Depends(local_source_connect_scope_progression_runtime),
) -> BuilderSourceScopeProposeResultV1Alpha1:
    """Propose the Connection Agent's source scope from one exact recorded Connect result."""

    try:
        admission = await propose_local_source_connect_scope(
            request=request.connect_request,
            result=request.connect_result,
            session=request.current,
            user=user,
            runtime=runtime,
            occurred_at=request.occurred_at,
        )
    except LocalSourceConnectSourceProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderSourceScopeProposeResultV1Alpha1(
        proposal=admission.proposal,
        session_revision=admission.session.revision,
    )


@router.post("/builder/source/approve-connect", response_model=BuilderSourceScopeApproveConnectResultV1Alpha1)
async def approve_connect_builder_source_scope(
    request: BuilderSourceScopeApproveConnectRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: LocalSourceConnectScopeProgressionRuntime = Depends(local_source_connect_scope_progression_runtime),
) -> BuilderSourceScopeApproveConnectResultV1Alpha1:
    """Record one explicit source-scope owner approval, then connect.

    This is exactly one source-scope owner decision (``approve_builder_source_scope``)
    followed by the exact recorded connect (``connect_local_source_connect_scope``);
    it exposes no approval-only shortcut and bundles no other approval.
    """

    try:
        reviewed = await approve_builder_source_scope(request=request.approval, user=user, records=runtime.records)
    except BuilderDispositionApprovalDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except BuilderDispositionApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BuilderDispositionApprovalUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    try:
        outcome = await connect_local_source_connect_scope(
            request=request.connect_request,
            result=request.connect_result,
            session=request.approval.current,
            proposal=request.approval.proposal,
            approval_receipt_ref=reviewed.approval.receipt_ref,
            user=user,
            runtime=runtime,
            occurred_at=request.approval.approved_at,
        )
    except LocalSourceConnectSourceProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LocalSourceConnectSourceProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderSourceScopeApproveConnectResultV1Alpha1(
        reviewed_approval=reviewed,
        profile=outcome.profile,
        session_revision=outcome.session.revision,
        blocked_reason=outcome.blocked_reason,
    )


@router.post("/builder/concept/propose", response_model=BuilderConceptModelProposeResultV1Alpha1)
async def propose_builder_concept_model(
    request: ConceptModelProposeRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderConceptProgressionRuntime = Depends(intelligence_builder_concept_progression_runtime),
) -> BuilderConceptModelProposeResultV1Alpha1:
    """Propose the Ontology Agent's concept model from the exact current SOURCES_READY handoff."""

    try:
        admission = await propose_intelligence_builder_concept_model(request=request, user=user, runtime=runtime)
    except IntelligenceBuilderConceptProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceBuilderConceptProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuilderConceptProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderConceptModelProposeResultV1Alpha1(
        proposal=admission.proposal,
        session_revision=admission.session.revision,
    )


@router.post("/builder/concept/approve", response_model=BuilderConceptModelApproveResultV1Alpha1)
async def approve_builder_concept_model_progression(
    request: BuilderConceptModelApproveRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderConceptProgressionRuntime = Depends(intelligence_builder_concept_progression_runtime),
) -> BuilderConceptModelApproveResultV1Alpha1:
    """Approve the exact current CONCEPT_MODEL_PROPOSED concept model."""

    try:
        result = await approve_intelligence_builder_concept_model(request=request, user=user, runtime=runtime)
    except IntelligenceBuilderConceptProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceBuilderConceptProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuilderConceptProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderConceptModelApproveResultV1Alpha1(
        reviewed_approval=result.reviewed_approval,
        proposal=result.approval.proposal,
        disposition=result.approval.disposition,
        session_revision=result.approval.session.revision,
    )


@router.post("/builder/intelligence/propose", response_model=BuilderIntelligenceModelProposeResultV1Alpha1)
async def propose_builder_intelligence_model(
    request: IntelligenceModelProposeRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime = Depends(
        intelligence_builder_intelligence_progression_runtime
    ),
) -> BuilderIntelligenceModelProposeResultV1Alpha1:
    """Propose the Intelligence Agent's model from the exact current CONCEPT_MODEL_APPROVED handoff."""

    try:
        admission = await propose_intelligence_builder_intelligence_model(request=request, user=user, runtime=runtime)
    except IntelligenceBuilderIntelligenceProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderIntelligenceModelProposeResultV1Alpha1(
        proposal=admission.proposal,
        session_revision=admission.session.revision,
    )


@router.post("/builder/intelligence/approve", response_model=BuilderIntelligenceModelApproveResultV1Alpha1)
async def approve_builder_intelligence_model_progression(
    request: BuilderIntelligenceModelApproveRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime = Depends(
        intelligence_builder_intelligence_progression_runtime
    ),
) -> BuilderIntelligenceModelApproveResultV1Alpha1:
    """Approve the exact current INTELLIGENCE_MODEL_PROPOSED intelligence model."""

    try:
        result = await approve_intelligence_builder_intelligence_model(request=request, user=user, runtime=runtime)
    except IntelligenceBuilderIntelligenceProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderIntelligenceModelApproveResultV1Alpha1(
        reviewed_approval=result.reviewed_approval,
        proposal=result.approval.proposal,
        disposition=result.approval.disposition,
        session_revision=result.approval.session.revision,
    )


@router.post("/builder/first-brief/prepare", response_model=BuilderFirstBriefPrepareResultV1Alpha1)
async def prepare_builder_first_brief(
    request: FirstBriefPrepareRequestV1Alpha1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuilderIntelligenceProgressionRuntime = Depends(
        intelligence_builder_intelligence_progression_runtime
    ),
) -> BuilderFirstBriefPrepareResultV1Alpha1:
    """Prepare the first Brief from the exact current INTELLIGENCE_MODEL_APPROVED handoff."""

    try:
        admission = await prepare_intelligence_builder_first_brief(request=request, user=user, runtime=runtime)
    except IntelligenceBuilderIntelligenceProgressionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceBuilderIntelligenceProgressionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return BuilderFirstBriefPrepareResultV1Alpha1(
        brief=admission.brief,
        session_revision=admission.session.revision,
    )


__all__ = [
    "activate_activation_plan",
    "approve_activation_plan",
    "approve_build_activation",
    "approve_builder_concept_model_progression",
    "approve_builder_intelligence_model_progression",
    "approve_connect_builder_source_scope",
    "associate_build_session",
    "authorize_connect_host",
    "bind_build_plan",
    "bootstrap_local_first_run",
    "intelligence_activation_approval_records",
    "prepare_activation_plan",
    "prepare_build",
    "prepare_builder_first_brief",
    "preview_connect_host",
    "project_build_plan",
    "project_build_resource_state",
    "propose_builder_concept_model",
    "propose_builder_intelligence_model",
    "propose_builder_source_scope",
    "retry_build_session",
    "router",
    "start_build",
]
