"""HTTP transport for starting one governed personal Intelligence build."""

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

router = APIRouter(prefix="/v1/intelligence/builds", tags=["intelligence-builds"])


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


__all__ = ["router", "start_build"]
