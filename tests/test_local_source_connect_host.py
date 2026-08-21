"""Tests for the Connect host persistence/replay repository (ACE PI13 WS2)."""

from __future__ import annotations

import hashlib
import json
import unittest.mock
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ace.application.intelligence_build_planning import INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT
from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingScope,
    authorize_local_source_connect,
    preview_local_source_connect,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.records import (
    ImmutableRecordPersistenceError,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.intelligence_builder_presentation import IntelligenceOnboardingProfileV1Alpha1
from ace.intelligence.contracts.pack import CompiledModuleV1
from ace.intelligence.contracts.source_mapping import (
    SOURCE_MAPPING_MODULE_VERSION,
    AttributeMappingV1,
    SourceMappingModuleV1,
    SourceMappingRuleV1,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.installed_intelligence_catalog import InstalledOnboardingProfile
from core.engine.core.intelligence_build_planner_registry import IntelligenceBuildPlannerRegistryError
from core.engine.core.local_source_connect import (
    LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
    LOCAL_SOURCE_CONNECT_RECORD_SPACE,
    LocalSourceConnectHostConflict,
    LocalSourceConnectHostDenied,
    LocalSourceConnectHostNotFound,
    LocalSourceConnectHostRuntime,
    LocalSourceConnectHostUnauthenticated,
    LocalSourceConnectHostUnavailable,
    LocalSourceConnectMappingScopeRequest,
    LocalSourceConnectPreviewHostRequest,
    LocalSourceConnectPreviewRuntime,
    LocalSourceConnectRecordConflict,
    LocalSourceConnectRecordRepository,
    LocalSourceConnectRecordUnavailable,
    authorize_local_source_connect_host,
    preview_local_source_connect_host,
)
from core.engine.core.source_snapshot_provider_registry import SourceSnapshotProviderRegistryError

NONEXISTENT_ROOT = "/nonexistent/pi13-ws2/host-local-root"

_CANONICAL_PAYLOAD = '{"text":"hello"}'
_PAYLOAD_DIGEST = "sha256:" + hashlib.sha256(_CANONICAL_PAYLOAD.encode("utf-8")).hexdigest()


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws2-host"})
    return CompiledPackRefV1(
        pack_id="pack-a",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _scope(mapping_id: str = "mapping-a", include: tuple[str, ...] = ("notes/*.md",)) -> LocalSourceMappingScope:
    return LocalSourceMappingScope(
        mapping_id=mapping_id,
        source_definition_ref="source-def-a",
        source_type_ref="source_type:local_files",
        subject_binding_id="subject-a",
        entity_type_id="entity-a",
        include=include,
    )


def _preview_request(**overrides) -> LocalSourceConnectPreviewRequest:
    values = dict(
        product_id="product:pi13-ws2-host",
        actor_ref="actor:reviewer-1",
        pack=_pack(),
        profile_id="profile-a",
        profile_digest=f"sha256:{canonical_hash({'profile': 'a'})}",
        source_group_id="source-group-a",
        expected_contribution="A cited orientation over the exact authorized local scope.",
        authorized_root=NONEXISTENT_ROOT,
        mapping_scopes=(_scope(),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewRequest(**values)


def _authorized_at() -> datetime:
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _authorization_request(**preview_overrides) -> LocalSourceConnectAuthorizationRequest:
    preview = preview_local_source_connect(_preview_request(**preview_overrides))
    return LocalSourceConnectAuthorizationRequest(
        preview=preview,
        authorized=True,
        authorized_at=_authorized_at(),
    )


def _provider_identity(**overrides) -> CapabilityArtifactIdentityV1Alpha1:
    values = dict(
        capability="source_snapshot",
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="spy-provider",
        implementation_version="1.0.0",
        artifact_digest=f"sha256:{canonical_hash({'provider': 'spy'})}",
    )
    values.update(overrides)
    return CapabilityArtifactIdentityV1Alpha1(**values)


class SpyProvider:
    """Returns a preconfigured acquired-file tuple, recording nothing further."""

    def __init__(self, files: tuple[AcquiredLocalFile, ...] = ()) -> None:
        self.artifact_identity = _provider_identity()
        self.files = files

    async def snapshot(self, request):
        return self.files


def _acquired_markdown_file(relative_path: str = "notes/a.md", **overrides) -> AcquiredLocalFile:
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(_CANONICAL_PAYLOAD),
        status="acquired",
        structured_payload_json=_CANONICAL_PAYLOAD,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


async def _build_result(request, files):
    return await authorize_local_source_connect(request, SpyProvider(files=files))


class JsonRoundTripImmutableRecordStore(InMemoryImmutableRecordStore):
    """Reserializes appended payloads to their real stored JSON shape.

    This proves persistence and replay survive an actual JSON round trip
    (tuples arriving back as arrays, datetimes as strings) rather than the
    plain in-memory store's Python-object passthrough.
    """

    async def append(self, request):
        receipt = await super().append(request)
        self.records = {
            storage_id: ImmutableRecordV1.model_validate_json(record.model_dump_json())
            for storage_id, record in self.records.items()
        }
        return receipt


class FailingStore(InMemoryImmutableRecordStore):
    """Raises persistence errors on demand, to prove exceptions become unavailable."""

    def __init__(self, *, fail_load_record: bool = False, fail_load_receipt: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fail_load_record = fail_load_record
        self.fail_load_receipt = fail_load_receipt

    async def load_record(self, storage_id, *, product_id, record_space, record_kind):
        if self.fail_load_record:
            raise ImmutableRecordPersistenceError("simulated load_record failure")
        return await super().load_record(
            storage_id, product_id=product_id, record_space=record_space, record_kind=record_kind
        )

    async def load_transaction_receipt(self, *, product_id, record_space, transaction_key):
        if self.fail_load_receipt:
            raise ImmutableRecordPersistenceError("simulated load_transaction_receipt failure")
        return await super().load_transaction_receipt(
            product_id=product_id, record_space=record_space, transaction_key=transaction_key
        )


# --- persist / replay ---


async def test_persist_writes_ordered_records_and_reopens_exact_result() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(), _acquired_markdown_file("notes/b.md")))
    store = JsonRoundTripImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)

    reopened = await repository.persist(request, result, _authorized_at())

    assert reopened == result

    receipt = await store.load_transaction_receipt(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        transaction_key=str(request.authorization_id),
    )
    assert receipt is not None
    kinds = [reference.record_kind for reference in receipt.records]
    assert kinds == ["preview", "authorization", "capture", "capture", "result"]

    for index, capture in enumerate(result.captures):
        loaded = await repository.load_capture(
            request.preview.product_id, capture.selection.reference(), actor_ref=request.preview.actor_ref
        )
        assert loaded == capture


async def test_exact_replay_from_new_repository_over_same_store_returns_without_writes() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = JsonRoundTripImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    first = await repository.persist(request, result, _authorized_at())

    fresh_repository = LocalSourceConnectRecordRepository(store)
    record_count_before = len(store.records)
    replayed = await fresh_repository.persist(request, result, _authorized_at())

    assert replayed == first
    assert len(store.records) == record_count_before


async def test_two_different_explicit_authorizations_of_same_preview_both_persist() -> None:
    preview = preview_local_source_connect(_preview_request())
    request_a = LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=_authorized_at())
    request_b = LocalSourceConnectAuthorizationRequest(
        preview=preview, authorized=True, authorized_at=_authorized_at() + timedelta(seconds=1)
    )
    assert request_a.authorization_id != request_b.authorization_id

    result_a = await _build_result(request_a, (_acquired_markdown_file(),))
    result_b = await _build_result(request_b, (_acquired_markdown_file(),))

    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    reopened_a = await repository.persist(request_a, result_a, _authorized_at())
    reopened_b = await repository.persist(request_b, result_b, _authorized_at() + timedelta(seconds=1))

    assert reopened_a == result_a
    assert reopened_b == result_b
    assert reopened_a != reopened_b


async def test_available_at_naive_is_rejected() -> None:
    request = _authorization_request()
    result = await _build_result(request, ())
    repository = LocalSourceConnectRecordRepository(InMemoryImmutableRecordStore())
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.persist(request, result, datetime(2026, 8, 20, 12, 0, 0))


async def test_available_at_before_authorized_at_is_rejected() -> None:
    request = _authorization_request()
    result = await _build_result(request, ())
    repository = LocalSourceConnectRecordRepository(InMemoryImmutableRecordStore())
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.persist(request, result, _authorized_at() - timedelta(seconds=1))


async def test_result_crossed_request_refs_is_rejected() -> None:
    request = _authorization_request()
    other_request = _authorization_request(source_group_id="source-group-b")
    result = await _build_result(other_request, ())
    repository = LocalSourceConnectRecordRepository(InMemoryImmutableRecordStore())
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.persist(request, result, _authorized_at())


async def test_same_authorization_with_changed_result_conflicts() -> None:
    request = _authorization_request()
    result_first = await _build_result(request, (_acquired_markdown_file(),))
    result_second = await _build_result(request, ())
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result_first, _authorized_at())

    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.persist(request, result_second, _authorized_at())


# --- load_capture failure modes ---


async def test_load_capture_missing_reference_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    other_selection = result.captures[0].selection.reference()
    tampered = other_selection.model_copy(update={"selection_id": "recorded_source_selection:" + "0" * 32})
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.load_capture(request.preview.product_id, tampered, actor_ref=request.preview.actor_ref)


async def test_load_capture_crossed_product_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    selection_ref = result.captures[0].selection.reference()
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.load_capture("product:some-other-product", selection_ref, actor_ref=request.preview.actor_ref)


async def test_load_capture_crossed_actor_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = JsonRoundTripImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    selection_ref = result.captures[0].selection.reference()
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.load_capture(request.preview.product_id, selection_ref, actor_ref="actor:someone-else")


async def test_load_capture_missing_preview_record_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    preview_storage_id = immutable_record_storage_id(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        record_kind="preview",
        record_key=str(request.authorization_id),
    )
    del store.records[preview_storage_id]

    selection_ref = result.captures[0].selection.reference()
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.load_capture(request.preview.product_id, selection_ref, actor_ref=request.preview.actor_ref)


async def test_load_capture_tampered_preview_record_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    preview_storage_id = immutable_record_storage_id(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        record_kind="preview",
        record_key=str(request.authorization_id),
    )
    original = store.records[preview_storage_id]
    tampered_payload = dict(original.payload)
    tampered_payload["actor_ref"] = "actor:tampered"
    store.records[preview_storage_id] = ImmutableRecordV1(
        product_id=original.product_id,
        record_space=original.record_space,
        record_kind=original.record_kind,
        record_key=original.record_key,
        payload_contract=original.payload_contract,
        payload=tampered_payload,
        as_of=original.as_of,
        available_at=original.available_at,
        processing_order=original.processing_order,
    )

    selection_ref = result.captures[0].selection.reference()
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.load_capture(request.preview.product_id, selection_ref, actor_ref=request.preview.actor_ref)


async def test_load_capture_store_exception_is_unavailable() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    failing_store = FailingStore(fail_load_record=True)
    failing_store.records = store.records
    failing_repository = LocalSourceConnectRecordRepository(failing_store)
    selection_ref = result.captures[0].selection.reference()
    with pytest.raises(LocalSourceConnectRecordUnavailable):
        await failing_repository.load_capture(
            request.preview.product_id, selection_ref, actor_ref=request.preview.actor_ref
        )


# --- tampered/crossed stored material during replay ---


async def test_tampered_capture_record_is_conflict_on_replay() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    capture = result.captures[0]
    storage_id = immutable_record_storage_id(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        record_kind=LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
        record_key=str(capture.selection.selection_id),
    )
    original = store.records[storage_id]
    tampered_payload = dict(original.payload)
    tampered_payload["relative_path"] = "notes/tampered.md"
    tampered_payload["capture_id"] = None
    tampered_payload["capture_digest"] = None
    tampered_record = ImmutableRecordV1(
        product_id=original.product_id,
        record_space=original.record_space,
        record_kind=original.record_kind,
        record_key=original.record_key,
        payload_contract=original.payload_contract,
        payload=tampered_payload,
        as_of=original.as_of,
        available_at=original.available_at,
        processing_order=original.processing_order,
    )
    store.records[storage_id] = tampered_record

    fresh_repository = LocalSourceConnectRecordRepository(store)
    with pytest.raises(LocalSourceConnectRecordConflict):
        await fresh_repository.replay(request)


async def test_missing_result_record_is_conflict_on_replay() -> None:
    request = _authorization_request()
    result = await _build_result(request, ())
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    result_storage_id = immutable_record_storage_id(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        record_kind="result",
        record_key=str(request.authorization_id),
    )
    del store.records[result_storage_id]

    fresh_repository = LocalSourceConnectRecordRepository(store)
    with pytest.raises(LocalSourceConnectRecordConflict):
        await fresh_repository.replay(request)


async def test_crossed_capture_selection_under_a_different_stored_key_is_conflict() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(), _acquired_markdown_file("notes/b.md")))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    first_capture, second_capture = result.captures[0], result.captures[1]
    first_storage_id = immutable_record_storage_id(
        product_id=request.preview.product_id,
        record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
        record_kind=LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
        record_key=str(first_capture.selection.selection_id),
    )
    original = store.records[first_storage_id]
    crossed_record = ImmutableRecordV1(
        product_id=original.product_id,
        record_space=original.record_space,
        record_kind=original.record_kind,
        record_key=original.record_key,
        payload_contract=original.payload_contract,
        payload=second_capture.model_dump(mode="python"),
        as_of=original.as_of,
        available_at=original.available_at,
        processing_order=original.processing_order,
    )
    store.records[first_storage_id] = crossed_record

    fresh_repository = LocalSourceConnectRecordRepository(store)
    with pytest.raises(LocalSourceConnectRecordConflict):
        await fresh_repository.replay(request)


