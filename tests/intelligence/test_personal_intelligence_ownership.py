from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.personal_intelligence_ownership import (
    PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND,
    PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
    PersonalIntelligenceDeletePreviewStale,
    PersonalIntelligenceOwnershipError,
    PersonalIntelligenceOwnershipService,
)
from ace.core.contracts import canonical_json
from ace.core.personal_intelligence_ownership import (
    BACKUP_NON_REAPPEARANCE_LIMITATION,
    PORTABILITY_SCOPE,
    SURVIVING_DERIVATIVE_DISCLOSURE,
    PersonalIntelligenceDeleteConfirmationV1Alpha1,
    PersonalIntelligenceDeletePreviewRequestV1Alpha1,
    PersonalIntelligenceExportRequestV1Alpha1,
)
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.testing.immutable_records import InMemoryImmutableRecordStore

NOW = datetime(2026, 8, 13, 16, 0, tzinfo=UTC)
PRODUCT_ID = "product:personal-intelligence"
ACTOR_REF = "actor:owner"


class _AllowOwner:
    def __init__(self) -> None:
        self.operations: list[str] = []

    async def authorize(self, *, authenticated_context, operation, subject_ref, evaluated_at) -> None:
        assert authenticated_context.product_id == PRODUCT_ID
        assert authenticated_context.actor_ref == ACTOR_REF
        assert subject_ref
        assert evaluated_at.tzinfo is not None
        self.operations.append(operation)


class _DenyOwner:
    async def authorize(self, **kwargs) -> None:
        raise PermissionError("owner authorization denied")


def _service(store: InMemoryImmutableRecordStore) -> PersonalIntelligenceOwnershipService:
    return PersonalIntelligenceOwnershipService(store=store, authorization=_AllowOwner())


def _context(*, product_id: str = PRODUCT_ID) -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=ACTOR_REF,
        authentication_receipt_ref="authentication_receipt:personal-owner",
        authentication_receipt_digest=f"sha256:{'1' * 64}",
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _record(
    *,
    key: str,
    secret: str,
    product_id: str = PRODUCT_ID,
    space: str = "live",
    order: int = 0,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=space,
        record_kind="brief" if space == "live" else "source",
        record_key=key,
        payload_contract="example.intelligence/v1",
        payload={"secret": secret, "source_ref": f"source:{key}"},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=1),
        processing_order=order,
    )


async def _seed(
    store: InMemoryImmutableRecordStore,
    *records: ImmutableRecordV1,
    transaction_key: str = "seed",
) -> None:
    grouped: dict[tuple[str, str], list[ImmutableRecordV1]] = {}
    for item in records:
        grouped.setdefault((item.product_id, item.record_space), []).append(item)
    for index, ((product_id, record_space), items) in enumerate(grouped.items()):
        normalized = tuple(
            item.model_copy(update={"processing_order": item_index}) for item_index, item in enumerate(items)
        )
        await store.append(
            AppendOnlyTransactionRequestV1(
                product_id=product_id,
                record_space=record_space,
                transaction_key=f"{transaction_key}-{index}",
                records=normalized,
                submitted_at=NOW,
            )
        )


