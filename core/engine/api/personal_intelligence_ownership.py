"""Authenticated HTTP transport for personal Intelligence ownership."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.personal_intelligence_ownership import (
    PersonalIntelligenceDeletePreviewV1Alpha1,
    PersonalIntelligenceExportArtifactV1Alpha1,
    PersonalOwnershipHttpConflict,
    PersonalOwnershipHttpDeleteConfirmationV1,
    PersonalOwnershipHttpDeletePreviewV1,
    PersonalOwnershipHttpDeletionResultV1,
    PersonalOwnershipHttpDenied,
    PersonalOwnershipHttpExportV1,
    PersonalOwnershipHttpRuntime,
    PersonalOwnershipHttpUnauthenticated,
    PersonalOwnershipHttpUnavailable,
    confirm_personal_intelligence_deletion,
    export_personal_intelligence,
    personal_ownership_runtime,
    preview_personal_intelligence_deletion,
)

router = APIRouter(
    prefix="/v1/intelligence/ownership",
    tags=["personal-intelligence-ownership"],
)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PersonalOwnershipHttpUnauthenticated):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified token lacks personal product scope",
        )
    if isinstance(exc, PersonalOwnershipHttpDenied):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Personal Intelligence ownership operation denied",
        )
    if isinstance(exc, PersonalOwnershipHttpUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Personal Intelligence ownership storage is unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Personal Intelligence ownership request is stale or conflicted",
    )


@router.post("/export", response_model=PersonalIntelligenceExportArtifactV1Alpha1)
async def export_ownership_artifact(
    selector: PersonalOwnershipHttpExportV1,
    user: dict = Depends(get_current_user),
    runtime: PersonalOwnershipHttpRuntime = Depends(personal_ownership_runtime),
) -> PersonalIntelligenceExportArtifactV1Alpha1:
    """Return canonical product records without claiming runnable restore."""

    try:
        return await export_personal_intelligence(
            selector=selector,
            user=user,
            runtime=runtime,
        )
    except (
        PersonalOwnershipHttpConflict,
        PersonalOwnershipHttpDenied,
        PersonalOwnershipHttpUnauthenticated,
        PersonalOwnershipHttpUnavailable,
    ) as exc:
        raise _translate(exc) from exc


@router.post(
    "/deletion/preview",
    response_model=PersonalIntelligenceDeletePreviewV1Alpha1,
)
async def preview_ownership_deletion(
    selector: PersonalOwnershipHttpDeletePreviewV1,
    user: dict = Depends(get_current_user),
    runtime: PersonalOwnershipHttpRuntime = Depends(personal_ownership_runtime),
) -> PersonalIntelligenceDeletePreviewV1Alpha1:
    """Return the exact expiring snapshot and digest required for confirmation."""

    try:
        return await preview_personal_intelligence_deletion(
            selector=selector,
            user=user,
            runtime=runtime,
        )
    except (
        PersonalOwnershipHttpConflict,
        PersonalOwnershipHttpDenied,
        PersonalOwnershipHttpUnauthenticated,
        PersonalOwnershipHttpUnavailable,
    ) as exc:
        raise _translate(exc) from exc


@router.post(
    "/deletion/confirm",
    response_model=PersonalOwnershipHttpDeletionResultV1,
)
async def confirm_ownership_deletion(
    selector: PersonalOwnershipHttpDeleteConfirmationV1,
    user: dict = Depends(get_current_user),
    runtime: PersonalOwnershipHttpRuntime = Depends(personal_ownership_runtime),
) -> PersonalOwnershipHttpDeletionResultV1:
    """Confirm one reviewed digest; this is deliberately not an HTTP DELETE."""

    try:
        return await confirm_personal_intelligence_deletion(
            selector=selector,
            user=user,
            runtime=runtime,
        )
    except (
        PersonalOwnershipHttpConflict,
        PersonalOwnershipHttpDenied,
        PersonalOwnershipHttpUnauthenticated,
        PersonalOwnershipHttpUnavailable,
    ) as exc:
        raise _translate(exc) from exc


__all__ = [
    "confirm_ownership_deletion",
    "export_ownership_artifact",
    "preview_ownership_deletion",
    "router",
]