async def test_result_referencing_a_different_preview_is_rejected_at_persist() -> None:
    request = _authorization_request()
    mismatched_result = await _build_result(_authorization_request(source_group_id="source-group-c"), ())
    repository = LocalSourceConnectRecordRepository(InMemoryImmutableRecordStore())
    with pytest.raises(LocalSourceConnectRecordConflict):
        await repository.persist(request, mismatched_result, _authorized_at())


async def test_store_exceptions_during_persist_are_unavailable() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    failing_store = FailingStore(fail_load_receipt=True)
    repository = LocalSourceConnectRecordRepository(failing_store)
    with pytest.raises(LocalSourceConnectRecordUnavailable):
        await repository.persist(request, result, _authorized_at())


async def test_store_exceptions_during_replay_load_record_are_unavailable() -> None:
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file(),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _authorized_at())

    failing_store = FailingStore(fail_load_record=True)
    failing_store.records = store.records
    failing_store.receipts = store.receipts
    failing_repository = LocalSourceConnectRecordRepository(failing_store)
    with pytest.raises(LocalSourceConnectRecordUnavailable):
        await failing_repository.replay(request)


# --- multi-file capture ordering ---


# --- authorize_local_source_connect_host ---


def _clock(*values: datetime):
    iterator = iter(values)

    def _next() -> datetime:
        return next(iterator)

    return _next


