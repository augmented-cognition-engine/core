from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from ace.core.records import AppendOnlyTransactionReceiptV1, ImmutableRecordReplayConflict, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    ChangeImpactV1Alpha1,
    ConfidenceBand,
    RepositoryIndexIdentityV1Alpha1,
    stable_digest,
)
from core.engine.code_intelligence.resource_plane import (
    CODE_LENS_ADMISSION_AUTHORITY,
    CODE_LENS_ADMISSION_OPERATION,
    CODE_LENS_RECORD_KIND,
    CODE_LENS_RECORD_SPACE,
    AtriumCodeLensAdmissionError,
    AtriumCodeLensAdmissionHttpConflict,
    AtriumCodeLensAdmissionHttpRuntime,
    AtriumCodeLensAdmissionService,
    AtriumCodeLensResourceProjectionReader,
    AtriumCodeLensRevisionV1Alpha1,
    admit_atrium_code_lens_revision,
)
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
    Phase1IndexStateV1Alpha1,
)
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
PRODUCT = "product:code-resource-plane"
ACTOR = "principal:code-indexer"
GRANT = "authority_grant:code-lens-admission"
REPOSITORY = "repository:ace-core"


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:code-resource-plane",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
    )


def _head() -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id=GRANT,
        sequence=1,
        revision_id="authority_revision:code-resource-plane",
        commit_receipt_id="authority_receipt:code-resource-plane",
        updated_at=NOW - timedelta(days=1),
    )


class _Authority:
    def __init__(self, *, operation: str = CODE_LENS_ADMISSION_OPERATION) -> None:
        self.operation = operation
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=self.operation,
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="b" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(_head()),
        )


def _index(*, revision: str = "1" * 40) -> RepositoryIndexIdentityV1Alpha1:
    return RepositoryIndexIdentityV1Alpha1(
        repository="ace-core",
        revision=revision,
        dirty=False,
        working_tree_digest="clean",
        scanner_contract="ace.graph-builder/phase1",
        observed_languages=("python",),
        generated_at=NOW - timedelta(minutes=5),
    )


def _snapshot(
    index: RepositoryIndexIdentityV1Alpha1,
    *,
    generation: int = 1,
    parent: DurablePhase1IndexSnapshotV1Alpha1 | None = None,
    parent_snapshot_id: str | None = None,
    parent_snapshot_digest: str | None = None,
):
    state = Phase1IndexStateV1Alpha1(files=(), symbols=(), imports=())
    if parent is not None:
        parent_snapshot_id = parent.snapshot_id
        parent_snapshot_digest = parent.snapshot_digest
    return DurablePhase1IndexSnapshotV1Alpha1(
        repository_path="/tmp/ace-core",
        index=index,
        index_id=index.index_id,
        generation=generation,
        parent_snapshot_id=parent_snapshot_id,
        parent_snapshot_digest=parent_snapshot_digest,
        phase1_state=state,
        phase1_state_digest=stable_digest(state),
        created_at=NOW - timedelta(minutes=4),
    )


def _lens(index: RepositoryIndexIdentityV1Alpha1, *, target: str = "core/engine/api/main.py"):
    return AtriumCodeLensV1Alpha1(
        index=index,
        query="What depends on this API module?",
        target_path=target,
        nodes=(),
        edges=(),
        impact=ChangeImpactV1Alpha1(
            target_path=target,
            direct_dependents=("tests/test_main.py",),
            transitive_dependents=(),
            affected_tests=("tests/test_main.py",),
            known_coverage_gaps=("runtime registration",),
            confidence=ConfidenceBand.SUPPORTED,
            basis="Static import graph only.",
        ),
        disconnected_symbols=(),
        evidence=(),
        omissions=("source bodies intentionally excluded",),
        degraded_reasons=(),
    )


def _store() -> InMemoryImmutableRecordStore:
    store = InMemoryImmutableRecordStore()
    store.set_governed_state_head(_head())
    return store


