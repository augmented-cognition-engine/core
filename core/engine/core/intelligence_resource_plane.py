"""Supported host composition for the governed Intelligence resource plane.

This is the only legacy Core host edge into the public ACE Application layer.
The HTTP adapter depends on this host boundary and never imports public ACE
packages directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_QUERY_AUTHORITY,
    ActionResourceProjectionReader,
    AgentMemoryResourceProjectionReader,
    AgentResourceProjectionReader,
    CompositeIntelligenceResourceProjectionReader,
    DecisionOutcomeFeedbackResourceProjectionReader,
    IntelligenceBuilderResourceProjectionReader,
    IntelligenceLedgerResourceProjectionReader,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourcePlaneAuthorizationPort,
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
    IntelligenceResourceQueryV1Alpha1,
    LiveSourceResourceProjectionReader,
    MonitoringResourceProjectionReader,
    RecordedSourceReadinessResourceProjectionReader,
)
from ace.application.intelligence_build_execution import AuthorizedIntelligenceBuild
from ace.application.intelligence_resource_plane import (
    IntelligenceResourcePageState,
    IntelligenceResourceRecordV1Alpha1,
)
from ace.core import ImmutableRecordPersistenceError, ImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.extensions.registry import registered_intelligence_resource_projection_providers


class IntelligenceResourceHttpQueryV1(BaseModel):
    """HTTP selector; authenticated context comes only from verified claims."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    resource_kinds: tuple[IntelligenceResourceKind, ...] = Field(min_length=1, max_length=32)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    as_of: datetime
    available_at: datetime
    page_size: int = Field(ge=1, le=200)
    cursor: IntelligenceResourceCursorV1Alpha1 | None = None


@dataclass(frozen=True, slots=True)
class IntelligenceResourceHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceResourcePlaneAuthorizationPort


class IntelligenceResourceHttpDenied(RuntimeError):
    """The verified principal or current Core grant denied the query."""


class IntelligenceResourceHttpUnauthenticated(RuntimeError):
    """The verified token did not contain a usable product-scoped principal."""


class IntelligenceResourceHttpUnavailable(RuntimeError):
    """Required authentication evidence could not be persisted."""


class IntelligenceResourceHttpContractConflict(RuntimeError):
    """The query could not preserve the exact resource-plane contract."""


class IntelligenceResourceProjectionCompositionError(ValueError):
    """An installed projection provider could not preserve the generic contract."""


# An installed provider's degraded reasons are conservatively bounded: they are
# opaque references, not messages, so a small count of short unique strings is
# always enough and an unbounded or repetitive set is a contract violation.
MAX_INSTALLED_PROVIDER_DEGRADED_REASONS = 8
MAX_INSTALLED_PROVIDER_DEGRADED_REASON_CHARS = 200
MAX_INSTALLED_PROVIDER_DEGRADED_REASON_TOTAL_CHARS = 1_024


def _resource_sort_key(record: IntelligenceResourceRecordV1Alpha1) -> tuple[datetime, str, str, int]:
    reference = record.reference
    return (reference.available_at, reference.resource_kind.value, reference.resource_id, reference.revision)