class CountingResolver:
    """Counts resolve() calls and returns/raises what it is configured with."""

    def __init__(self, provider=None, *, raise_error: Exception | None = None) -> None:
        self.provider = provider
        self.raise_error = raise_error
        self.calls = 0

    def resolve(self):
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        return self.provider


class CountingProvider(SpyProvider):
    """Counts snapshot() calls and can be configured to raise instead of return."""

    def __init__(self, files: tuple[AcquiredLocalFile, ...] = (), *, raise_error: Exception | None = None) -> None:
        super().__init__(files=files)
        self.calls = 0
        self.raise_error = raise_error

    async def snapshot(self, request):
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        return await super().snapshot(request)


def _host_user(**overrides) -> dict:
    values = {"sub": "actor:reviewer-1", "product": "product:pi13-ws2-host"}
    values.update(overrides)
    return values


def _runtime(
    store: InMemoryImmutableRecordStore | None = None,
    *,
    resolver: CountingResolver | None = None,
    clock,
) -> LocalSourceConnectHostRuntime:
    return LocalSourceConnectHostRuntime(
        repository=LocalSourceConnectRecordRepository(store if store is not None else InMemoryImmutableRecordStore()),
        provider_resolver=resolver if resolver is not None else CountingResolver(),
        clock=clock,
    )


