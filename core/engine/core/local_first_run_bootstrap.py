"""Production governed local first-run bootstrap for the fixed local owner.

PI13 §8.1 (corrected WS3, part a): wire the five existing local-owner grants
that ``ace setup`` creates into the real domain-activation, Intelligence-build,
and resource-read paths. This module composes only existing production
services and durable stores:

- activation authority bindings are derived from the pack's own authority
  requests onto the exact fixed grants (no new grant vocabulary, no minting);
- every required authority-grant governed-state head is resolved at point of
  use through ``RecordedIntelligenceActivationAuthority`` with its exact
  identity and precondition rules;
- the durable reviewed activation approval is minted once through the
  existing ``approve_intelligence_activation`` service and thereafter exactly
  resumed from its append-only record — never re-minted, never hand-written;
- the returned start request is the existing ``IntelligenceBuildStartV1Alpha2``
  shape whose ``/start`` execution resolves the authorized Intelligence build
  receipt and whose resource page resolves the ``observe_read`` authority-use
  receipt from the same governed heads.

When setup is incomplete or durable material crossed, the bootstrap fails
closed and names the exact missing or conflicting authority. Echo resolvers,
fabricated receipts or hashes, injected heads, and testing stores have no
seam here: the durable runtime factory composes the SurrealDB-backed stores.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ace.application import AuthorityBindingV1
from ace.application.intelligence_build_execution import IntelligenceBuildStartV1Alpha2
from ace.application.intelligence_build_plan_binding import BoundIntelligenceBuildPlanV1Alpha1
from ace.core.records import ImmutableRecordStore
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from ace.core.state import (
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateStore,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_activation_authority import (
    INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION,
    INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
    INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
    LOCAL_OWNER_BUILD_GRANT_REF,
    LOCAL_OWNER_READ_GRANT_REF,
    IntelligenceActivationApprovalConflict,
    IntelligenceActivationApprovalDenied,
    IntelligenceActivationApprovalError,
    IntelligenceActivationApprovalUnavailable,
    IntelligenceActivationApproveRequestV1Alpha1,
    RecordedIntelligenceActivationAuthority,
    ReviewedIntelligenceActivationApprovalV1Alpha1,
    approve_intelligence_activation,
    intelligence_activation_start_request,
    verified_local_intelligence_owner,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_GRANTS

LOCAL_FIRST_RUN_BUILD_AUTHORITY_VERSION = "ace.host.local-first-run-build-authority/v1alpha1"

_GRANTS_BY_AUTHORITY = {spec.authority_class.value: spec for spec in LOCAL_OWNER_GRANTS}


class LocalFirstRunBootstrapError(RuntimeError):
    """The governed local first-run bootstrap failed closed."""


class LocalFirstRunBootstrapDenied(LocalFirstRunBootstrapError):
    """The verified caller is not the fixed local Intelligence owner."""


class LocalFirstRunAuthorityMissing(LocalFirstRunBootstrapError):
    """A required fixed local-owner authority is missing, inactive, or unresolvable."""


class LocalFirstRunBootstrapConflict(LocalFirstRunBootstrapError):
    """Durable or submitted material crossed the exact reviewed first-run identity."""


class LocalFirstRunBootstrapUnavailable(LocalFirstRunBootstrapError):
    """Durable governed or append-only storage cannot currently be read or written."""


class PackAuthorityRequest(Protocol):
    """The exact identity a pack authority request exposes; keeps this host
    adapter off the ``ace.intelligence`` bounded context."""

    @property
    def request_id(self) -> str: ...

    @property
    def authority(self) -> str: ...


def local_owner_authority_bindings(
    authority_requests: Iterable[PackAuthorityRequest],
) -> tuple[AuthorityBindingV1, ...]:
    """Bind each pack authority request to the exact matching fixed local-owner grant.

    This is derivation, not authority: no grant is resolved or exercised here.
    An authority the five fixed grants do not cover fails closed by name so
    setup gaps and pack vocabulary drift surface as exact configuration errors.
    """

    bindings: list[AuthorityBindingV1] = []
    for request in authority_requests:
        spec = _GRANTS_BY_AUTHORITY.get(request.authority)
        if spec is None:
            raise LocalFirstRunAuthorityMissing(
                f"no fixed local-owner grant covers authority '{request.authority}' "
                f"requested by '{request.request_id}'; the fixed setup grants cover only: "
                f"{', '.join(sorted(_GRANTS_BY_AUTHORITY))}"
            )
        bindings.append(
            AuthorityBindingV1(
                request_id=request.request_id,
                authority=request.authority,
                grant_ref=spec.grant_ref,
            )
        )
    return tuple(bindings)


class LocalFirstRunGrantHeadV1Alpha1(BaseModel):
    """One required fixed grant resolved from its exact current governed head."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_ref: str
    authority: str
    grant: ResolvedAuthorityGrantV1
    head: GovernedStateHeadPreconditionV1Alpha1


