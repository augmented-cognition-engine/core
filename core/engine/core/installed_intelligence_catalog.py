"""Discover inert Intelligence onboarding profiles from installed distributions.

The host recognizes a validated resource shape, never a domain or package name.
Domain distributions remain JSON-only and do not gain executable entry points.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Iterable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from ace import __version__ as ace_version
from ace.application import IntelligenceOnboardingProfileV1Alpha1
from ace.application.domain_activation_plan import (
    DomainActivationPlanAdmissionError,
    load_domain_activation_plan_history,
)
from ace.application.domain_activation_plan_contracts import (
    ActivationPlanAction,
    ActivationRuntimeState,
    CompiledOverlayV1,
    CompiledPackRefV1,
)
from ace.application.installed_pack_artifacts import (
    DomainPackManifestV1,
    discover_installed_domain_pack_previews,
)
from ace.core.state import GovernedStateStore
from ace_mcp_client import __version__ as mcp_client_version
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore

MAX_ONBOARDING_PROFILE_BYTES = 1_000_000
ONBOARDING_PROFILE_FILENAME = "onboarding_profile.json"


class InstalledIntelligenceCatalogError(RuntimeError):
    """Installed catalog material was unreadable, invalid, or conflicting."""


class InstalledDistribution(Protocol):
    @property
    def files(self): ...

    @property
    def metadata(self): ...

    @property
    def version(self) -> str: ...

    def locate_file(self, path) -> Path: ...


@dataclass(frozen=True, slots=True)
class InstalledOnboardingProfile:
    distribution: str
    distribution_version: str
    resource_path: str
    profile: IntelligenceOnboardingProfileV1Alpha1


class DomainPackActivationRevisionProjectionV1(BaseModel):
    """Exact governed Pack/overlay material from one append-only revision."""

    model_config = ConfigDict(extra="forbid")

    revision: int
    revision_id: str
    revision_digest: str
    action: ActivationPlanAction
    state: ActivationRuntimeState
    pack: CompiledPackRefV1
    overlay: CompiledOverlayV1
    plan_id: str
    plan_digest: str
    approval_receipt_ref: str
    approval_receipt_digest: str
    actor_ref: str
    occurred_at: datetime
    commit_receipt_id: str
    commit_receipt_digest: str
    committed_at: datetime


class DomainPackActivationHistoryProjectionV1(BaseModel):
    """Authenticated read projection; historical material grants no live authority."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.domain-pack-activation-history/v1alpha1"] = (
        "ace.http.domain-pack-activation-history/v1alpha1"
    )
    authority_stage: Literal["historical_reference"] = "historical_reference"
    live_authority: Literal[False] = False
    product_id: str
    activation_key: str
    activation_id: str
    current: DomainPackActivationRevisionProjectionV1
    history: tuple[DomainPackActivationRevisionProjectionV1, ...]


class DomainPackActivationHistoryDenied(RuntimeError):
    """Verified identity lacks lifecycle-administration authority."""


class DomainPackActivationHistoryUnauthenticated(RuntimeError):
    """Verified identity omitted exact product scope."""


class DomainPackActivationHistoryNotFound(RuntimeError):
    """No exact v1alpha2 activation exists for the supplied activation key."""


class DomainPackActivationHistoryUnavailable(RuntimeError):
    """Persisted activation history failed exact reconstruction."""


def domain_pack_activation_store() -> GovernedStateStore:
    return SurrealGovernedStateStore(pool)


async def read_domain_pack_activation_history(
    *,
    activation_key: str,
    user: dict,
    store: GovernedStateStore,
) -> DomainPackActivationHistoryProjectionV1:
    product_id = user.get("product")
    actor_ref = user.get("sub")
    if not isinstance(product_id, str) or not product_id.startswith("product:") or not isinstance(actor_ref, str):
        raise DomainPackActivationHistoryUnauthenticated("verified token lacks exact product scope")
    authorities = user.get("authorities")
    if not isinstance(authorities, list) or "administer_lifecycle" not in authorities:
        raise DomainPackActivationHistoryDenied("Pack activation history requires administer_lifecycle authority")
    try:
        committed = await load_domain_activation_plan_history(
            store=store,
            product_id=product_id,
            activation_key=activation_key,
        )
    except (AttributeError, TypeError, ValueError, DomainActivationPlanAdmissionError) as exc:
        raise DomainPackActivationHistoryUnavailable("exact Pack activation history is unavailable") from exc
    if not committed:
        raise DomainPackActivationHistoryNotFound("no activation exists for the exact activation key")
    rows = tuple(
        DomainPackActivationRevisionProjectionV1(
            revision=item.revision.revision,
            revision_id=str(item.revision.revision_id),
            revision_digest=str(item.revision.revision_digest),
            action=item.revision.plan.action,
            state=item.revision.state,
            pack=item.revision.plan.spec.pack,
            overlay=item.revision.plan.spec.overlay,
            plan_id=str(item.revision.plan.plan_id),
            plan_digest=str(item.revision.plan.plan_digest),
            approval_receipt_ref=item.revision.approval_receipt_ref,
            approval_receipt_digest=f"sha256:{item.commit_receipt.approval.receipt_hash}",
            actor_ref=item.revision.actor_ref,
            occurred_at=item.revision.occurred_at,
            commit_receipt_id=str(item.commit_receipt.receipt_id),
            commit_receipt_digest=f"sha256:{item.commit_receipt.receipt_hash}",
            committed_at=item.commit_receipt.committed_at,
        )
        for item in committed
    )
    current = rows[0]
    return DomainPackActivationHistoryProjectionV1(
        product_id=product_id,
        activation_key=activation_key,
        activation_id=str(committed[0].revision.activation_id),
        current=current,
        history=rows,
    )