async def test_missing_user_claims_is_unauthenticated_and_calls_nothing() -> None:
    request = _authorization_request()
    resolver = CountingResolver(CountingProvider())
    store = InMemoryImmutableRecordStore()
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at()))

    with pytest.raises(LocalSourceConnectHostUnauthenticated):
        await authorize_local_source_connect_host(request, {"sub": "actor:reviewer-1"}, runtime)

    assert resolver.calls == 0
    assert store.records == {}


async def test_crossed_actor_or_product_is_denied_and_calls_nothing() -> None:
    request = _authorization_request()
    resolver = CountingResolver(CountingProvider())
    store = InMemoryImmutableRecordStore()
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at()))

    with pytest.raises(LocalSourceConnectHostDenied):
        await authorize_local_source_connect_host(request, _host_user(sub="actor:someone-else"), runtime)
    with pytest.raises(LocalSourceConnectHostDenied):
        await authorize_local_source_connect_host(request, _host_user(product="product:some-other"), runtime)

    assert resolver.calls == 0
    assert store.records == {}


async def test_new_read_stale_more_than_five_minutes_is_conflict_and_calls_nothing() -> None:
    request = _authorization_request()
    resolver = CountingResolver(CountingProvider(files=(_acquired_markdown_file(),)))
    store = InMemoryImmutableRecordStore()
    stale_now = _authorized_at() + timedelta(minutes=5, seconds=1)
    runtime = _runtime(store, resolver=resolver, clock=_clock(stale_now))

    with pytest.raises(LocalSourceConnectHostConflict):
        await authorize_local_source_connect_host(request, _host_user(), runtime)

    assert resolver.calls == 0
    assert resolver.provider.calls == 0
    assert store.records == {}


async def test_new_read_future_more_than_five_minutes_is_conflict_and_calls_nothing() -> None:
    request = _authorization_request()
    resolver = CountingResolver(CountingProvider(files=(_acquired_markdown_file(),)))
    store = InMemoryImmutableRecordStore()
    future_now = _authorized_at() - timedelta(minutes=5, seconds=1)
    runtime = _runtime(store, resolver=resolver, clock=_clock(future_now))

    with pytest.raises(LocalSourceConnectHostConflict):
        await authorize_local_source_connect_host(request, _host_user(), runtime)

    assert resolver.calls == 0
    assert resolver.provider.calls == 0
    assert store.records == {}