class LocalFirstRunBuildAuthorityV1Alpha1(BaseModel):
    """The exact durable first-run authority material a clean local owner holds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["ace.host.local-first-run-build-authority/v1alpha1"] = LOCAL_FIRST_RUN_BUILD_AUTHORITY_VERSION
    product_id: str
    actor_ref: str
    bound_plan_id: str
    bound_plan_digest: str
    grants: tuple[LocalFirstRunGrantHeadV1Alpha1, ...]
    approval: ResolvedApprovalReceiptV1
    resumed: bool
    start_request: IntelligenceBuildStartV1Alpha2


@dataclass(frozen=True, slots=True)
class LocalFirstRunBootstrapRuntime:
    records: ImmutableRecordStore
    governed_state: GovernedStateStore


def local_first_run_bootstrap_runtime() -> LocalFirstRunBootstrapRuntime:
    """The durable production composition: SurrealDB-backed stores only."""

    return LocalFirstRunBootstrapRuntime(
        records=SurrealImmutableRecordStore(pool),
        governed_state=SurrealGovernedStateStore(pool),
    )


def _exact_bound_identity(bound_plan: BoundIntelligenceBuildPlanV1Alpha1) -> None:
    spec = bound_plan.activation_spec
    if (
        bound_plan.bound_plan_id is None
        or bound_plan.bound_plan_digest is None
        or bound_plan.execution_request_id is None
        or bound_plan.execution_request_digest is None
        or spec.spec_id is None
        or spec.spec_hash is None
    ):
        raise LocalFirstRunBootstrapConflict("bound activation plan is missing exact identity")


def _validated_activation_bindings(bound_plan: BoundIntelligenceBuildPlanV1Alpha1) -> None:
    for binding in bound_plan.activation_spec.authority_bindings:
        spec = _GRANTS_BY_AUTHORITY.get(binding.authority)
        if spec is None:
            raise LocalFirstRunAuthorityMissing(
                f"no fixed local-owner grant covers activation authority '{binding.authority}' "
                f"bound by '{binding.request_id}'"
            )
        if binding.grant_ref != spec.grant_ref:
            raise LocalFirstRunBootstrapConflict(
                f"activation authority binding '{binding.request_id}' names '{binding.grant_ref}' "
                f"instead of the fixed local-owner grant '{spec.grant_ref}'"
            )


async def _resolved_grant_heads(
    *,
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1,
    product_id: str,
    resolver: RecordedIntelligenceActivationAuthority,
    governed_state: GovernedStateStore,
    evaluated_at: datetime,
) -> tuple[LocalFirstRunGrantHeadV1Alpha1, ...]:
    required: dict[str, str] = {}
    for binding in bound_plan.activation_spec.authority_bindings:
        required.setdefault(binding.grant_ref, binding.authority)
    required.setdefault(LOCAL_OWNER_BUILD_GRANT_REF, "intelligence_build")
    required.setdefault(LOCAL_OWNER_READ_GRANT_REF, "observe_read")

    resolved: list[LocalFirstRunGrantHeadV1Alpha1] = []
    for grant_ref, authority in required.items():
        try:
            grant = await resolver.resolve_grant(
                grant_ref=grant_ref,
                product_id=product_id,
                authority=authority,
                effective_at=evaluated_at,
            )
            head = await governed_state.load_head(
                state_kind=AUTHORITY_GRANT_STATE_KIND,
                product_id=product_id,
                state_id=grant_ref,
            )
        except IntelligenceActivationApprovalDenied as exc:
            raise LocalFirstRunAuthorityMissing(
                f"required fixed local-owner grant did not resolve: {grant_ref} ({authority}); "
                "run `ace setup` to create or repair the fixed owner grants"
            ) from exc
        except IntelligenceActivationApprovalUnavailable as exc:
            raise LocalFirstRunBootstrapUnavailable("durable authority-grant storage is unavailable") from exc
        if head is None:
            raise LocalFirstRunAuthorityMissing(
                f"required fixed local-owner grant head disappeared during resolution: {grant_ref}"
            )
        try:
            precondition = GovernedStateHeadPreconditionV1Alpha1.from_head(head)
        except ValueError as exc:
            raise LocalFirstRunBootstrapConflict(
                f"current governed head for {grant_ref} failed exact validation"
            ) from exc
        resolved.append(
            LocalFirstRunGrantHeadV1Alpha1(
                grant_ref=grant_ref,
                authority=authority,
                grant=grant,
                head=precondition,
            )
        )
    return tuple(resolved)


async def _resumed_approval(
    *,
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1,
    product_id: str,
    actor_ref: str,
    records: ImmutableRecordStore,
    resolver: RecordedIntelligenceActivationAuthority,
    evaluated_at: datetime,
) -> ResolvedApprovalReceiptV1 | None:
    spec = bound_plan.activation_spec
    try:
        recorded = await records.read_as_of(
            product_id=product_id,
            record_space=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_SPACE,
            record_kind=INTELLIGENCE_ACTIVATION_APPROVAL_RECORD_KIND,
            available_at=evaluated_at,
        )
    except Exception as exc:
        raise LocalFirstRunBootstrapUnavailable("durable activation-approval storage is unavailable") from exc

    candidates: list[ReviewedIntelligenceActivationApprovalV1Alpha1] = []
    for record in recorded:
        if record.payload_contract != INTELLIGENCE_ACTIVATION_APPROVAL_ARTIFACT_VERSION:
            continue
        raw_spec = record.payload.get("activation_spec_id") if isinstance(record.payload, dict) else None
        if raw_spec != spec.spec_id:
            continue
        try:
            candidates.append(ReviewedIntelligenceActivationApprovalV1Alpha1.model_validate(record.payload))
        except ValueError as exc:
            raise LocalFirstRunBootstrapConflict(
                "recorded activation approval for this exact activation failed revalidation"
            ) from exc
    if not candidates:
        return None
    if len(candidates) > 1:
        raise LocalFirstRunBootstrapConflict(
            "more than one durable activation approval binds this exact activation specification"
        )
    artifact = candidates[0]
    if (
        artifact.product_id != product_id
        or artifact.actor_ref != actor_ref
        or artifact.bound_plan_id != bound_plan.bound_plan_id
        or artifact.bound_plan_digest != bound_plan.bound_plan_digest
        or artifact.execution_request_id != bound_plan.execution_request_id
        or artifact.execution_request_digest != bound_plan.execution_request_digest
        or artifact.activation_spec_digest != f"sha256:{spec.spec_hash}"
    ):
        raise LocalFirstRunBootstrapConflict(
            "the durable activation approval for this activation binds a different exact bound plan"
        )
    try:
        return await resolver.resolve_approval(
            receipt_ref=artifact.approval.receipt_ref,
            product_id=product_id,
            subject_ref=str(spec.spec_id),
            actor_ref=actor_ref,
            effective_at=evaluated_at,
        )
    except IntelligenceActivationApprovalDenied as exc:
        raise LocalFirstRunBootstrapConflict("recorded activation approval is stale or mismatched") from exc
    except IntelligenceActivationApprovalUnavailable as exc:
        raise LocalFirstRunBootstrapUnavailable("durable activation-approval storage is unavailable") from exc


async def bootstrap_local_first_run_build_authority(
    *,
    bound_plan: BoundIntelligenceBuildPlanV1Alpha1,
    user: dict,
    runtime: LocalFirstRunBootstrapRuntime,
    approved_at: datetime,
    evaluated_at: datetime | None = None,
) -> LocalFirstRunBuildAuthorityV1Alpha1:
    """Obtain or exactly resume the governed first-run authority for one bound plan.

    Idempotent for the same exact bound plan: the first call mints the durable
    reviewed activation approval through the existing approval service; every
    later call resumes the identical recorded receipt and start request. A
    durable approval that binds a different bound plan for the same activation
    specification fails closed instead of being replaced.

    ``approved_at`` is the reviewed request's own approval timestamp and is
    used only when minting the durable approval; it never moves the authority
    evaluation point. ``evaluated_at`` is the server's authority-evaluation
    time — current grant heads and approval resolution — and defaults to
    server-now, so an identical replay after a revocation fails closed instead
    of resolving stale authority as of the old client timestamp.
    """

    try:
        actor_ref, product_id = verified_local_intelligence_owner(user)
    except IntelligenceActivationApprovalDenied as exc:
        raise LocalFirstRunBootstrapDenied(str(exc)) from exc

    plan_request = bound_plan.binding_request.plan.request
    if plan_request.product_id != product_id or plan_request.actor_ref != actor_ref:
        raise LocalFirstRunBootstrapDenied("bound plan crossed the fixed local-owner scope")
    _exact_bound_identity(bound_plan)
    _validated_activation_bindings(bound_plan)

    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    resolver = RecordedIntelligenceActivationAuthority(
        records=runtime.records,
        governed_state=runtime.governed_state,
    )
    grants = await _resolved_grant_heads(
        bound_plan=bound_plan,
        product_id=product_id,
        resolver=resolver,
        governed_state=runtime.governed_state,
        evaluated_at=now,
    )

    approval = await _resumed_approval(
        bound_plan=bound_plan,
        product_id=product_id,
        actor_ref=actor_ref,
        records=runtime.records,
        resolver=resolver,
        evaluated_at=now,
    )
    if approval is not None:
        try:
            start_request = intelligence_activation_start_request(bound=bound_plan, approval=approval)
        except IntelligenceActivationApprovalConflict as exc:
            raise LocalFirstRunBootstrapConflict(str(exc)) from exc
        resumed = True
    else:
        try:
            result = await approve_intelligence_activation(
                request=IntelligenceActivationApproveRequestV1Alpha1(
                    decision="approve",
                    bound_plan=bound_plan,
                    approved_at=approved_at.astimezone(UTC),
                ),
                user=user,
                records=runtime.records,
            )
        except IntelligenceActivationApprovalDenied as exc:
            raise LocalFirstRunBootstrapDenied(str(exc)) from exc
        except IntelligenceActivationApprovalConflict as exc:
            raise LocalFirstRunBootstrapConflict(str(exc)) from exc
        except IntelligenceActivationApprovalUnavailable as exc:
            raise LocalFirstRunBootstrapUnavailable(str(exc)) from exc
        except IntelligenceActivationApprovalError as exc:
            raise LocalFirstRunBootstrapUnavailable(str(exc)) from exc
        approval = result.approval
        start_request = result.start_request
        resumed = False

    return LocalFirstRunBuildAuthorityV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        bound_plan_id=str(bound_plan.bound_plan_id),
        bound_plan_digest=str(bound_plan.bound_plan_digest),
        grants=grants,
        approval=approval,
        resumed=resumed,
        start_request=start_request,
    )


__all__ = [
    "LOCAL_FIRST_RUN_BUILD_AUTHORITY_VERSION",
    "LocalFirstRunAuthorityMissing",
    "LocalFirstRunBootstrapConflict",
    "LocalFirstRunBootstrapDenied",
    "LocalFirstRunBootstrapError",
    "LocalFirstRunBootstrapRuntime",
    "LocalFirstRunBootstrapUnavailable",
    "LocalFirstRunBuildAuthorityV1Alpha1",
    "LocalFirstRunGrantHeadV1Alpha1",
    "PackAuthorityRequest",
    "bootstrap_local_first_run_build_authority",
    "local_first_run_bootstrap_runtime",
    "local_owner_authority_bindings",
]