def _distribution_name(distribution: InstalledDistribution) -> str:
    value = distribution.metadata.get("Name")
    if not isinstance(value, str) or not value.strip():
        raise InstalledIntelligenceCatalogError("installed distribution omitted its canonical name")
    return value.strip()


def _profile_paths(distribution: InstalledDistribution) -> tuple:
    paths = []
    for candidate in distribution.files or ():
        normalized = PurePosixPath(str(candidate).replace("\\", "/"))
        if (
            normalized.name == ONBOARDING_PROFILE_FILENAME
            and "domain_packs" in normalized.parts
            and ".dist-info" not in normalized.as_posix()
        ):
            paths.append(candidate)
    return tuple(sorted(paths, key=str))


def _load_profile(*, distribution: InstalledDistribution, candidate, name: str) -> InstalledOnboardingProfile:
    resource_path = str(candidate).replace("\\", "/")
    try:
        path = Path(distribution.locate_file(candidate))
        payload = path.read_bytes()
    except OSError as exc:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile is unreadable: {name}:{resource_path}"
        ) from exc
    if not payload or len(payload) > MAX_ONBOARDING_PROFILE_BYTES:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile exceeded its bounded size: {name}:{resource_path}"
        )
    try:
        json.loads(payload)
        profile = IntelligenceOnboardingProfileV1Alpha1.model_validate_json(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise InstalledIntelligenceCatalogError(
            f"installed onboarding profile failed exact validation: {name}:{resource_path}"
        ) from exc
    return InstalledOnboardingProfile(
        distribution=name,
        distribution_version=str(distribution.version),
        resource_path=resource_path,
        profile=profile,
    )


def discover_installed_onboarding_profiles(
    distributions: Iterable[InstalledDistribution] | None = None,
) -> tuple[InstalledOnboardingProfile, ...]:
    """Return validated inert profiles with deterministic provenance and ordering."""

    installed = metadata.distributions() if distributions is None else distributions
    discovered: list[InstalledOnboardingProfile] = []
    for distribution in sorted(installed, key=lambda item: _distribution_name(item).lower()):
        name = _distribution_name(distribution)
        for candidate in _profile_paths(distribution):
            discovered.append(_load_profile(distribution=distribution, candidate=candidate, name=name))

    by_id: dict[str, InstalledOnboardingProfile] = {}
    for item in discovered:
        incumbent = by_id.get(item.profile.profile_id)
        if incumbent is None:
            by_id[item.profile.profile_id] = item
            continue
        if incumbent.profile.profile_digest != item.profile.profile_digest:
            raise InstalledIntelligenceCatalogError(
                f"installed onboarding profile identity conflicts across distributions: {item.profile.profile_id}"
            )
    return tuple(sorted(by_id.values(), key=lambda item: (item.profile.domain_label or "", item.profile.profile_id)))


__all__ = [
    "DomainPackActivationHistoryDenied",
    "DomainPackActivationHistoryNotFound",
    "DomainPackActivationHistoryProjectionV1",
    "DomainPackActivationHistoryUnavailable",
    "DomainPackActivationHistoryUnauthenticated",
    "DomainPackActivationRevisionProjectionV1",
    "DomainPackManifestV1",
    "InstalledIntelligenceCatalogError",
    "InstalledOnboardingProfile",
    "IntelligenceOnboardingProfileV1Alpha1",
    "ace_version",
    "discover_installed_domain_pack_previews",
    "discover_installed_onboarding_profiles",
    "domain_pack_activation_store",
    "mcp_client_version",
    "read_domain_pack_activation_history",
]
