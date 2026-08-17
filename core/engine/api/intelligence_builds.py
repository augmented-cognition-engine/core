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


__all__ = [
    "activate_activation_plan",
    "approve_activation_plan",
    "approve_build_activation",
    "associate_build_session",
    "bind_build_plan",
    "intelligence_activation_approval_records",
    "prepare_activation_plan",
    "prepare_build",
    "project_build_plan",
    "project_build_resource_state",
    "retry_build_session",
    "router",
    "start_build",
]