@pytest.mark.asyncio
async def test_admission_is_append_only_body_free_and_exactly_authorized() -> None:
    store = _store()
    authority = _Authority()
    index = _index()
    result = await AtriumCodeLensAdmissionService(records=store, authority=authority).admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(index),
        lens=_lens(index),
        admitted_at=NOW,
    )

    assert result.replayed is False
    assert result.revision.revision == 1
    assert result.revision.index_snapshot_id.startswith("code_index_snapshot:")
    assert result.revision.index_id == index.index_id
    assert result.revision.lens_id == _lens(index).lens_id
    assert result.revision.local_snapshot_is_product_truth is False
    assert result.revision.source_authority is False
    assert result.revision.reasoning_authority is False
    assert result.revision.delivery_authority is False
    assert result.revision.effect_authority is False
    assert '"body":' not in json.dumps(result.revision.model_dump(mode="json"))
    assert authority.calls[0]["authority"] == CODE_LENS_ADMISSION_AUTHORITY
    assert authority.calls[0]["operation"] == CODE_LENS_ADMISSION_OPERATION
    assert len(store.records) == 1
    record = next(iter(store.records.values()))
    assert record.record_space == CODE_LENS_RECORD_SPACE
    assert record.record_kind == CODE_LENS_RECORD_KIND
    assert result.transaction.governed_state_preconditions == (
        GovernedStateHeadPreconditionV1Alpha1.from_head(_head()),
    )


@pytest.mark.asyncio
async def test_replay_is_idempotent_and_new_snapshot_appends_immediate_supersession() -> None:
    store = _store()
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    first_index = _index()
    first_snapshot = _snapshot(first_index)
    first = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=first_snapshot,
        lens=_lens(first_index),
        admitted_at=NOW,
    )
    replay = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=first_snapshot,
        lens=_lens(first_index),
        admitted_at=NOW,
    )
    assert replay.replayed is True
    assert replay.revision == first.revision
    assert len(store.records) == 1

    second_index = _index(revision="2" * 40)
    second = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(second_index, generation=2, parent=first_snapshot),
        lens=_lens(second_index),
        admitted_at=NOW + timedelta(minutes=1),
    )
    assert second.revision.revision == 2
    assert second.revision.supersedes_revision_id == first.revision.revision_id
    assert second.revision.supersedes_revision_digest == first.revision.revision_digest
    assert len(store.records) == 2


@pytest.mark.asyncio
async def test_successor_rejects_snapshot_generation_gap_and_forked_parent() -> None:
    store = _store()
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    first_index = _index()
    first_snapshot = _snapshot(first_index)
    await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=first_snapshot,
        lens=_lens(first_index),
        admitted_at=NOW,
    )
    next_index = _index(revision="2" * 40)

    with pytest.raises(AtriumCodeLensAdmissionError, match="generation is not contiguous"):
        await service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(next_index, generation=3, parent=first_snapshot),
            lens=_lens(next_index),
            admitted_at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(AtriumCodeLensAdmissionError, match="exact predecessor"):
        await service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(
                next_index,
                generation=2,
                parent_snapshot_id="code_index_snapshot:fork",
                parent_snapshot_digest="sha256:" + "f" * 64,
            ),
            lens=_lens(next_index),
            admitted_at=NOW + timedelta(minutes=1),
        )
    assert len(store.records) == 1


@pytest.mark.asyncio
async def test_successor_rejects_regressing_as_of_before_it_can_create_future_lineage() -> None:
    store = _store()
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    first_index = _index()
    first_snapshot = _snapshot(first_index)
    await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=first_snapshot,
        lens=_lens(first_index),
        admitted_at=NOW,
    )
    stale_index = _index(revision="2" * 40).model_copy(
        update={"generated_at": first_index.generated_at - timedelta(minutes=30)}
    )
    with pytest.raises(AtriumCodeLensAdmissionError, match="as_of cannot regress"):
        await service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(stale_index, generation=2, parent=first_snapshot),
            lens=_lens(stale_index),
            admitted_at=NOW + timedelta(minutes=1),
        )
    assert len(store.records) == 1


class _SwappedReceiptStore:
    def __init__(self, inner: InMemoryImmutableRecordStore) -> None:
        self.inner = inner
        self.swapped_receipt = None

    async def read_as_of(self, **kwargs):
        return await self.inner.read_as_of(**kwargs)

    async def append(self, request):
        return await self.inner.append(request)

    async def load_transaction_receipt(self, **kwargs):
        if self.swapped_receipt is not None:
            return self.swapped_receipt
        return await self.inner.load_transaction_receipt(**kwargs)


