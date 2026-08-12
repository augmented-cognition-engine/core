from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application import IntelligenceResourcePlaneService as PublicIntelligenceResourcePlaneService
from ace.application.intelligence_resource_plane import (
    RESOURCE_QUERY_AUTHORITY,
    RESOURCE_QUERY_OPERATION,
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
    IntelligenceResourceProjectionBatch,
)
from ace.core.agent_composition import AuthorityClass
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence import IntelligenceResourceKind as PublicIntelligenceResourceKind
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1

pytestmark = pytest.mark.unit

PRODUCT = "product:resource-plane"
NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def _context(
    *,
    product_id: str = PRODUCT,
    actor_ref: str = "principal:analyst",
    receipt_suffix: str = "resource-plane",
    authenticated_at: datetime = NOW - timedelta(minutes=10),
) -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        authentication_receipt_ref=f"authentication_receipt:{receipt_suffix}",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=authenticated_at,
        expires_at=NOW + timedelta(minutes=30),
    )


def _reference(
    kind: IntelligenceResourceKind,
    suffix: str,
    *,
    product_id: str = PRODUCT,
    revision: int = 1,
    available_at: datetime = NOW,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=kind,
        resource_id=f"{kind.value}:{suffix}",
        resource_digest="sha256:" + (suffix[0] if suffix[0] in "abcdef" else "b") * 64,
        resource_contract=f"ace.intelligence.{kind.value.replace('_', '-')}/v1alpha1",
        revision=revision,
        as_of=available_at - timedelta(minutes=1),
        available_at=available_at,
    )


def _record(
    kind: IntelligenceResourceKind,
    suffix: str,
    *,
    product_id: str = PRODUCT,
    revision: int = 1,
    available_at: datetime = NOW,
    subject_refs: tuple[str, ...] = ("entity:ai-model",),
) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_reference(
            kind,
            suffix,
            product_id=product_id,
            revision=revision,
            available_at=available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"{kind.value} {suffix}",
        subject_refs=subject_refs,
        payload=CanonicalJsonValueV1Alpha1(value_json='{"status":"current"}'),
    )


def _query(
    *,
    kinds: tuple[IntelligenceResourceKind, ...] = (IntelligenceResourceKind.SIGNAL,),
    page_size: int = 2,
    cursor: IntelligenceResourceCursorV1Alpha1 | None = None,
    subject_refs: tuple[str, ...] = (),
) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=kinds,
        subject_refs=subject_refs,
        as_of=NOW,
        available_at=NOW,
        page_size=page_size,
        cursor=cursor,
    )


class _Authority:
    def __init__(self, *, mutate_operation: bool = False) -> None:
        self.calls: list[dict] = []
        self.mutate_operation = mutate_operation

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation="inspect" if self.mutate_operation else kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="d" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(minutes=20),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=kwargs["context"].product_id,
                state_id=kwargs["grant_ref"],
                sequence=1,
                revision_id="authority_revision:resource-read",
                commit_receipt_id="authority_receipt:resource-read",
            ),
        )


class _Reader:
    def __init__(
        self,
        records: tuple[IntelligenceResourceRecordV1Alpha1, ...],
        *,
        state: IntelligenceResourcePageState = IntelligenceResourcePageState.COMPLETE,
        reasons: tuple[str, ...] = (),
    ) -> None:
        self.records = records
        self.state = state
        self.reasons = reasons
        self.calls: list[dict] = []

    async def read(self, **kwargs) -> IntelligenceResourceProjectionBatch:
        self.calls.append(kwargs)
        return IntelligenceResourceProjectionBatch(
            records=self.records,
            state=self.state,
            degraded_reason_refs=self.reasons,
        )


def test_resource_plane_covers_the_complete_0_8_public_family() -> None:
    assert {item.value for item in IntelligenceResourceKind} == {
        "connection",
        "source",
        "source_health",
        "entity",
        "observation",
        "signal",
        "shift",
        "case",
        "brief",
        "monitor",
        "subscription",
        "agent",
        "decision",
        "action",
        "outcome",
        "feedback",
        "evidence_lineage",
        "uncertainty",
        "conflict",
        "semantic_revision",
        "context_manifest",
        "memory_use",
    }


