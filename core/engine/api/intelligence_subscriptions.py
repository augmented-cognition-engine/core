"""HTTP transport for authenticated record-only subscription lifecycle."""

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_subscriptions import (
    IntelligenceSubscriptionHttpConflict,
    IntelligenceSubscriptionHttpDenied,
    IntelligenceSubscriptionHttpRuntime,
    IntelligenceSubscriptionHttpUnauthenticated,
    IntelligenceSubscriptionHttpUnavailable,
    IntelligenceSubscriptionLifecycleHttpRequestV1,
    IntelligenceSubscriptionLifecycleResultV1Alpha1,
    intelligence_subscription_runtime,
    transition_record_only_subscription,
)

router = APIRouter(prefix="/v1/intelligence/subscriptions", tags=["intelligence-subscriptions"])


@router.post("/lifecycle", response_model=IntelligenceSubscriptionLifecycleResultV1Alpha1)
async def transition_subscription_lifecycle(
    request: IntelligenceSubscriptionLifecycleHttpRequestV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceSubscriptionHttpRuntime = Depends(intelligence_subscription_runtime),
) -> IntelligenceSubscriptionLifecycleResultV1Alpha1:
    """Create, pause, resume, or revoke one record-only owner preference."""

    try:
        return await transition_record_only_subscription(
            selector=request,
            user=user,
            runtime=runtime,
        )
    except IntelligenceSubscriptionHttpUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except IntelligenceSubscriptionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntelligenceSubscriptionHttpConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntelligenceSubscriptionHttpUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


__all__ = [
    "intelligence_subscription_runtime",
    "router",
    "transition_subscription_lifecycle",
]
