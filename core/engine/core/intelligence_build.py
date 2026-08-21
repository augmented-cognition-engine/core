"""Governed host boundary for starting one personal Intelligence build.

Core owns authentication, authority use, and the stable HTTP material. A host
supplies the domain-neutral executor; domain repositories remain responsible
for source options, ontology vocabulary, watch policy, and briefing strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from ace.application import InstalledCompiledPackArtifactResolver, IntelligenceResourcePageV1Alpha1
from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildExecutor,
    IntelligenceBuildHostServices,
    IntelligenceBuildResourcePagePort,
    IntelligenceBuildStartV1,
    IntelligenceBuildStartV1Alpha2,
    ProductScopedImmutableRecordStore,
)
from ace.application.intelligence_build_host import DurableIntelligenceBuildHostComposer
from ace.application.intelligence_build_planning import intelligence_build_execution_identity
from ace.core import CoreAuthorityResolver, ImmutableRecordStore, ResolvedApprovalReceiptV1
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    IntelligenceActivationApprovalDenied,
    IntelligenceActivationApprovalUnavailable,
    RecordedIntelligenceActivationAuthority,
)
from core.engine.core.intelligence_build_cognition import (
    IntelligenceBuildCognitionUnavailable,
    ProductionIntelligenceBuildCognitionResolver,
)
from core.engine.core.intelligence_build_executor_registry import (
    IntelligenceBuildExecutorRegistryError,
    resolve_intelligence_build_executor,
)
from core.engine.core.intelligence_resource_plane import CoreIntelligenceBuildResourcePagePort

INTELLIGENCE_BUILD_AUTHORITY = "intelligence_build"
INTELLIGENCE_BUILD_OPERATION = "start_intelligence_build"
INTELLIGENCE_BUILD_RESULT_VERSION = "ace.http.intelligence-build-result/v1alpha1"


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


class IntelligenceBuildHostCompositionPort(Protocol):
    async def compose(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
        resources: IntelligenceBuildResourcePagePort,
        activation_authority: CoreAuthorityResolver,
    ) -> IntelligenceBuildHostServices: ...


@dataclass(frozen=True, slots=True)
class IntelligenceBuildHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceBuildAuthorizationPort
    activation_authority: CoreAuthorityResolver
    executor: IntelligenceBuildExecutor
    host_composer: IntelligenceBuildHostCompositionPort | None = None


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


class _InstalledIntelligenceBuildExecutor:
    async def start(
        self, build: AuthorizedIntelligenceBuild, host_services: IntelligenceBuildHostServices
    ) -> IntelligenceResourcePageV1Alpha1:
        try:
            executor = resolve_intelligence_build_executor(build.request.profile_id)
        except IntelligenceBuildExecutorRegistryError as exc:
            raise IntelligenceBuildUnavailable("installed Intelligence build executors are ambiguous") from exc
        if executor is None:
            raise IntelligenceBuildUnavailable(
                f"no Intelligence build executor is registered for profile: {build.request.profile_id}"
            )
        return await executor.start(build, host_services)


def intelligence_build_runtime() -> IntelligenceBuildHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    authority = GovernedStateRuntimeUseResolver(governed_state=governed_state)
    activation_authority = RecordedIntelligenceActivationAuthority(
        records=records,
        governed_state=governed_state,
    )
    cognition_resolver = ProductionIntelligenceBuildCognitionResolver(
        governed_state=governed_state,
        runtime_use=authority,
        records=records,
    )
    return IntelligenceBuildHttpRuntime(
        records=records,
        authority=authority,
        activation_authority=activation_authority,
        executor=_InstalledIntelligenceBuildExecutor(),
        host_composer=DurableIntelligenceBuildHostComposer(
            governed_state=governed_state,
            runtime_use=authority,
            packs=InstalledCompiledPackArtifactResolver.discover(),
            first_brief_cognition_resolver=cognition_resolver,
        ),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceBuildUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or not {
        INTELLIGENCE_BUILD_AUTHORITY,
        "observe_read",
    }.issubset(authorities):
        raise IntelligenceBuildDenied("Intelligence build and read authorities are required")
    return actor_ref, product_id


def _request_identity(*, request: IntelligenceBuildStartV1Alpha2, product_id: str, actor_ref: str) -> tuple[str, str]:
    material = request.model_dump(
        mode="json",
        exclude={
            "authority_grant_ref",
            "resource_authority_grant_ref",
            "activation_approval_receipt_ref",
        },
    )
    return intelligence_build_execution_identity(
        product_id=product_id,
        actor_ref=actor_ref,
        request_material=material,
    )


async def start_intelligence_build(
    *,
    request: IntelligenceBuildStartV1Alpha2,
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

        activation_approval = ResolvedApprovalReceiptV1.model_validate(
            (
                await runtime.activation_authority.resolve_approval(
                    receipt_ref=request.activation_approval_receipt_ref,
                    product_id=product_id,
                    subject_ref=request.activation_approval_subject_ref,
                    actor_ref=actor_ref,
                    effective_at=evaluated_at,
                )
            ).model_dump(mode="python")
        )
        if (
            activation_approval.receipt_ref != request.activation_approval_receipt_ref
            or activation_approval.product_id != product_id
            or activation_approval.subject_ref != request.activation_approval_subject_ref
            or activation_approval.actor_ref != actor_ref
            or activation_approval.approved_at > evaluated_at
        ):
            raise IntelligenceBuildContractConflict(
                "activation approval resolver changed the reviewed activation subject"
            )

        authorized_build = AuthorizedIntelligenceBuild(
            build_id=build_id,
            request_digest=request_digest,
            product_id=product_id,
            actor_ref=actor_ref,
            request=request,
            authority_use=exact_authority,
            activation_approval=activation_approval,
        )
        scoped_records = ProductScopedImmutableRecordStore(product_id=product_id, store=runtime.records)
        resources = CoreIntelligenceBuildResourcePagePort(
            build=authorized_build,
            records=scoped_records,
            authority=runtime.authority,
        )
        host_services = IntelligenceBuildHostServices(
            records=scoped_records,
            resources=resources,
            activation_authority=runtime.activation_authority,
        )
        if runtime.host_composer is not None:
            host_services = await runtime.host_composer.compose(
                build=authorized_build,
                records=scoped_records,
                resources=resources,
                activation_authority=runtime.activation_authority,
            )
        page = IntelligenceResourcePageV1Alpha1.model_validate(
            (await runtime.executor.start(authorized_build, host_services)).model_dump(mode="python")
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
    except IntelligenceActivationApprovalDenied as exc:
        raise IntelligenceBuildDenied("reviewed activation approval or authority denied the build") from exc
    except IntelligenceActivationApprovalUnavailable as exc:
        raise IntelligenceBuildUnavailable("reviewed activation authority is unavailable") from exc
    except IntelligenceBuildCognitionUnavailable as exc:
        raise IntelligenceBuildUnavailable(str(exc)) from exc
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
    "IntelligenceBuildHostCompositionPort",
    "IntelligenceBuildResultV1",
    "IntelligenceBuildStartV1",
    "IntelligenceBuildUnauthenticated",
    "IntelligenceBuildUnavailable",
    "intelligence_build_runtime",
    "start_intelligence_build",
]
