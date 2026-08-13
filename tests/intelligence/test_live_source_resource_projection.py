from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application import LiveSourceResourceProjectionReader
from ace.core import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    LiveSourceIngressRecordKind,
)
from tests.intelligence.test_live_source_ingress import BASE, PRODUCT, _Clock, _environment

pytestmark = pytest.mark.unit


def _query(*kinds: IntelligenceResourceKind) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:analyst",
            authentication_receipt_ref="authentication_receipt:source-projection",
            authentication_receipt_digest="sha256:" + "d" * 64,
            authenticated_at=BASE,
            expires_at=BASE + timedelta(minutes=5),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=kinds,
        as_of=BASE + timedelta(minutes=1),
        available_at=BASE + timedelta(minutes=1),
        page_size=20,
    )


@pytest.mark.asyncio
async def test_successful_governed_capture_projects_redacted_connection_and_source() -> None:
    env = await _environment()
    await env.service.admit(request=env.request, pack=env.pack)

    batch = await LiveSourceResourceProjectionReader(store=env.record_store).read(
        query=_query(IntelligenceResourceKind.CONNECTION, IntelligenceResourceKind.SOURCE),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert [item.reference.resource_kind for item in batch.records] == [
        IntelligenceResourceKind.CONNECTION,
        IntelligenceResourceKind.SOURCE,
    ]
    connection, source = batch.records
    assert connection.reference.revision == source.reference.revision == 1
    assert source.provenance == (connection.reference,)
    assert connection.payload is not None
    assert source.payload is not None
    connection_payload = connection.payload.parsed_value()
    source_payload = source.payload.parsed_value()
    assert connection_payload["source_definition_ref"] == env.request.source_definition_ref
    assert source_payload["captured_payload_redacted"] is True
    serialized = f"{connection_payload}{source_payload}"
    assert "captured_payload_json" not in serialized
    assert "requested_uri" not in serialized
    assert "effective_uri" not in serialized
    assert "resolved_ip_addresses" not in serialized
    assert "locator" not in serialized

    restarted = await LiveSourceResourceProjectionReader(store=env.record_store).read(
        query=_query(IntelligenceResourceKind.CONNECTION, IntelligenceResourceKind.SOURCE),
        after=None,
        limit=20,
    )
    assert restarted == batch


@pytest.mark.asyncio
async def test_repeated_capture_preserves_exact_revision_lineage() -> None:
    first = await _environment()
    await first.service.admit(request=first.request, pack=first.pack)
    second = await _environment(
        record_store=first.record_store,
        clock=_Clock(
            BASE + timedelta(seconds=20),
            BASE + timedelta(seconds=22),
            BASE + timedelta(seconds=23),
        ),
    )
    second_request = second.request.model_copy(
        update={
            "idempotency_key": "live-ingress:two",
            "requested_at": BASE + timedelta(seconds=10),
            "request_id": None,
            "request_digest": None,
        }
    )
    second_request = type(second.request).model_validate(second_request.model_dump(mode="python"))
    await second.service.admit(request=second_request, pack=second.pack)

    batch = await LiveSourceResourceProjectionReader(store=second.record_store).read(
        query=_query(IntelligenceResourceKind.CONNECTION, IntelligenceResourceKind.SOURCE),
        after=None,
        limit=20,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    by_kind = {
        kind: sorted(
            (item for item in batch.records if item.reference.resource_kind is kind),
            key=lambda item: item.reference.revision,
        )
        for kind in (IntelligenceResourceKind.CONNECTION, IntelligenceResourceKind.SOURCE)
    }
    for revisions in by_kind.values():
        assert [item.reference.revision for item in revisions] == [1, 2]
        assert revisions[1].supersedes == revisions[0].reference
        assert revisions[1].reference.resource_digest != revisions[0].reference.resource_digest
    assert by_kind[IntelligenceResourceKind.SOURCE][1].provenance == (
        by_kind[IntelligenceResourceKind.CONNECTION][1].reference,
    )


@pytest.mark.asyncio
async def test_partial_or_invalid_admission_degrades_without_exposing_source_material() -> None:
    env = await _environment()
    await env.service.admit(request=env.request, pack=env.pack)
    admission_storage_id = next(
        key
        for key, record in env.record_store.records.items()
        if record.record_kind == LiveSourceIngressRecordKind.SOURCE_ADMISSION.value
    )
    del env.record_store.records[admission_storage_id]

    batch = await LiveSourceResourceProjectionReader(store=env.record_store).read(
        query=_query(IntelligenceResourceKind.CONNECTION, IntelligenceResourceKind.SOURCE),
        after=None,
        limit=20,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:orphan-live-source-record",)


@pytest.mark.asyncio
async def test_source_health_is_not_fabricated_from_success_only_admission_records() -> None:
    env = await _environment()
    await env.service.admit(request=env.request, pack=env.pack)

    batch = await LiveSourceResourceProjectionReader(store=env.record_store).read(
        query=_query(IntelligenceResourceKind.SOURCE_HEALTH),
        after=None,
        limit=20,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == ("degraded_reason:unsupported-source_health",)