async def test_naive_clock_is_unavailable() -> None:
    request = _authorization_request()
    resolver = CountingResolver(CountingProvider(files=(_acquired_markdown_file(),)))
    store = InMemoryImmutableRecordStore()
    runtime = _runtime(store, resolver=resolver, clock=_clock(datetime(2026, 8, 20, 12, 0, 0)))

    with pytest.raises(LocalSourceConnectHostUnavailable):
        await authorize_local_source_connect_host(request, _host_user(), runtime)


async def test_success_resolves_once_and_persists_reopens_exact_result() -> None:
    request = _authorization_request()
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = JsonRoundTripImmutableRecordStore()
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at(), _authorized_at()))

    result = await authorize_local_source_connect_host(request, _host_user(), runtime)

    assert resolver.calls == 1
    assert provider.calls == 1
    assert len(result.captures) == 1

    repository = LocalSourceConnectRecordRepository(store)
    reopened = await repository.replay(request)
    assert reopened == result
    loaded = await repository.load_capture(
        request.preview.product_id, result.captures[0].selection.reference(), actor_ref=request.preview.actor_ref
    )
    assert loaded == result.captures[0]


async def test_exact_stored_replay_wins_over_a_deliberately_failing_new_read() -> None:
    request = _authorization_request()
    store = InMemoryImmutableRecordStore()
    seeding_resolver = CountingResolver(CountingProvider(files=(_acquired_markdown_file(),)))
    seeding_runtime = _runtime(store, resolver=seeding_resolver, clock=_clock(_authorized_at(), _authorized_at()))
    stored = await authorize_local_source_connect_host(request, _host_user(), seeding_runtime)

    failing_resolver = CountingResolver(raise_error=AssertionError("must not resolve on exact replay"))
    old_now = _authorized_at() + timedelta(days=365)
    fresh_runtime = _runtime(store, resolver=failing_resolver, clock=_clock(old_now))

    replayed = await authorize_local_source_connect_host(request, _host_user(), fresh_runtime)

    assert replayed == stored
    assert failing_resolver.calls == 0


async def test_no_provider_available_is_unavailable() -> None:
    request = _authorization_request()
    resolver = CountingResolver(None)
    runtime = _runtime(resolver=resolver, clock=_clock(_authorized_at()))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await authorize_local_source_connect_host(request, _host_user(), runtime)


async def test_provider_registry_failure_is_unavailable() -> None:
    request = _authorization_request()
    resolver = CountingResolver(raise_error=SourceSnapshotProviderRegistryError("registry unavailable"))
    runtime = _runtime(resolver=resolver, clock=_clock(_authorized_at()))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await authorize_local_source_connect_host(request, _host_user(), runtime)


async def test_provider_snapshot_exception_is_unavailable() -> None:
    request = _authorization_request()
    provider = CountingProvider(raise_error=RuntimeError("snapshot exploded"))
    resolver = CountingResolver(provider)
    runtime = _runtime(resolver=resolver, clock=_clock(_authorized_at()))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await authorize_local_source_connect_host(request, _host_user(), runtime)
    assert provider.calls == 1


async def test_unsafe_provider_result_is_conflict() -> None:
    request = _authorization_request()
    unsafe_file = _acquired_markdown_file(relative_path="../escape.md")
    provider = CountingProvider(files=(unsafe_file,))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at()))

    with pytest.raises(LocalSourceConnectHostConflict):
        await authorize_local_source_connect_host(request, _host_user(), runtime)

    assert store.records == {}


async def test_append_failure_maps_to_unavailable() -> None:
    request = _authorization_request()
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore(fail_after_records=1)
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at(), _authorized_at()))

    with pytest.raises(LocalSourceConnectHostUnavailable):
        await authorize_local_source_connect_host(request, _host_user(), runtime)


async def test_post_capture_clock_before_authorized_at_is_conflict_and_no_append() -> None:
    request = _authorization_request()
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()
    stale_available_at = _authorized_at() - timedelta(seconds=1)
    runtime = _runtime(store, resolver=resolver, clock=_clock(_authorized_at(), stale_available_at))

    with pytest.raises(LocalSourceConnectHostConflict):
        await authorize_local_source_connect_host(request, _host_user(), runtime)

    assert store.records == {}


async def test_multi_file_capture_order_reopens_exactly() -> None:
    request = _authorization_request()
    files = (
        _acquired_markdown_file("notes/c.md"),
        _acquired_markdown_file("notes/a.md"),
        _acquired_markdown_file("notes/b.md"),
    )
    result = await _build_result(request, files)
    assert [capture.relative_path for capture in result.captures] == ["notes/a.md", "notes/b.md", "notes/c.md"]

    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    reopened = await repository.persist(request, result, _authorized_at())

    assert [capture.relative_path for capture in reopened.captures] == ["notes/a.md", "notes/b.md", "notes/c.md"]
    for capture in reopened.captures:
        loaded = await repository.load_capture(
            request.preview.product_id, capture.selection.reference(), actor_ref=request.preview.actor_ref
        )
        assert loaded == capture


