"""Authorized application service for the unified Intelligence resource plane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourcePageState,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
)

RESOURCE_QUERY_OPERATION = "query_intelligence_resources"
RESOURCE_QUERY_AUTHORITY = "read_intelligence_resources"


class IntelligenceResourcePlaneError(RuntimeError):
    """A resource query failed closed before exposing a projection."""


class IntelligenceResourcePlaneAuthorizationPort(Protocol):
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
class IntelligenceResourceProjectionBatch:
    """One rebuildable adapter result; never authoritative state."""

    records: tuple[IntelligenceResourceRecordV1Alpha1, ...]
    state: IntelligenceResourcePageState = IntelligenceResourcePageState.COMPLETE
    degraded_reason_refs: tuple[str, ...] = ()


class IntelligenceResourceProjectionReader(Protocol):
    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch: ...


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IntelligenceResourcePlaneError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _sort_key(record: IntelligenceResourceRecordV1Alpha1) -> tuple[datetime, str, str, int]:
    reference = record.reference
    return (
        reference.available_at,
        reference.resource_kind.value,
        reference.resource_id,
        reference.revision,
    )


def _revalidate_query(value: IntelligenceResourceQueryV1Alpha1) -> IntelligenceResourceQueryV1Alpha1:
    try:
        return IntelligenceResourceQueryV1Alpha1.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceResourcePlaneError("resource query failed exact revalidation") from exc


def _revalidate_batch(value: IntelligenceResourceProjectionBatch) -> IntelligenceResourceProjectionBatch:
    if not isinstance(value, IntelligenceResourceProjectionBatch):
        raise IntelligenceResourcePlaneError("resource projection reader returned an unsupported batch")
    try:
        records = tuple(
            IntelligenceResourceRecordV1Alpha1.model_validate(record.model_dump(mode="python"))
            for record in value.records
        )
        state = IntelligenceResourcePageState(value.state)
        reasons = tuple(value.degraded_reason_refs)
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceResourcePlaneError("resource projection batch failed exact revalidation") from exc
    if state is IntelligenceResourcePageState.COMPLETE and reasons:
        raise IntelligenceResourcePlaneError("complete projection batch cannot declare degraded reasons")
    if state is IntelligenceResourcePageState.DEGRADED and not reasons:
        raise IntelligenceResourcePlaneError("degraded projection batch requires explicit reason references")
    return IntelligenceResourceProjectionBatch(records=records, state=state, degraded_reason_refs=reasons)


class IntelligenceResourcePlaneService:
    """Query one authorized resource view without owning persistence or authority."""

    def __init__(
        self,
        *,
        reader: IntelligenceResourceProjectionReader,
        authority: IntelligenceResourcePlaneAuthorizationPort,
    ) -> None:
        self.reader = reader
        self.authority = authority

    async def query(
        self,
        request: IntelligenceResourceQueryV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> IntelligenceResourcePageV1Alpha1:
        exact = _revalidate_query(request)
        evaluated = _aware(evaluated_at, name="evaluated_at")
        context = exact.authenticated_context
        if not (exact.available_at <= evaluated < context.expires_at):
            raise IntelligenceResourcePlaneError("resource query evaluation fell outside its temporal window")

        authority_use = await self.authority.resolve_authority_use(
            context=context,
            use_subject_ref=str(exact.query_id),
            use_subject_digest=str(exact.query_digest),
            operation=RESOURCE_QUERY_OPERATION,
            authority=RESOURCE_QUERY_AUTHORITY,
            grant_ref=exact.authority_grant_ref,
            evaluated_at=evaluated,
        )
        try:
            resolved = AuthorityUseReceiptV1Alpha1.model_validate(authority_use.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise IntelligenceResourcePlaneError("resource query authority receipt failed revalidation") from exc
        if (
            resolved.product_id != exact.product_id
            or resolved.actor_ref != context.actor_ref
            or resolved.authenticated_context != context
            or resolved.use_subject_ref != exact.query_id
            or resolved.use_subject_digest != exact.query_digest
            or resolved.operation != RESOURCE_QUERY_OPERATION
            or resolved.authority != RESOURCE_QUERY_AUTHORITY
            or resolved.grant_ref != exact.authority_grant_ref
            or resolved.evaluated_at != evaluated
        ):
            raise IntelligenceResourcePlaneError("authority resolver did not preserve the exact resource query")

        batch = _revalidate_batch(
            await self.reader.read(
                query=exact,
                after=exact.cursor,
                limit=exact.page_size + 1,
            )
        )
        if len(batch.records) > exact.page_size + 1:
            raise IntelligenceResourcePlaneError("resource reader exceeded the bounded page request")
        ordering = [_sort_key(item) for item in batch.records]
        if ordering != sorted(ordering) or len(ordering) != len(set(ordering)):
            raise IntelligenceResourcePlaneError("resource reader returned unstable or duplicate ordering")

        requested_kinds = set(exact.resource_kinds)
        requested_subjects = set(exact.subject_refs)
        for item in batch.records:
            reference = item.reference
            if reference.product_id != exact.product_id:
                raise IntelligenceResourcePlaneError("resource reader crossed product scope")
            if reference.resource_kind not in requested_kinds:
                raise IntelligenceResourcePlaneError("resource reader returned an unrequested resource kind")
            if reference.as_of > exact.as_of or reference.available_at > exact.available_at:
                raise IntelligenceResourcePlaneError("resource reader crossed the query temporal cutoff")
            if requested_subjects and requested_subjects.isdisjoint(item.subject_refs):
                raise IntelligenceResourcePlaneError("resource reader returned an item outside the subject filter")
            if exact.cursor is not None:
                cursor_key = (
                    exact.cursor.after_available_at,
                    exact.cursor.after_resource_kind.value,
                    exact.cursor.after_resource_id,
                    exact.cursor.after_revision,
                )
                if _sort_key(item) <= cursor_key:
                    raise IntelligenceResourcePlaneError("resource reader did not advance beyond the cursor")

        visible = batch.records[: exact.page_size]
        next_cursor = None
        if len(batch.records) > exact.page_size:
            last = visible[-1].reference
            next_cursor = IntelligenceResourceCursorV1Alpha1(
                query_id=str(exact.query_id),
                after_available_at=last.available_at,
                after_resource_kind=last.resource_kind,
                after_resource_id=last.resource_id,
                after_revision=last.revision,
            )

        return IntelligenceResourcePageV1Alpha1(
            query_id=str(exact.query_id),
            query_digest=str(exact.query_digest),
            product_id=exact.product_id,
            actor_ref=context.actor_ref,
            as_of=exact.as_of,
            available_at=exact.available_at,
            evaluated_at=evaluated,
            state=batch.state,
            items=visible,
            next_cursor=next_cursor,
            degraded_reason_refs=batch.degraded_reason_refs,
            authority_use=resolved,
        )


__all__ = [
    "RESOURCE_QUERY_AUTHORITY",
    "RESOURCE_QUERY_OPERATION",
    "IntelligenceResourcePlaneAuthorizationPort",
    "IntelligenceResourcePlaneError",
    "IntelligenceResourcePlaneService",
    "IntelligenceResourceProjectionBatch",
    "IntelligenceResourceProjectionReader",
]