class _InstalledIntelligenceResourceProjectionReader:
    """Instantiate one optional provider only when its declared kinds are queried.

    Every batch an installed provider returns is re-validated here, before it
    can reach the composite and the generic resource-plane service.  The
    service already fails a query that crosses product, kind, temporal, subject,
    ordering, or page bounds — but it fails the *whole page*, which would let one
    optional product provider take unrelated Core kinds down with it.  This
    wrapper therefore enforces the same invariants itself and converts any
    violation into bounded degradation of this provider's claimed kinds only.
    """

    def __init__(self, *, definition, records: ImmutableRecordStore, supported_kinds) -> None:
        self.definition = definition
        self.records = records
        self.supported_kinds = supported_kinds

    def _degraded_reasons(self, requested_kinds) -> tuple[str, ...]:
        identity = f"{self.definition.extension_id}:{self.definition.provider_name}"
        fingerprint = sha256(identity.encode("utf-8")).hexdigest()[:16]
        return tuple(
            f"degraded_reason:projection-provider-unavailable:{kind.value}:{fingerprint}"
            for kind in sorted(set(requested_kinds) & self.supported_kinds, key=lambda item: item.value)
        )

    @staticmethod
    def _validated_reason_refs(value) -> tuple[str, ...]:
        """Bound a provider's degraded references before they leave this host."""

        if not isinstance(value, (tuple, list)):
            raise TypeError("installed projection provider returned unbounded degraded references")
        reasons = tuple(value)
        if len(reasons) > MAX_INSTALLED_PROVIDER_DEGRADED_REASONS or len(set(reasons)) != len(reasons):
            raise TypeError("installed projection provider returned excessive or duplicate degraded references")
        total = 0
        for item in reasons:
            if not isinstance(item, str) or not item or len(item) > MAX_INSTALLED_PROVIDER_DEGRADED_REASON_CHARS:
                raise TypeError("installed projection provider returned an invalid degraded reference")
            total += len(item)
        if total > MAX_INSTALLED_PROVIDER_DEGRADED_REASON_TOTAL_CHARS:
            raise TypeError("installed projection provider returned oversized degraded references")
        return reasons

    def _validated_records(self, *, query, after, limit, records) -> tuple[IntelligenceResourceRecordV1Alpha1, ...]:
        if not isinstance(records, (tuple, list)) or len(records) > limit:
            raise TypeError("installed projection provider exceeded the bounded page request")
        exact = tuple(
            IntelligenceResourceRecordV1Alpha1.model_validate(record.model_dump(mode="python")) for record in records
        )
        claimed = set(query.resource_kinds) & self.supported_kinds
        subjects = set(query.subject_refs)
        for item in exact:
            reference = item.reference
            if reference.product_id != query.product_id:
                raise TypeError("installed projection provider crossed product scope")
            if reference.resource_kind not in claimed:
                raise TypeError("installed projection provider returned an unclaimed resource kind")
            if reference.as_of > query.as_of or reference.available_at > query.available_at:
                raise TypeError("installed projection provider crossed the query temporal cutoff")
            if subjects and subjects.isdisjoint(item.subject_refs):
                raise TypeError("installed projection provider returned an item outside the subject filter")
        # A record's own degraded_reason_refs is provider-supplied material, exactly
        # like the batch-level reasons below: never forwarded, even when it is a
        # single unique string that already satisfies the contract's reference
        # pattern.  Every kind here was just confirmed claimed, so the deterministic
        # host reason is always available to replace it with.
        exact = tuple(
            item.model_copy(update={"degraded_reason_refs": self._degraded_reasons((item.reference.resource_kind,))})
            if item.degraded_reason_refs
            else item
            for item in exact
        )
        ordering = [_resource_sort_key(item) for item in exact]
        if ordering != sorted(ordering) or len(ordering) != len(set(ordering)):
            raise TypeError("installed projection provider returned unstable or duplicate ordering")
        if after is not None:
            cursor_key = (
                after.after_available_at,
                after.after_resource_kind.value,
                after.after_resource_id,
                after.after_revision,
            )
            if any(key <= cursor_key for key in ordering):
                raise TypeError("installed projection provider did not advance beyond the cursor")
        return exact

    async def read(self, *, query, after, limit) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        if not (requested & self.supported_kinds):
            return IntelligenceResourceProjectionBatch(records=())
        try:
            contributor = self.definition.factory(self.records)
            actual_kinds = getattr(contributor, "supported_kinds")
            if (
                not isinstance(actual_kinds, frozenset)
                or not actual_kinds
                or any(not isinstance(kind, IntelligenceResourceKind) for kind in actual_kinds)
                or actual_kinds != self.supported_kinds
                or not callable(getattr(contributor, "read", None))
            ):
                raise TypeError("installed projection provider is malformed")
            batch = await contributor.read(query=query, after=after, limit=limit)
            if not isinstance(batch, IntelligenceResourceProjectionBatch):
                raise TypeError("installed projection provider returned an unsupported batch")
            records = self._validated_records(query=query, after=after, limit=limit, records=batch.records)
            state = IntelligenceResourcePageState(batch.state)
            # Bound-check the provider's reasons (count, type, length, duplicates)
            # so a malformed batch still fails closed, but never forward the
            # provider's own text even once it is valid: any nonempty batch-level
            # degradation is replaced with the same deterministic host reason used
            # on the exception path below, scoped to requested-and-claimed kinds.
            reasons = self._validated_reason_refs(batch.degraded_reason_refs)
            if (state is IntelligenceResourcePageState.COMPLETE and reasons) or (
                state is IntelligenceResourcePageState.DEGRADED and not reasons
            ):
                raise TypeError("installed projection provider returned an inconsistent batch")
            return IntelligenceResourceProjectionBatch(
                records=records,
                state=state,
                degraded_reason_refs=(self._degraded_reasons(requested) if reasons else ()),
            )
        except Exception:
            # Deliberately opaque: the provider's own exception text or batch
            # content never reaches the caller, and only this provider's claimed
            # kinds degrade — unrelated Core kinds keep their exact page.
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=self._degraded_reasons(requested),
            )


def intelligence_resource_runtime() -> IntelligenceResourceHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceResourceHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=governed_state),
    )


def intelligence_resource_projection_reader(records: ImmutableRecordStore) -> IntelligenceResourceProjectionReader:
    """Compose all disjoint rebuildable public projection contributors."""

    contributors: list[IntelligenceResourceProjectionReader] = [
        IntelligenceBuilderResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        ActionResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        AgentMemoryResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        AgentResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        IntelligenceLedgerResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        MonitoringResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        DecisionOutcomeFeedbackResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        LiveSourceResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        RecordedSourceReadinessResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
    ]
    for definition in registered_intelligence_resource_projection_providers():
        try:
            raw_kinds = definition.supported_kinds
            if not isinstance(raw_kinds, tuple) or not raw_kinds or len(raw_kinds) > 32:
                continue
            valid_kinds: set[IntelligenceResourceKind] = set()
            for value in raw_kinds:
                if not isinstance(value, str):
                    continue
                try:
                    valid_kinds.add(IntelligenceResourceKind(value))
                except ValueError:
                    continue
            declared_kinds = frozenset(valid_kinds)
        except (AttributeError, TypeError):
            continue
        if not declared_kinds:
            continue
        contributors.append(
            _InstalledIntelligenceResourceProjectionReader(
                definition=definition,
                records=records,
                supported_kinds=declared_kinds,
            )
        )
    try:
        return CompositeIntelligenceResourceProjectionReader(*contributors)
    except ValueError as exc:
        raise IntelligenceResourceProjectionCompositionError(
            "installed resource projection providers claim overlapping generic kinds"
        ) from exc