# --- preview_local_source_connect_host ---

PREVIEW_PROFILE_ID = "intelligence_onboarding_profile:notes"
PREVIEW_GROUP_ID = "notes_group"
PREVIEW_MAPPING_ID = "mapping-a"


def _preview_profile(**group_overrides) -> IntelligenceOnboardingProfileV1Alpha1:
    group = dict(
        source_group_id=PREVIEW_GROUP_ID,
        label="Notes",
        description="Installed notes source group description.",
        evidence_role="primary_evidence",
        source_ids=["notes"],
        source_labels=["Notes"],
        access_label="Local files",
        default_selected=True,
    )
    group.update(group_overrides)
    return IntelligenceOnboardingProfileV1Alpha1.model_validate_json(
        json.dumps(
            {
                "contract": "ace.intelligence.onboarding-profile/v1alpha1",
                "profile_id": PREVIEW_PROFILE_ID,
                "topic_id": "notes",
                "display_name": "Notes",
                "prompt": "What do you need to stay ahead of?",
                "description": "Installed profile description.",
                "outcomes": [
                    {
                        "outcome_id": "decision_readiness",
                        "label": "Stay decision-ready",
                        "description": "Orient around material change and evidence.",
                        "icon_hint": "strategy",
                        "recommended_watch_ids": [],
                        "recommended_intelligence_ids": [],
                        "recommended_topic_labels": [],
                        "recommended_intelligence_labels": [],
                    }
                ],
                "source_groups": [group],
                "cadences": [{"cadence_id": "daily", "label": "Daily", "description": "A daily orientation."}],
                "default_cadence_id": "daily",
                "first_value": {
                    "public_sources_first": True,
                    "private_sources_optional": True,
                    "completion_label": "Open Brief",
                },
                "guardrails": {
                    "declarative_only": True,
                    "authorizes_connections": False,
                    "authorizes_monitors": False,
                    "proposed_sources_are_not_connected": True,
                    "feedback_may_reweight_relevance_not_authority": True,
                },
            }
        )
    )


PREVIEW_PROFILE = _preview_profile()
PREVIEW_INSTALLED_PROFILE = InstalledOnboardingProfile(
    distribution="ace-domain-fixture",
    distribution_version="1.0.0",
    resource_path="notes/onboarding_profile.json",
    profile=PREVIEW_PROFILE,
)


def _preview_pack_reference() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws2-preview-host"})
    return CompiledPackRefV1(
        pack_id="pack-preview",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


PREVIEW_PACK_REFERENCE = _preview_pack_reference()
PREVIEW_PLANNER_ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="intelligence_build_planning",
    contract=INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT,
    implementation_id="fixture_planner",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "b" * 64,
)


def _installed_mapping(mapping_id: str = PREVIEW_MAPPING_ID) -> SourceMappingRuleV1:
    return SourceMappingRuleV1(
        mapping_id=mapping_id,
        source_definition_ref="source-def-a",
        source_type_ref="source_type:local_files",
        capability_requirement_id="local_files_snapshot",
        authority_request_id="read_local_files",
        allowed_uri_schemes=("file",),
        subject_binding_id="subject-a",
        entity_type_id="entity-a",
        attribute_mappings=(AttributeMappingV1(attribute_id="body", source_pointer="/body"),),
        static_confidence=1.0,
    )


def _mapping_module_compiled(
    *, module_id: str = PREVIEW_GROUP_ID, mappings: tuple[SourceMappingRuleV1, ...] | None = None
) -> CompiledModuleV1:
    module = SourceMappingModuleV1(
        module_id=module_id,
        mappings=mappings if mappings is not None else (_installed_mapping(),),
    )
    payload = canonical_json(module)
    return CompiledModuleV1(
        module_id=module_id,
        contract=SOURCE_MAPPING_MODULE_VERSION,
        canonical_payload=payload,
        module_digest=f"sha256:{canonical_hash(json.loads(payload))}",
    )


def _installed_pack(*, modules: tuple[CompiledModuleV1, ...] | None = None) -> SimpleNamespace:
    reference = PREVIEW_PACK_REFERENCE
    return SimpleNamespace(
        compiled_pack_id=reference.compiled_pack_id,
        pack_digest=reference.pack_digest,
        modules=modules if modules is not None else (_mapping_module_compiled(),),
    )


