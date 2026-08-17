"""Host-composed truthful live/proposal system-projection resource-state read.

This is the composition endpoint described by
``docs/design/atrium-live-domain-health-projection-v1.md``. It proves the
accepted-plan-to-activation-revision association against the actual current
production path — prepare -> bind -> approve -> start -> active Builder
session -> canonical activation — not a separate scheme. It carries no new
persistence, authority, activation, session, resource, or health framework:
it reuses ``DurableIntelligenceBuildHostComposer``'s existing durable
Builder-artifact bootstrap (the same logic ``/start`` uses to grant build
execution ports) and composes it with the existing plan-projection and
resource-plane read boundaries over one shared immutable record store and one
shared governed-state store/authority adapter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ace.application.intelligence_build_host import (
    DurableIntelligenceBuildHostComposer,
    IntelligenceBuildHostCompositionError,
)
from ace.application.intelligence_build_plan_binding import BoundIntelligenceBuildPlanV1Alpha1
from ace.application.intelligence_system_projection import (
    IntelligenceSystemProjectionV1Alpha1,
    project_intelligence_system_resource_state,
)
from ace.core import CoreAuthorityResolver, ImmutableRecordStore
from ace.core.state import GovernedStateStore
from core.engine.core.agent_composition_runtime import GovernedStateRuntimeUseResolver
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    IntelligenceActivationApprovalDenied,
    IntelligenceActivationApprovalUnavailable,
    RecordedIntelligenceActivationAuthority,
)
from core.engine.core.intelligence_build_plan import (
    IntelligenceBuildPlanConflict,
    IntelligenceBuildPlanHttpRuntime,
    IntelligenceBuildPlanNotFound,
    IntelligenceBuildPlanUnauthenticated,
    IntelligenceBuildPlanUnavailable,
    intelligence_build_plan_runtime,
    project_intelligence_build_plan,
)
from core.engine.core.intelligence_resource_plane import (
    IntelligenceResourceHttpContractConflict,
    IntelligenceResourceHttpDenied,
    IntelligenceResourceHttpQueryV1,
    IntelligenceResourceHttpRuntime,
    IntelligenceResourceHttpUnauthenticated,
    IntelligenceResourceHttpUnavailable,
    query_intelligence_resource_page_with_query,
)


class IntelligenceBuildResourceStateRequestV1(BaseModel):
    """The exact bound plan, its approval receipt reference, and the existing
    resource selector only. No client-authored health, coverage, or mode
    value is accepted anywhere in this envelope.
    """

    model_config = ConfigDict(extra="forbid")

    bound_plan: dict[str, Any]
    activation_approval_receipt_ref: str
    selector: IntelligenceResourceHttpQueryV1

    def exact_bound_plan(self) -> BoundIntelligenceBuildPlanV1Alpha1:
        return BoundIntelligenceBuildPlanV1Alpha1.model_validate_json(json.dumps(self.bound_plan))


@dataclass(frozen=True, slots=True)
class IntelligenceBuildResourceStateRuntime:
    """One shared immutable record store and one shared governed store/authority adapter."""

    records: ImmutableRecordStore
    governed_state: GovernedStateStore
    activation_authority: CoreAuthorityResolver
    build_plan: IntelligenceBuildPlanHttpRuntime
    resources: IntelligenceResourceHttpRuntime
    composer: DurableIntelligenceBuildHostComposer


class IntelligenceBuildResourceStateError(RuntimeError):
    """Base failure for the host-composed live/proposal resource-state read."""


class IntelligenceBuildResourceStateUnauthenticated(IntelligenceBuildResourceStateError):
    """Verified token or bound plan crossed product/actor scope."""


class IntelligenceBuildResourceStateNotFound(IntelligenceBuildResourceStateError):
    """The reviewed plan names an onboarding profile that is not installed."""


class IntelligenceBuildResourceStateDenied(IntelligenceBuildResourceStateError):
    """The current Core grant denied the point-of-use resource read."""


class IntelligenceBuildResourceStateConflict(IntelligenceBuildResourceStateError):
    """Supplied material is stale, forged, ambiguous, or otherwise not exact."""


class IntelligenceBuildResourceStateUnavailable(IntelligenceBuildResourceStateError):
    """Required durable material could not be read."""


def intelligence_build_resource_state_runtime() -> IntelligenceBuildResourceStateRuntime:
    """Compose one runtime from one shared record store and one shared governed store."""

    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    runtime_use = GovernedStateRuntimeUseResolver(governed_state=governed_state)
    build_plan = intelligence_build_plan_runtime()
    return IntelligenceBuildResourceStateRuntime(
        records=records,
        governed_state=governed_state,
        activation_authority=RecordedIntelligenceActivationAuthority(records=records, governed_state=governed_state),
        build_plan=build_plan,
        resources=IntelligenceResourceHttpRuntime(records=records, authority=runtime_use),
        composer=DurableIntelligenceBuildHostComposer(
            governed_state=governed_state,
            runtime_use=runtime_use,
            packs=build_plan.packs,
        ),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceBuildResourceStateUnauthenticated("verified token lacks product scope")
    return actor_ref, product_id


async def project_intelligence_build_resource_state(
    *,
    request: IntelligenceBuildResourceStateRequestV1,
    user: dict,
    runtime: IntelligenceBuildResourceStateRuntime,
) -> IntelligenceSystemProjectionV1Alpha1:
    """Enrich one exact bound plan's projection from the actual accepted current path.

    ``mode`` becomes ``live`` only when: the exact bound plan's activation
    specification is durably approved (independently reloaded, never trusted
    from the client body); exactly one currently ``ACTIVE`` Builder session's
    activation plan/receipt artifacts durably exist for it and reload without
    drift (reusing ``DurableIntelligenceBuildHostComposer``'s existing
    bootstrap — the same logic the current ``/start`` path uses to grant
    build execution ports); the reloaded canonical activation revision and
    its current head agree; the canonical spec/Pack/overlay/bindings agree
    with the bound plan; and the authorized resource page fully closes. Every
    other case preserves ``mode: proposed`` with an explicit gap instead of
    guessing; structurally invalid, crossed, or ambiguous material fails
    closed instead.
    """

    actor_ref, product_id = _verified_claims(user)
    evaluated_at = datetime.now(UTC)

    try:
        bound_plan = request.exact_bound_plan()
    except (TypeError, ValueError) as exc:
        raise IntelligenceBuildResourceStateConflict("bound plan failed exact structural revalidation") from exc

    plan = bound_plan.binding_request.plan
    if plan.request.product_id != product_id or plan.request.actor_ref != actor_ref:
        raise IntelligenceBuildResourceStateUnauthenticated("bound plan crossed verified product or actor scope")

    try:
        plan_projection = await project_intelligence_build_plan(
            plan=plan,
            user=user,
            runtime=runtime.build_plan,
        )
    except IntelligenceBuildPlanUnauthenticated as exc:
        raise IntelligenceBuildResourceStateUnauthenticated(str(exc)) from exc
    except IntelligenceBuildPlanNotFound as exc:
        raise IntelligenceBuildResourceStateNotFound(str(exc)) from exc
    except IntelligenceBuildPlanConflict as exc:
        raise IntelligenceBuildResourceStateConflict(str(exc)) from exc
    except IntelligenceBuildPlanUnavailable as exc:
        raise IntelligenceBuildResourceStateUnavailable(str(exc)) from exc

    spec = bound_plan.activation_spec
    activation_revision = None
    try:
        # Independent re-resolution: the stored approval receipt must exist
        # and must itself name this exact bound-plan activation subject and
        # the current verified actor. A missing or mismatched approval is the
        # ordinary not-yet-approved case, not an error — the projection stays
        # proposed below.
        activation_approval = await runtime.activation_authority.resolve_approval(
            receipt_ref=request.activation_approval_receipt_ref,
            product_id=product_id,
            subject_ref=str(spec.spec_id),
            actor_ref=actor_ref,
            effective_at=evaluated_at,
        )
    except IntelligenceActivationApprovalDenied:
        activation_approval = None
    except IntelligenceActivationApprovalUnavailable as exc:
        raise IntelligenceBuildResourceStateUnavailable("reviewed activation approval is unavailable") from exc

    if activation_approval is not None:
        try:
            binding = await runtime.composer.resolve_active_binding(
                product_id=product_id,
                actor_ref=actor_ref,
                evaluated_at=evaluated_at,
                activation_approval_subject_ref=str(spec.spec_id),
                activation_approval_receipt_ref=request.activation_approval_receipt_ref,
                activation_approval=activation_approval,
                records=runtime.records,
                activation_authority=runtime.activation_authority,
            )
        except IntelligenceBuildHostCompositionError as exc:
            raise IntelligenceBuildResourceStateConflict(str(exc)) from exc
        if binding is not None:
            revision = binding.prepared_binding.revision
            if revision.spec != spec:
                raise IntelligenceBuildResourceStateConflict(
                    "canonical activation spec, Pack, overlay, and bindings do not agree with the bound plan"
                )
            activation_revision = binding.prepared_binding.reference

    try:
        query, page = await query_intelligence_resource_page_with_query(
            selector=request.selector,
            user=user,
            runtime=runtime.resources,
        )
    except IntelligenceResourceHttpUnauthenticated as exc:
        raise IntelligenceBuildResourceStateUnauthenticated(str(exc)) from exc
    except IntelligenceResourceHttpDenied as exc:
        raise IntelligenceBuildResourceStateDenied(str(exc)) from exc
    except IntelligenceResourceHttpUnavailable as exc:
        raise IntelligenceBuildResourceStateUnavailable(str(exc)) from exc
    except IntelligenceResourceHttpContractConflict as exc:
        raise IntelligenceBuildResourceStateConflict(str(exc)) from exc

    try:
        return project_intelligence_system_resource_state(
            projection=plan_projection,
            query=query,
            page=page,
            activation_revision=activation_revision,
        )
    except (TypeError, ValueError) as exc:
        raise IntelligenceBuildResourceStateConflict(
            "resource-state projection could not preserve its exact contract"
        ) from exc


__all__ = [
    "IntelligenceBuildResourceStateConflict",
    "IntelligenceBuildResourceStateDenied",
    "IntelligenceBuildResourceStateError",
    "IntelligenceBuildResourceStateNotFound",
    "IntelligenceBuildResourceStateRequestV1",
    "IntelligenceBuildResourceStateRuntime",
    "IntelligenceBuildResourceStateUnauthenticated",
    "IntelligenceBuildResourceStateUnavailable",
    "intelligence_build_resource_state_runtime",
    "project_intelligence_build_resource_state",
]
