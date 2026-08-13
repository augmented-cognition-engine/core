"""HTTP transport for the governed ACE Intelligence resource plane."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_resource_plane import (
    IntelligenceResourceHttpContractConflict,
    IntelligenceResourceHttpDenied,
    IntelligenceResourceHttpQueryV1,
    IntelligenceResourceHttpRuntime,
    IntelligenceResourceHttpUnauthenticated,
    IntelligenceResourceHttpUnavailable,
    IntelligenceResourcePageV1Alpha1,
    intelligence_resource_runtime,
    query_intelligence_resource_page,
)

router = APIRouter(prefix="/v1/intelligence/resources", tags=["intelligence-resources"])


@router.post("/query", response_model=IntelligenceResourcePageV1Alpha1)
async def query_intelligence_resources(
    selector: IntelligenceResourceHttpQueryV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceResourceHttpRuntime = Depends(intelligence_resource_runtime),
) -> IntelligenceResourcePageV1Alpha1:
    """Reauthenticate and reauthorize one point-in-time page; cursors grant no authority."""

    try:
        return await query_intelligence_resource_page(
            selector=selector,
            user=user,
            runtime=runtime,
        )
    except IntelligenceResourceHttpUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks product scope"
        ) from exc
    except IntelligenceResourceHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence query denied") from exc
    except IntelligenceResourceHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence authentication evidence is unavailable",
        ) from exc
    except IntelligenceResourceHttpContractConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Intelligence resource query could not preserve its exact contract",
        ) from exc


__all__ = [
    "IntelligenceResourceHttpQueryV1",
    "IntelligenceResourceHttpRuntime",
    "intelligence_resource_runtime",
    "query_intelligence_resources",
    "router",
]