class CoreIntelligenceBuildResourcePagePort:
    """Resolve one exact read page for an already-authorized build invocation."""

    def __init__(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
        authority: IntelligenceResourcePlaneAuthorizationPort,
    ) -> None:
        self.build = build
        self.records = records
        self.authority = authority

    async def query(
        self,
        *,
        resource_kinds: tuple[IntelligenceResourceKind, ...],
        subject_refs: tuple[str, ...],
        as_of: datetime,
        available_at: datetime,
        evaluated_at: datetime,
        page_size: int = 200,
    ) -> IntelligenceResourcePageV1Alpha1:
        context = self.build.authority_use.authenticated_context
        if context.product_id != self.build.product_id or context.actor_ref != self.build.actor_ref:
            raise IntelligenceResourceHttpContractConflict("build context crossed its authorized scope")
        request = IntelligenceResourceQueryV1Alpha1(
            authenticated_context=context,
            product_id=self.build.product_id,
            authority_grant_ref=self.build.request.resource_authority_grant_ref,
            resource_kinds=resource_kinds,
            subject_refs=subject_refs,
            as_of=as_of,
            available_at=available_at,
            page_size=page_size,
        )
        return await IntelligenceResourcePlaneService(
            reader=intelligence_resource_projection_reader(self.records),
            authority=self.authority,
        ).query(request, evaluated_at=evaluated_at)


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceResourceHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_QUERY_AUTHORITY not in authorities:
        raise IntelligenceResourceHttpDenied("intelligence read authority is required")
    return actor_ref, product_id


async def query_intelligence_resource_page_with_query(
    *,
    selector: IntelligenceResourceHttpQueryV1,
    user: dict,
    runtime: IntelligenceResourceHttpRuntime,
) -> tuple[IntelligenceResourceQueryV1Alpha1, IntelligenceResourcePageV1Alpha1]:
    """Bind verified host context to one authorized public resource query.

    Returns the exact resolved query alongside its page so a caller composing
    a further truthful read (e.g. a live system-projection enrichment) can
    revalidate the page against the same query material without repeating
    authentication or point-of-use ``observe_read`` authorization.
    """

    actor_ref, product_id = _verified_claims(user)
    evaluated_at = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=evaluated_at,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = IntelligenceResourceQueryV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            resource_kinds=selector.resource_kinds,
            subject_refs=selector.subject_refs,
            as_of=selector.as_of,
            available_at=selector.available_at,
            page_size=selector.page_size,
            cursor=selector.cursor,
        )
        page = await IntelligenceResourcePlaneService(
            reader=intelligence_resource_projection_reader(runtime.records),
            authority=runtime.authority,
        ).query(request, evaluated_at=evaluated_at)
        return request, page
    except GovernedCompositionAuthorityError as exc:
        raise IntelligenceResourceHttpDenied("current Core grant denied the query") from exc
    except ImmutableRecordPersistenceError as exc:
        raise IntelligenceResourceHttpUnavailable("authentication evidence is unavailable") from exc
    except (IntelligenceResourcePlaneError, TypeError, ValueError) as exc:
        raise IntelligenceResourceHttpContractConflict("resource query contract could not be preserved") from exc


async def query_intelligence_resource_page(
    *,
    selector: IntelligenceResourceHttpQueryV1,
    user: dict,
    runtime: IntelligenceResourceHttpRuntime,
) -> IntelligenceResourcePageV1Alpha1:
    """Bind verified host context to one authorized public resource query."""

    _, page = await query_intelligence_resource_page_with_query(selector=selector, user=user, runtime=runtime)
    return page


__all__ = [
    "MAX_INSTALLED_PROVIDER_DEGRADED_REASONS",
    "MAX_INSTALLED_PROVIDER_DEGRADED_REASON_CHARS",
    "MAX_INSTALLED_PROVIDER_DEGRADED_REASON_TOTAL_CHARS",
    "IntelligenceResourceHttpContractConflict",
    "IntelligenceResourceHttpDenied",
    "IntelligenceResourceHttpQueryV1",
    "IntelligenceResourceHttpRuntime",
    "IntelligenceResourceHttpUnauthenticated",
    "IntelligenceResourceHttpUnavailable",
    "IntelligenceResourceProjectionCompositionError",
    "CoreIntelligenceBuildResourcePagePort",
    "IntelligenceResourcePageV1Alpha1",
    "intelligence_resource_projection_reader",
    "intelligence_resource_runtime",
    "query_intelligence_resource_page",
    "query_intelligence_resource_page_with_query",
]