def test_resource_plane_is_exported_through_the_supported_public_packages() -> None:
    assert PublicIntelligenceResourcePlaneService is IntelligenceResourcePlaneService
    assert PublicIntelligenceResourceKind is IntelligenceResourceKind
    assert IntelligenceResourceQueryV1Alpha1.model_json_schema()["type"] == "object"
    assert RESOURCE_QUERY_AUTHORITY == AuthorityClass.OBSERVE_READ.value


def test_query_identity_excludes_cursor_but_cursor_is_bound_to_the_exact_query() -> None:
    first = _query()
    cursor = IntelligenceResourceCursorV1Alpha1(
        query_id=str(first.query_id),
        after_available_at=NOW,
        after_resource_kind=IntelligenceResourceKind.SIGNAL,
        after_resource_id="signal:b",
        after_revision=1,
    )
    second = _query(cursor=cursor)
    assert second.query_id == first.query_id
    assert second.query_digest == first.query_digest
    assert cursor.reusable_authority is False

    with pytest.raises(ValueError, match="different query"):
        _query(
            cursor=cursor,
            kinds=(IntelligenceResourceKind.BRIEF,),
        )


def test_query_identity_survives_reauthentication_but_remains_actor_bound() -> None:
    first = _query()
    refreshed_context = _context(
        receipt_suffix="resource-plane-refresh",
        authenticated_at=NOW - timedelta(minutes=1),
    )
    refreshed = IntelligenceResourceQueryV1Alpha1(
        **{
            **first.model_dump(
                mode="python",
                exclude={"authenticated_context", "query_id", "query_digest"},
            ),
            "authenticated_context": refreshed_context,
        }
    )
    assert refreshed.query_id == first.query_id
    assert refreshed.query_digest == first.query_digest

    other_actor = IntelligenceResourceQueryV1Alpha1(
        **{
            **first.model_dump(
                mode="python",
                exclude={"authenticated_context", "query_id", "query_digest"},
            ),
            "authenticated_context": _context(actor_ref="principal:other"),
        }
    )
    assert other_actor.query_id != first.query_id


def test_historical_cutoff_is_authorized_at_request_time_not_authentication_time() -> None:
    context = _context(authenticated_at=NOW)
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=context,
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.BRIEF,),
        as_of=NOW - timedelta(days=2),
        available_at=NOW - timedelta(days=1),
        page_size=10,
    )
    assert query.available_at < context.authenticated_at


def test_record_requires_exact_provenance_scope_and_revision_lineage() -> None:
    prior = _reference(IntelligenceResourceKind.ENTITY, "a", revision=1)
    current = _reference(IntelligenceResourceKind.ENTITY, "a", revision=2, available_at=NOW + timedelta(minutes=1))
    record = IntelligenceResourceRecordV1Alpha1(
        reference=current,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Entity revision",
        provenance=(prior,),
        supersedes=prior,
        payload=CanonicalJsonValueV1Alpha1(value_json='{"name":"ACE"}'),
    )
    assert record.supersedes == prior

    with pytest.raises(ValueError, match="crossed product scope"):
        IntelligenceResourceRecordV1Alpha1(
            reference=current,
            availability=IntelligenceResourceAvailability.AVAILABLE,
            title="Invalid entity revision",
            provenance=(_reference(IntelligenceResourceKind.SOURCE, "b", product_id="product:other"),),
        )

    with pytest.raises(ValueError, match="immediately previous revision"):
        IntelligenceResourceRecordV1Alpha1(
            reference=_reference(
                IntelligenceResourceKind.ENTITY,
                "a",
                revision=3,
                available_at=NOW + timedelta(minutes=2),
            ),
            availability=IntelligenceResourceAvailability.AVAILABLE,
            title="Skipped entity lineage",
            supersedes=prior,
        )


def test_degraded_and_tombstoned_records_fail_closed_on_missing_truth() -> None:
    with pytest.raises(ValueError, match="requires explicit reason"):
        IntelligenceResourceRecordV1Alpha1(
            reference=_reference(IntelligenceResourceKind.SOURCE_HEALTH, "a"),
            availability=IntelligenceResourceAvailability.DEGRADED,
            title="Source health unavailable",
        )
    with pytest.raises(ValueError, match="cannot expose payload"):
        IntelligenceResourceRecordV1Alpha1(
            reference=_reference(IntelligenceResourceKind.MEMORY_USE, "a"),
            availability=IntelligenceResourceAvailability.TOMBSTONED,
            title="Erased memory use",
            payload=CanonicalJsonValueV1Alpha1(value_json="{}"),
        )