class _PreviewPackResolver:
    def __init__(self, *, pack: SimpleNamespace | None = None, reference: CompiledPackRefV1 | None = None) -> None:
        self.pack = pack if pack is not None else _installed_pack()
        self.reference = reference if reference is not None else PREVIEW_PACK_REFERENCE
        self.calls: list[CompiledPackRefV1] = []

    async def resolve_exact(self, *, reference):
        self.calls.append(reference)
        if reference != self.reference:
            return None
        return SimpleNamespace(pack=self.pack)


class _PreviewPlanner:
    profile_id = PREVIEW_PROFILE_ID
    pack_reference = PREVIEW_PACK_REFERENCE
    artifact_identity = PREVIEW_PLANNER_ARTIFACT


class _InvalidPreviewPlanner:
    """Lacks the attributes required for exact v1alpha3 planner revalidation."""


class _PreviewPlannerResolver:
    def __init__(self, planner=None, *, raise_error: Exception | None = None) -> None:
        self.planner = planner
        self.raise_error = raise_error
        self.calls: list[str] = []

    def resolve(self, profile_id: str):
        self.calls.append(profile_id)
        if self.raise_error is not None:
            raise self.raise_error
        return self.planner


def _preview_runtime(
    *,
    profiles: tuple[InstalledOnboardingProfile, ...] = (PREVIEW_INSTALLED_PROFILE,),
    packs: _PreviewPackResolver | None = None,
    planners: _PreviewPlannerResolver | None = None,
) -> LocalSourceConnectPreviewRuntime:
    return LocalSourceConnectPreviewRuntime(
        profiles=profiles,
        packs=packs if packs is not None else _PreviewPackResolver(),
        planners=planners if planners is not None else _PreviewPlannerResolver(_PreviewPlanner()),
    )