@pytest.mark.asyncio
async def test_replay_rejects_a_valid_receipt_from_another_lens_family() -> None:
    inner = _store()
    store = _SwappedReceiptStore(inner)
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    index = _index()
    snapshot = _snapshot(index)
    await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=snapshot,
        lens=_lens(index),
        admitted_at=NOW,
    )
    other = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=snapshot,
        lens=_lens(index, target="core/engine/api/other.py"),
        admitted_at=NOW,
    )
    store.swapped_receipt = other.transaction

    with pytest.raises(AtriumCodeLensAdmissionError, match="does not bind the exact revision"):
        await service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=snapshot,
            lens=_lens(index),
            admitted_at=NOW,
        )


@pytest.mark.asyncio
async def test_replay_rejects_unrelated_grant_precondition_and_arbitrary_request_hash() -> None:
    inner = _store()
    store = _SwappedReceiptStore(inner)
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    index = _index()
    snapshot = _snapshot(index)
    first = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=snapshot,
        lens=_lens(index),
        admitted_at=NOW,
    )
    material = first.transaction.model_dump(mode="python", exclude={"receipt_id", "receipt_hash"})
    material["request_hash"] = "sha256:" + "c" * 64
    material["governed_state_preconditions"] = (
        GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id="authority_grant:unrelated",
            sequence=7,
            revision_id="authority_revision:unrelated",
            commit_receipt_id="authority_receipt:unrelated",
        ),
    )
    store.swapped_receipt = AppendOnlyTransactionReceiptV1.model_validate(material)

    with pytest.raises(AtriumCodeLensAdmissionError, match="does not bind the exact revision"):
        await service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=snapshot,
            lens=_lens(index),
            admitted_at=NOW,
        )


@pytest.mark.asyncio
async def test_http_host_classifies_immutable_replay_race_as_conflict(monkeypatch) -> None:
    evaluated_at = datetime.now(UTC)
    store = _store()

    async def _lose_exact_race(*_args, **_kwargs):
        raise ImmutableRecordReplayConflict("concurrent exact revision won")

    monkeypatch.setattr(AtriumCodeLensAdmissionService, "admit", _lose_exact_race)
    with pytest.raises(AtriumCodeLensAdmissionHttpConflict, match="concurrent race"):
        await admit_atrium_code_lens_revision(
            user={
                "sub": ACTOR,
                "product": PRODUCT,
                "authorities": [CODE_LENS_ADMISSION_AUTHORITY],
                "exp": (evaluated_at + timedelta(hours=1)).timestamp(),
            },
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(_index()),
            lens=_lens(_index()),
            runtime=AtriumCodeLensAdmissionHttpRuntime(records=store, authority=_Authority()),
            evaluated_at=evaluated_at,
        )


class _ConcurrentReadStore(InMemoryImmutableRecordStore):
    def __init__(self) -> None:
        super().__init__()
        self._reads = 0
        self._both_read = asyncio.Event()

    async def read_as_of(self, **kwargs):
        result = await super().read_as_of(**kwargs)
        self._reads += 1
        if self._reads == 2:
            self._both_read.set()
        await self._both_read.wait()
        return result


