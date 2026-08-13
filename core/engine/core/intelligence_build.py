"""Governed host boundary for starting one personal Intelligence build.

Core owns authentication, authority use, and the stable HTTP material. A host
supplies the domain-neutral executor; domain repositories remain responsible
for source options, ontology vocabulary, watch policy, and briefing strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ace.application import IntelligenceResourcePageV1Alpha1
from ace.core import ImmutableRecordStore
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore

INTELLIGENCE_BUILD_AUTHORITY = "intelligence_build"
INTELLIGENCE_BUILD_OPERATION = "start_intelligence_build"
INTELLIGENCE_BUILD_RESULT_VERSION = "ace.http.intelligence-build-result/v1alpha1"


class IntelligenceBuildStartV1(BaseModel):
    """One reviewed Atrium plan submitted for governed execution."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    client_request_id: str = Field(min_length=1, max_length=240)
    profile_id: str = Field(min_length=1, max_length=240)
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str = Field(min_length=1, max_length=240)
    source_group_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    cadence_id: str = Field(min_length=1, max_length=240)
    requested_at: datetime

    @field_validator("source_group_ids")
    @classmethod
    def _unique_source_groups(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_group_ids must be unique")
        return value


class IntelligenceBuildResultV1(BaseModel):
    """Authorized result returned after a host completes or safely blocks a build."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.intelligence-build-result/v1alpha1"] = INTELLIGENCE_BUILD_RESULT_VERSION
    build_id: str
    request_digest: str
    product_id: str
    actor_ref: str
    accepted_at: datetime
    authority_use: AuthorityUseReceiptV1Alpha1
    resource_page: IntelligenceResourcePageV1Alpha1


@dataclass(frozen=True, slots=True)
class AuthorizedIntelligenceBuild:
    build_id: str
    request_digest: str
    product_id: str
    actor_ref: str
    request: IntelligenceBuildStartV1
    authority_use: AuthorityUseReceiptV1Alpha1


class IntelligenceBuildExecutor(Protocol):
    async def start(self, build: AuthorizedIntelligenceBuild) -> IntelligenceResourcePageV1Alpha1: ...


class IntelligenceBuildAuthorizationPort(Protocol):
    async def resolve_authority_use(
        self,
        *,
        context,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        authority: str,
        grant_ref: str,
        evaluated_at: datetime,
    ) -> AuthorityUseReceiptV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class IntelligenceBuildHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceBuildAuthorizationPort
    executor: IntelligenceBuildExecutor


class IntelligenceBuildError(RuntimeError):
    """Base failure for the governed Intelligence build boundary."""


class IntelligenceBuildDenied(IntelligenceBuildError):
    """Current verified identity or Core authority denied the build."""


class IntelligenceBuildUnauthenticated(IntelligenceBuildError):
    """Verified token lacks a usable product-scoped identity."""


class IntelligenceBuildUnavailable(IntelligenceBuildError):
    """The host cannot currently execute or receipt a build."""


class IntelligenceBuildContractConflict(IntelligenceBuildError):
    """A host result did not preserve the authorized request."""


class _UnavailableIntelligenceBuildExecutor:
    async def start(self, build: AuthorizedIntelligenceBuild) -> IntelligenceResourcePageV1Alpha1:
        del build
        raise IntelligenceBuildUnavailable("no Intelligence build executor is registered")


def intelligence_build_runtime() -> IntelligenceBuildHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceBuildHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=governed_state),
        executor=_UnavailableIntelligenceBuildExecutor(),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceBuildUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or INTELLIGENCE_BUILD_AUTHORITY not in authorities:
        raise IntelligenceBuildDenied("Intelligence build authority is required")
    return actor_ref, product_id


def _request_identity(*, request: IntelligenceBuildStartV1, product_id: str, actor_ref: str) -> tuple[str, str]:
    material = request.model_dump(mode="json", exclude={"authority_grant_ref"})
    raw_digest = canonical_hash([product_id, actor_ref, material])
    return f"intelligence_build:{raw_digest[:32]}", f"sha256:{raw_digest}"


async def start_intelligence_build(
    *,
    request: IntelligenceBuildStartV1,
    user: dict,
    runtime: IntelligenceBuildHttpRuntime,
) -> IntelligenceBuildResultV1:
    """Authorize one reviewed plan and delegate only its domain execution."""

    actor_ref, product_id = _verified_claims(user)
    evaluated_at = datetime.now(UTC)
    if request.requested_at.tzinfo is None or request.requested_at.utcoffset() is None:
        raise IntelligenceBuildContractConflict("requested_at must include a timezone")
    if request.requested_at.astimezone(UTC) > evaluated_at + timedelta(minutes=5):
        raise IntelligenceBuildContractConflict("requested_at cannot be materially in the future")
    build_id, request_digest = _request_identity(
        request=request,
        product_id=product_id,
        actor_ref=actor_ref,
    )

    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=evaluated_at,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        authority_use = await runtime.authority.resolve_authority_use(
            context=authentication.runtime_context(),
            use_subject_ref=build_id,
            use_subject_digest=request_digest,
            operation=INTELLIGENCE_BUILD_OPERATION,
            authority=INTELLIGENCE_BUILD_AUTHORITY,
            grant_ref=request.authority_grant_ref,
            evaluated_at=evaluated_at,
        )
        exact_authority = AuthorityUseReceiptV1Alpha1.model_validate(authority_use.model_dump(mode="python"))
        if (
            exact_authority.product_id != product_id
            or exact_authority.actor_ref != actor_ref
            or exact_authority.use_subject_ref != build_id
            or exact_authority.use_subject_digest != request_digest
            or exact_authority.operation != INTELLIGENCE_BUILD_OPERATION
            or exact_authority.authority != INTELLIGENCE_BUILD_AUTHORITY
            or exact_authority.grant_ref != request.authority_grant_ref
        ):
            raise IntelligenceBuildContractConflict("authority resolver changed the Intelligence build request")

        page = IntelligenceResourcePageV1Alpha1.model_validate(
            (
                await runtime.executor.start(
                    AuthorizedIntelligenceBuild(
                        build_id=build_id,
                        request_digest=request_digest,
                        product_id=product_id,
                        actor_ref=actor_ref,
                        request=request,
                        authority_use=exact_authority,
                    )
                )
            ).model_dump(mode="python")
        )
        if page.product_id != product_id or page.actor_ref != actor_ref:
            raise IntelligenceBuildContractConflict("build executor crossed the authenticated product scope")
        return IntelligenceBuildResultV1(
            build_id=build_id,
            request_digest=request_digest,
            product_id=product_id,
            actor_ref=actor_ref,
            accepted_at=evaluated_at,
            authority_use=exact_authority,
            resource_page=page,
        )
    except GovernedCompositionAuthorityError as exc:
        raise IntelligenceBuildDenied("current Core grant denied the build") from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise IntelligenceBuildContractConflict("Intelligence build result failed exact validation") from exc
    except IntelligenceBuildError:
        raise
    except Exception as exc:
        raise IntelligenceBuildUnavailable("Intelligence build execution is unavailable") from exc


__all__ = [
    "INTELLIGENCE_BUILD_AUTHORITY",
    "INTELLIGENCE_BUILD_OPERATION",
    "AuthorizedIntelligenceBuild",
    "IntelligenceBuildContractConflict",
    "IntelligenceBuildAuthorizationPort",
    "IntelligenceBuildDenied",
    "IntelligenceBuildExecutor",
    "IntelligenceBuildHttpRuntime",
    "IntelligenceBuildResultV1",
    "IntelligenceBuildStartV1",
    "IntelligenceBuildUnauthenticated",
    "IntelligenceBuildUnavailable",
    "intelligence_build_runtime",
    "start_intelligence_build",
]