@pytest.mark.asyncio
async def test_authorized_query_returns_stable_page_and_next_cursor() -> None:
    records = (
        _record(IntelligenceResourceKind.SIGNAL, "a", available_at=NOW - timedelta(seconds=2)),
        _record(IntelligenceResourceKind.SIGNAL, "b", available_at=NOW - timedelta(seconds=1)),
        _record(IntelligenceResourceKind.SIGNAL, "c", available_at=NOW),
    )
    reader = _Reader(records)
    authority = _Authority()
    service = IntelligenceResourcePlaneService(reader=reader, authority=authority)
    request = _query(page_size=2)

    page = await service.query(request, evaluated_at=NOW + timedelta(minutes=1))

    assert page.items == records[:2]
    assert page.next_cursor is not None
    assert page.next_cursor.after_resource_id == "signal:b"
    assert page.next_cursor.query_id == request.query_id
    assert page.authority_use.operation == RESOURCE_QUERY_OPERATION
    assert page.authority_use.authority == RESOURCE_QUERY_AUTHORITY
    assert page.reusable_authority is False
    assert reader.calls[0]["limit"] == 3
    assert authority.calls[0]["use_subject_ref"] == request.query_id


@pytest.mark.asyncio
async def test_subject_filter_and_degraded_state_are_preserved() -> None:
    record = _record(
        IntelligenceResourceKind.BRIEF,
        "a",
        subject_refs=("entity:ai-model", "entity:provider"),
    )
    reader = _Reader(
        (record,),
        state=IntelligenceResourcePageState.DEGRADED,
        reasons=("degraded_reason:stale-secondary-source",),
    )
    page = await IntelligenceResourcePlaneService(reader=reader, authority=_Authority()).query(
        _query(
            kinds=(IntelligenceResourceKind.BRIEF,),
            subject_refs=("entity:provider",),
        ),
        evaluated_at=NOW + timedelta(minutes=1),
    )
    assert page.state is IntelligenceResourcePageState.DEGRADED
    assert page.degraded_reason_refs == ("degraded_reason:stale-secondary-source",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "message"),
    [
        (_record(IntelligenceResourceKind.SIGNAL, "a", product_id="product:other"), "crossed product scope"),
        (_record(IntelligenceResourceKind.BRIEF, "a"), "unrequested resource kind"),
        (
            _record(IntelligenceResourceKind.SIGNAL, "a", available_at=NOW + timedelta(minutes=1)),
            "temporal cutoff",
        ),
        (
            _record(IntelligenceResourceKind.SIGNAL, "a", subject_refs=("entity:other",)),
            "outside the subject filter",
        ),
    ],
)
async def test_reader_cannot_widen_query_scope(record, message: str) -> None:
    request = _query(subject_refs=("entity:ai-model",))
    with pytest.raises(IntelligenceResourcePlaneError, match=message):
        await IntelligenceResourcePlaneService(reader=_Reader((record,)), authority=_Authority()).query(
            request,
            evaluated_at=NOW + timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_reader_must_advance_stably_beyond_cursor() -> None:
    first = _query(page_size=1)
    cursor = IntelligenceResourceCursorV1Alpha1(
        query_id=str(first.query_id),
        after_available_at=NOW,
        after_resource_kind=IntelligenceResourceKind.SIGNAL,
        after_resource_id="signal:b",
        after_revision=1,
    )
    with pytest.raises(IntelligenceResourcePlaneError, match="did not advance"):
        await IntelligenceResourcePlaneService(
            reader=_Reader((_record(IntelligenceResourceKind.SIGNAL, "b"),)),
            authority=_Authority(),
        ).query(_query(page_size=1, cursor=cursor), evaluated_at=NOW + timedelta(minutes=1))


@pytest.mark.asyncio
async def test_authority_receipt_cannot_substitute_operation() -> None:
    with pytest.raises(IntelligenceResourcePlaneError, match="did not preserve"):
        await IntelligenceResourcePlaneService(
            reader=_Reader(()),
            authority=_Authority(mutate_operation=True),
        ).query(_query(), evaluated_at=NOW + timedelta(minutes=1))