@pytest.mark.asyncio
async def test_concurrent_different_first_revisions_conflict_without_forking() -> None:
    store = _ConcurrentReadStore()
    store.set_governed_state_head(_head())
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    first_index = _index()
    second_index = _index(revision="2" * 40)

    results = await asyncio.gather(
        service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(first_index),
            lens=_lens(first_index),
            admitted_at=NOW,
        ),
        service.admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(second_index),
            lens=_lens(second_index),
            admitted_at=NOW,
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ImmutableRecordReplayConflict) for result in results) == 1
    assert len(store.records) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tampered_field", "tampered_value"),
    (
        ("index_generation", 4),
        ("as_of", NOW - timedelta(minutes=30)),
    ),
)
async def test_projection_degrades_on_tampered_generation_or_regressing_as_of(
    tampered_field: str,
    tampered_value,
) -> None:
    store = _store()
    service = AtriumCodeLensAdmissionService(records=store, authority=_Authority())
    first_index = _index()
    first_snapshot = _snapshot(first_index)
    first = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=first_snapshot,
        lens=_lens(first_index),
        admitted_at=NOW,
    )
    second_index = _index(revision="2" * 40)
    second = await service.admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(second_index, generation=2, parent=first_snapshot),
        lens=_lens(second_index),
        admitted_at=NOW + timedelta(minutes=1),
    )
    payload = second.revision.model_dump(mode="python")
    payload.update({tampered_field: tampered_value, "revision_id": None, "revision_digest": None})
    tampered = AtriumCodeLensRevisionV1Alpha1.model_validate(payload)
    prior_record = next(record for record in store.records.values() if record.payload["revision"] == 2)
    replacement = ImmutableRecordV1(
        product_id=prior_record.product_id,
        record_space=prior_record.record_space,
        record_kind=prior_record.record_kind,
        record_key=prior_record.record_key,
        payload_contract=prior_record.payload_contract,
        payload=tampered.model_dump(mode="json"),
        as_of=tampered.as_of,
        available_at=tampered.admitted_at,
        processing_order=0,
    )
    store.records[str(prior_record.storage_id)] = replacement
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,),
        subject_refs=(first.revision.repository_ref,),
        as_of=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=1),
        page_size=10,
    )

    batch = await AtriumCodeLensResourceProjectionReader(store=store).read(query=query, after=None, limit=11)

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.records == ()
    assert batch.degraded_reason_refs == ("degraded_reason:invalid-atrium-code-lens-revision",)


class _WrongEnvelopeStore:
    def __init__(self, record: ImmutableRecordV1) -> None:
        self.record = record

    async def read_as_of(self, **kwargs):
        return (self.record,)


@pytest.mark.asyncio
async def test_projection_degrades_when_immutable_envelope_classifiers_are_tampered() -> None:
    store = _store()
    index = _index()
    admitted = await AtriumCodeLensAdmissionService(records=store, authority=_Authority()).admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(index),
        lens=_lens(index),
        admitted_at=NOW,
    )
    valid = next(iter(store.records.values()))
    wrong = ImmutableRecordV1(
        product_id=valid.product_id,
        record_space="other_space",
        record_kind="other_kind",
        record_key=valid.record_key,
        payload_contract=valid.payload_contract,
        payload=valid.payload,
        as_of=valid.as_of,
        available_at=valid.available_at,
        processing_order=1,
    )
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,),
        subject_refs=(admitted.revision.repository_ref,),
        as_of=NOW,
        available_at=NOW,
        page_size=10,
    )

    batch = await AtriumCodeLensResourceProjectionReader(store=_WrongEnvelopeStore(wrong)).read(
        query=query,
        after=None,
        limit=11,
    )

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.records == ()
    assert batch.degraded_reason_refs == ("degraded_reason:invalid-atrium-code-lens-revision",)


@pytest.mark.asyncio
async def test_admission_fails_closed_when_authority_mutates_the_exact_operation() -> None:
    store = _store()
    index = _index()
    with pytest.raises(AtriumCodeLensAdmissionError, match="changed the exact lens admission"):
        await AtriumCodeLensAdmissionService(records=store, authority=_Authority(operation="inspect")).admit(
            context=_context(),
            authority_grant_ref=GRANT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(index),
            lens=_lens(index),
            admitted_at=NOW,
        )
    assert store.records == {}


@pytest.mark.asyncio
async def test_semantic_revision_projection_is_product_scoped_body_free_and_rebuildable() -> None:
    store = _store()
    index = _index()
    admitted = await AtriumCodeLensAdmissionService(records=store, authority=_Authority()).admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(index),
        lens=_lens(index),
        admitted_at=NOW,
    )
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,),
        subject_refs=(admitted.revision.index_snapshot_id,),
        as_of=NOW,
        available_at=NOW,
        page_size=10,
    )
    batch = await AtriumCodeLensResourceProjectionReader(store=store).read(
        query=query,
        after=None,
        limit=11,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert len(batch.records) == 1
    item = batch.records[0]
    assert item.reference.resource_kind is IntelligenceResourceKind.SEMANTIC_REVISION
    assert item.reference.resource_id == admitted.revision.lens_family_id
    assert item.reference.resource_digest == admitted.revision.revision_digest
    assert item.reference.revision == 1
    payload = item.payload.parsed_value()
    assert payload["index_snapshot_id"] == admitted.revision.index_snapshot_id
    assert payload["index_id"] == admitted.revision.index_id
    assert payload["lens_id"] == admitted.revision.lens_id
    assert payload["context_bodies_exposed"] is False
    assert payload["local_snapshot_is_product_truth"] is False
    assert '"body":' not in item.payload.value_json


@pytest.mark.asyncio
async def test_projection_does_not_cross_product_scope() -> None:
    store = _store()
    index = _index()
    await AtriumCodeLensAdmissionService(records=store, authority=_Authority()).admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(index),
        lens=_lens(index),
        admitted_at=NOW,
    )
    foreign = AuthenticatedRuntimeContextV1Alpha1(
        product_id="product:other",
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:other",
        authentication_receipt_digest="sha256:" + "d" * 64,
        authenticated_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
    )
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=foreign,
        product_id="product:other",
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,),
        as_of=NOW,
        available_at=NOW,
        page_size=10,
    )
    batch = await AtriumCodeLensResourceProjectionReader(store=store).read(
        query=query,
        after=None,
        limit=11,
    )
    assert batch.records == ()