def _preview_host_request(**overrides) -> LocalSourceConnectPreviewHostRequest:
    values = dict(
        profile_id=PREVIEW_PROFILE_ID,
        profile_digest=PREVIEW_PROFILE.profile_digest,
        source_group_id=PREVIEW_GROUP_ID,
        authorized_root=NONEXISTENT_ROOT,
        mapping_scopes=(LocalSourceConnectMappingScopeRequest(mapping_id=PREVIEW_MAPPING_ID, include=("notes/*.md",)),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewHostRequest(**values)


def _preview_host_user(**overrides) -> dict:
    values = {"sub": "actor:reviewer-1", "product": "product:pi13-ws2-host"}
    values.update(overrides)
    return values


def _raise_if_touched(*args, **kwargs):
    raise AssertionError("preview_local_source_connect_host must not touch the filesystem")


@contextmanager
def _forbidden_filesystem():
    with (
        unittest.mock.patch("os.path.exists", _raise_if_touched),
        unittest.mock.patch("os.stat", _raise_if_touched),
        unittest.mock.patch("os.scandir", _raise_if_touched),
        unittest.mock.patch("builtins.open", _raise_if_touched),
    ):
        yield


async def test_preview_success_derives_product_actor_and_installed_semantics() -> None:
    packs = _PreviewPackResolver()
    planners = _PreviewPlannerResolver(_PreviewPlanner())
    runtime = _preview_runtime(packs=packs, planners=planners)
    request = _preview_host_request()

    with _forbidden_filesystem():
        preview = await preview_local_source_connect_host(request, _preview_host_user(), runtime)

    assert preview.product_id == "product:pi13-ws2-host"
    assert preview.actor_ref == "actor:reviewer-1"
    assert preview.profile_id == PREVIEW_PROFILE_ID
    assert preview.profile_digest == PREVIEW_PROFILE.profile_digest
    assert preview.source_group_id == PREVIEW_GROUP_ID
    assert preview.expected_contribution == PREVIEW_PROFILE.source_groups[0].description
    assert preview.pack == PREVIEW_PACK_REFERENCE
    assert preview.authorized_root == NONEXISTENT_ROOT
    assert len(preview.mapping_scopes) == 1
    scope = preview.mapping_scopes[0]
    installed = _installed_mapping()
    assert scope.mapping_id == installed.mapping_id
    assert scope.source_definition_ref == installed.source_definition_ref
    assert scope.source_type_ref == installed.source_type_ref
    assert scope.subject_binding_id == installed.subject_binding_id
    assert scope.entity_type_id == installed.entity_type_id
    assert scope.include == ("notes/*.md",)
    assert preview.exclude == ()
    assert planners.calls == [PREVIEW_PROFILE_ID]
    assert packs.calls == [PREVIEW_PACK_REFERENCE]


async def test_preview_request_missing_claims_is_unauthenticated() -> None:
    runtime = _preview_runtime()
    with pytest.raises(LocalSourceConnectHostUnauthenticated):
        await preview_local_source_connect_host(_preview_host_request(), {"sub": "actor:reviewer-1"}, runtime)


async def test_preview_wrong_profile_digest_is_conflict() -> None:
    runtime = _preview_runtime()
    request = _preview_host_request(profile_digest="sha256:" + "0" * 64)
    with pytest.raises(LocalSourceConnectHostConflict):
        await preview_local_source_connect_host(request, _preview_host_user(), runtime)


async def test_preview_missing_profile_is_not_found() -> None:
    runtime = _preview_runtime(profiles=())
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_duplicate_profile_is_unavailable() -> None:
    runtime = _preview_runtime(profiles=(PREVIEW_INSTALLED_PROFILE, PREVIEW_INSTALLED_PROFILE))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_missing_source_group_is_not_found() -> None:
    runtime = _preview_runtime()
    request = _preview_host_request(source_group_id="unknown_group")
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(request, _preview_host_user(), runtime)


async def test_preview_duplicate_source_group_is_unavailable() -> None:
    duplicated_profile = _preview_profile()
    duplicated = duplicated_profile.model_copy(
        update={"source_groups": duplicated_profile.source_groups + duplicated_profile.source_groups}
    )
    installed = InstalledOnboardingProfile(
        distribution="ace-domain-fixture",
        distribution_version="1.0.0",
        resource_path="notes/onboarding_profile.json",
        profile=duplicated,
    )
    runtime = _preview_runtime(profiles=(installed,))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_duplicate_mapping_scope_request_is_conflict() -> None:
    runtime = _preview_runtime()
    request = _preview_host_request(
        mapping_scopes=(
            LocalSourceConnectMappingScopeRequest(mapping_id=PREVIEW_MAPPING_ID, include=("notes/a.md",)),
            LocalSourceConnectMappingScopeRequest(mapping_id=PREVIEW_MAPPING_ID, include=("notes/b.md",)),
        )
    )
    with pytest.raises(LocalSourceConnectHostConflict):
        await preview_local_source_connect_host(request, _preview_host_user(), runtime)


async def test_preview_planner_registry_failure_is_unavailable() -> None:
    planners = _PreviewPlannerResolver(raise_error=IntelligenceBuildPlannerRegistryError("registry unavailable"))
    runtime = _preview_runtime(planners=planners)
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_missing_planner_is_not_found() -> None:
    runtime = _preview_runtime(planners=_PreviewPlannerResolver(None))
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_invalid_installed_planner_is_unavailable() -> None:
    runtime = _preview_runtime(planners=_PreviewPlannerResolver(_InvalidPreviewPlanner()))
    with pytest.raises(LocalSourceConnectHostUnavailable):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_missing_pack_is_not_found() -> None:
    packs = _PreviewPackResolver(
        reference=CompiledPackRefV1(
            pack_id="other-pack",
            pack_version="1.0.0",
            compiled_pack_id="pack_ir:" + "0" * 32,
            pack_digest="sha256:" + "0" * 64,
        )
    )
    runtime = _preview_runtime(packs=packs)
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_mismatched_resolved_pack_is_conflict() -> None:
    mismatched_pack = SimpleNamespace(
        compiled_pack_id="pack_ir:" + "9" * 32,
        pack_digest=PREVIEW_PACK_REFERENCE.pack_digest,
        modules=(_mapping_module_compiled(),),
    )
    packs = _PreviewPackResolver(pack=mismatched_pack)
    runtime = _preview_runtime(packs=packs)
    with pytest.raises(LocalSourceConnectHostConflict):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_missing_mapping_module_is_not_found() -> None:
    other_module = _mapping_module_compiled(module_id="other_group")
    packs = _PreviewPackResolver(pack=_installed_pack(modules=(other_module,)))
    runtime = _preview_runtime(packs=packs)
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_missing_mapping_is_not_found() -> None:
    packs = _PreviewPackResolver(
        pack=_installed_pack(modules=(_mapping_module_compiled(mappings=(_installed_mapping("other-mapping"),)),))
    )
    runtime = _preview_runtime(packs=packs)
    with pytest.raises(LocalSourceConnectHostNotFound):
        await preview_local_source_connect_host(_preview_host_request(), _preview_host_user(), runtime)


async def test_preview_client_invalid_lexical_scope_is_conflict() -> None:
    runtime = _preview_runtime()
    request = _preview_host_request(
        mapping_scopes=(LocalSourceConnectMappingScopeRequest(mapping_id=PREVIEW_MAPPING_ID, include=("/absolute",)),)
    )
    with pytest.raises(LocalSourceConnectHostConflict):
        await preview_local_source_connect_host(request, _preview_host_user(), runtime)


def test_preview_runtime_has_no_source_snapshot_provider_involvement() -> None:
    assert not hasattr(LocalSourceConnectPreviewRuntime, "provider_resolver")
    fields = {field.name for field in LocalSourceConnectPreviewRuntime.__dataclass_fields__.values()}
    assert "provider_resolver" not in fields
