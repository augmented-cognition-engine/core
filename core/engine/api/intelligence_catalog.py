"""Read-only catalog of validated inert Intelligence starting profiles."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ace.intelligence import IntelligenceOnboardingProfileV1Alpha1
from core.engine.core.auth import get_current_user
from core.engine.core.installed_intelligence_catalog import discover_installed_onboarding_profiles

router = APIRouter(prefix="/v1/intelligence/catalog", tags=["intelligence-catalog"])


class InstalledIntelligenceProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: str
    distribution_version: str
    resource_path: str
    profile: IntelligenceOnboardingProfileV1Alpha1


class InstalledIntelligenceCatalogV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.installed-intelligence-catalog/v1alpha1"] = (
        "ace.http.installed-intelligence-catalog/v1alpha1"
    )
    profiles: tuple[InstalledIntelligenceProfileV1, ...]


@router.get("/profiles", response_model=InstalledIntelligenceCatalogV1)
async def installed_profiles(user: dict = Depends(get_current_user)) -> InstalledIntelligenceCatalogV1:
    """List validated installed profiles; authentication never grants their proposed effects."""

    del user
    return InstalledIntelligenceCatalogV1(
        profiles=tuple(
            InstalledIntelligenceProfileV1(
                distribution=item.distribution,
                distribution_version=item.distribution_version,
                resource_path=item.resource_path,
                profile=item.profile,
            )
            for item in discover_installed_onboarding_profiles()
        )
    )


__all__ = ["InstalledIntelligenceCatalogV1", "InstalledIntelligenceProfileV1", "installed_profiles", "router"]