def test_snapshot_index_lens_chain_must_be_exact() -> None:
    first = _index()
    second = _index(revision="2" * 40)
    with pytest.raises(AtriumCodeLensAdmissionError, match="one exact chain"):
        # The check occurs before any authorization or append.
        from core.engine.code_intelligence.resource_plane import _intent

        _intent(
            product_id=PRODUCT,
            repository_ref=REPOSITORY,
            snapshot=_snapshot(first),
            lens=_lens(second),
        )


def test_supported_host_composition_admits_only_the_existing_generic_kind() -> None:
    reader = intelligence_resource_projection_reader(_store())
    assert IntelligenceResourceKind.SEMANTIC_REVISION in reader.supported_kinds
    assert not any("code" in kind.value for kind in IntelligenceResourceKind)


def _query() -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,),
        as_of=NOW,
        available_at=NOW,
        page_size=10,
    )


@pytest.mark.asyncio
async def test_projection_fails_closed_above_its_explicit_history_bound() -> None:
    """Admitted product history must not dictate unbounded work per page.

    Per-family chain revalidation has to see a family whole, so this reader
    cannot page its own source query; it therefore refuses above an explicit
    bound instead of decoding, projecting, and sorting an unbounded history.
    """

    from core.engine.code_intelligence.resource_plane import (
        CODE_LENS_HISTORY_BOUND_REASON,
        MAX_PROJECTED_CODE_LENS_REVISIONS,
    )

    counted: list[dict] = []

    class _OversizedHistoryStore:
        async def count_as_of(self, **kwargs) -> int:
            counted.append(kwargs)
            return MAX_PROJECTED_CODE_LENS_REVISIONS + 1

        async def read_as_of(self, **kwargs):
            raise AssertionError("bounded projection must not read history past its explicit limit")

    batch = await AtriumCodeLensResourceProjectionReader(store=_OversizedHistoryStore()).read(
        query=_query(),
        after=None,
        limit=10,
    )

    assert batch.records == ()
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert batch.degraded_reason_refs == (CODE_LENS_HISTORY_BOUND_REASON,)
    assert counted == [
        {
            "product_id": PRODUCT,
            "record_space": CODE_LENS_RECORD_SPACE,
            "record_kind": CODE_LENS_RECORD_KIND,
            "available_at": NOW,
        }
    ]


@pytest.mark.asyncio
async def test_projection_still_serves_history_at_the_bound() -> None:
    from core.engine.code_intelligence.resource_plane import MAX_PROJECTED_CODE_LENS_REVISIONS

    store = _store()
    index = _index()
    await AtriumCodeLensAdmissionService(records=store, authority=_Authority()).admit(
        context=_context(),
        authority_grant_ref=GRANT,
        repository_ref=REPOSITORY,
        snapshot=_snapshot(index),
        lens=_lens(index),
        admitted_at=NOW,
    )

    class _AtBoundStore:
        def __init__(self, inner) -> None:
            self.inner = inner

        async def count_as_of(self, **kwargs) -> int:
            return MAX_PROJECTED_CODE_LENS_REVISIONS

        async def read_as_of(self, **kwargs):
            return await self.inner.read_as_of(**kwargs)

    batch = await AtriumCodeLensResourceProjectionReader(store=_AtBoundStore(store)).read(
        query=_query(),
        after=None,
        limit=10,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert len(batch.records) == 1