def _preview_request() -> PersonalIntelligenceDeletePreviewRequestV1Alpha1:
    return PersonalIntelligenceDeletePreviewRequestV1Alpha1(
        authenticated_context=_context(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _confirmation(preview) -> PersonalIntelligenceDeleteConfirmationV1Alpha1:
    return PersonalIntelligenceDeleteConfirmationV1Alpha1(
        authenticated_context=_context(),
        preview=preview,
        confirmation_digest=str(preview.confirmation_digest),
        confirmed_at=NOW + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_export_is_canonical_product_scoped_evidence_without_restore_claim() -> None:
    store = InMemoryImmutableRecordStore()
    first = _record(key="brief:1", secret="alpha")
    second = _record(key="source:1", secret="beta", space="prepared")
    foreign = _record(key="brief:foreign", secret="foreign", product_id="product:foreign")
    await _seed(store, first, second, foreign)
    service = _service(store)

    request = PersonalIntelligenceExportRequestV1Alpha1(
        authenticated_context=_context(),
        requested_at=NOW,
    )
    artifact = await service.export(request)
    replay = await service.export(request)

    assert artifact == replay
    assert artifact.product_id == PRODUCT_ID
    assert artifact.record_count == 2
    assert tuple(item.storage_id for item in artifact.records) == tuple(sorted((first.storage_id, second.storage_id)))
    assert artifact.portability_scope == PORTABILITY_SCOPE
    assert artifact.runnable_restore_supported is False
    assert artifact.artifact_digest == replay.artifact_digest
    assert "foreign" not in canonical_json(artifact)


@pytest.mark.asyncio
async def test_export_fails_closed_when_host_authorization_denies() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    service = PersonalIntelligenceOwnershipService(store=store, authorization=_DenyOwner())

    with pytest.raises(PersonalIntelligenceOwnershipError, match="failed exact validation"):
        await service.export(
            PersonalIntelligenceExportRequestV1Alpha1(
                authenticated_context=_context(),
                requested_at=NOW,
            )
        )


@pytest.mark.asyncio
async def test_delete_requires_exact_confirmation_digest() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    service = _service(store)
    preview = await service.preview_delete(_preview_request())

    with pytest.raises(ValidationError, match="confirmation_digest"):
        PersonalIntelligenceDeleteConfirmationV1Alpha1(
            authenticated_context=_context(),
            preview=preview,
            confirmation_digest=f"sha256:{'f' * 64}",
            confirmed_at=NOW + timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_changed_record_set_invalidates_preview_without_deleting_anything() -> None:
    store = InMemoryImmutableRecordStore()
    original = _record(key="brief:1", secret="alpha")
    await _seed(store, original)
    service = _service(store)
    preview = await service.preview_delete(_preview_request())
    later = _record(key="brief:2", secret="later")
    await _seed(store, later, transaction_key="later")

    with pytest.raises(PersonalIntelligenceDeletePreviewStale, match="changed after preview"):
        await service.confirm_delete(_confirmation(preview))

    remaining = await store.scan_product_records(product_id=PRODUCT_ID)
    assert {item.storage_id for item in remaining} == {original.storage_id, later.storage_id}


@pytest.mark.asyncio
async def test_confirmed_delete_removes_content_and_leaves_content_free_replayable_proof() -> None:
    store = InMemoryImmutableRecordStore()
    first = _record(key="brief:1", secret="TOP-SECRET-ALPHA")
    second = _record(key="source:1", secret="TOP-SECRET-BETA", space="prepared")
    foreign = _record(key="brief:foreign", secret="FOREIGN", product_id="product:foreign")
    await _seed(store, first, second, foreign)
    service = _service(store)
    preview = await service.preview_delete(_preview_request())
    confirmation = _confirmation(preview)

    result = await service.confirm_delete(confirmation)
    replay = await service.confirm_delete(confirmation)

    assert result == replay
    assert result.proof.removed_count == 2
    assert result.proof.primary_store_non_reappearance_verified is True
    assert result.proof.backup_non_reappearance_proven is False
    assert result.proof.backup_limitation == BACKUP_NON_REAPPEARANCE_LIMITATION
    remaining = await store.scan_product_records(product_id=PRODUCT_ID)
    assert len(remaining) == 1
    proof_record = remaining[0]
    assert proof_record.record_space == PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE
    assert proof_record.record_kind == PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND
    proof_material = canonical_json(proof_record)
    assert "TOP-SECRET-ALPHA" not in proof_material
    assert "TOP-SECRET-BETA" not in proof_material
    assert str(first.storage_id) not in proof_material
    assert str(second.storage_id) not in proof_material
    foreign_remaining = await store.scan_product_records(product_id="product:foreign")
    assert tuple(item.storage_id for item in foreign_remaining) == (foreign.storage_id,)


@pytest.mark.asyncio
async def test_atomic_erasure_failure_preserves_all_content_and_no_proof() -> None:
    store = InMemoryImmutableRecordStore()
    first = _record(key="brief:1", secret="alpha")
    second = _record(key="source:1", secret="beta", space="prepared")
    await _seed(store, first, second)
    service = _service(store)
    preview = await service.preview_delete(_preview_request())
    store.fail_after_records = 1

    with pytest.raises(PersonalIntelligenceOwnershipError, match="failed atomically"):
        await service.confirm_delete(_confirmation(preview))

    remaining = await store.scan_product_records(product_id=PRODUCT_ID)
    assert {item.storage_id for item in remaining} == {first.storage_id, second.storage_id}
    assert all(item.record_space != PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE for item in remaining)


def test_surviving_derivative_disclosure_enumerates_decision_9_kinds():
    # Decision 9: deletion must cover OR explicitly enumerate as surviving every derived artifact —
    # embeddings, graph rows, caches, indexes. The additive disclosure names them explicitly so a
    # person can tell exactly what is not removed.
    text = SURVIVING_DERIVATIVE_DISCLOSURE.lower()
    for kind in ("embedding", "graph", "index", "cache"):
        assert kind in text, f"disclosure must explicitly name '{kind}' as possibly surviving (Decision 9)"


@pytest.mark.asyncio
async def test_pre_field_records_revalidate_to_identical_identity():
    # Backward-compat (PR #241 review): a preview/proof written BEFORE the additive disclosure field
    # — i.e. whose stored JSON lacks it — must revalidate to the SAME identity digest. The field is
    # defaulted and excluded from identity derivation, so replaying a pre-#241 record does not fail
    # (unlike editing the persisted backup_limitation Literal, which would break replay).
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    service = _service(store)
    preview = await service.preview_delete(_preview_request())
    proof = (await service.confirm_delete(_confirmation(preview))).proof

    for instance in (preview, proof):
        # Records are stored and re-loaded as JSON, so simulate an old record by round-tripping
        # through JSON with the field removed (the contract is strict; model_validate_json is the
        # real replay path).
        raw = json.loads(instance.model_dump_json())
        assert raw["surviving_derivative_disclosure"] == SURVIVING_DERIVATIVE_DISCLOSURE
        del raw["surviving_derivative_disclosure"]  # simulate a record persisted before the field

        revalidated = type(instance).model_validate_json(json.dumps(raw))

        # The default fills in on load, and the identity is unchanged (field excluded from the digest),
        # so the whole record — id and digest included — reopens identically.
        assert revalidated.surviving_derivative_disclosure == SURVIVING_DERIVATIVE_DISCLOSURE
        assert json.loads(revalidated.model_dump_json(exclude={"surviving_derivative_disclosure"})) == raw
