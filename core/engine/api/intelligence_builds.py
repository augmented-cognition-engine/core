"""HTTP transport for preparing and starting one personal Intelligence build."""

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_build import (
    IntelligenceBuildContractConflict,
    IntelligenceBuildDenied,
    IntelligenceBuildHttpRuntime,
    IntelligenceBuildResultV1,
    IntelligenceBuildStartV1,
    IntelligenceBuildUnauthenticated,
    IntelligenceBuildUnavailable,
    intelligence_build_runtime,
    start_intelligence_build,
)
from core.engine.core.intelligence_build_plan import (
    IntelligenceBuildPlanConflict,
    IntelligenceBuildPlanHttpRuntime,
    IntelligenceBuildPlanNotFound,
    IntelligenceBuildPlanPrepareV1,
    IntelligenceBuildPlanUnauthenticated,
    IntelligenceBuildPlanUnavailable,
    IntelligenceBuildPlanV1Alpha1,
    intelligence_build_plan_runtime,
    prepare_intelligence_build_plan,
)

router = APIRouter(prefix="/v1/intelligence/builds", tags=["intelligence-builds"])


@router.post("/prepare", response_model=IntelligenceBuildPlanV1Alpha1)
async def prepare_build(
    request: IntelligenceBuildPlanPrepareV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceBuildPlanHttpRuntime = Depends(intelligence_build_plan_runtime),
) -> IntelligenceBuildPlanV1Alpha1:
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


@router.post("/start", response_model=IntelligenceBuildResultV1)
async def start_build(
    request: IntelligenceBuildStartV1,
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


__all__ = ["prepare_build", "router", "start_build"]
