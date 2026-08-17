from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ace.core import (
    AppendOnlyTransactionRequestV1,
    GovernedStateCommitRequestV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordReplayConflict,
    ImmutableRecordV1,
    ResolvedApprovalReceiptV1,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 16, tzinfo=UTC)
PRODUCT = "product:runtime-use"


def _head(
    kind: str = "runtime_state",
    state_id: str = "runtime_state:subject",
    *,
    sequence: int = 1,
) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=sequence,
        revision_id=f"{kind}_revision:{sequence}",
        commit_receipt_id=f"governed_state_commit_receipt:{kind}-{sequence}",
        updated_at=NOW,
    )


def _append_request(
    *,
    key: str = "append:one",
    preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = (),
) -> AppendOnlyTransactionRequestV1:
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="conformance",
        record_kind="opaque",
        record_key=key,
        payload_contract="example.opaque/v1",
        payload={"value": key},
        as_of=NOW,
        available_at=NOW,
        processing_order=0,
    )
    return AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="conformance",
        transaction_key=key,
        records=(record,),
        submitted_at=NOW,
        governed_state_preconditions=preconditions,
    )


def _divergent_append_request(
    request: AppendOnlyTransactionRequestV1,
) -> AppendOnlyTransactionRequestV1:
    source = request.records[0]
    record = ImmutableRecordV1(
        product_id=source.product_id,
        record_space=source.record_space,
        record_kind=source.record_kind,
        record_key=source.record_key,
        payload_contract=source.payload_contract,
        payload={"value": "different"},
        as_of=source.as_of,
        available_at=source.available_at,
        processing_order=source.processing_order,
    )
    return AppendOnlyTransactionRequestV1(
        product_id=request.product_id,
        record_space=request.record_space,
        transaction_key=request.transaction_key,
        records=(record,),
        submitted_at=request.submitted_at,
        governed_state_preconditions=request.governed_state_preconditions,
    )


def test_governed_state_receipt_identity_is_timezone_offset_invariant() -> None:
    offset_time = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    revision = GovernedStateRevisionV1(
        state_kind="runtime_state",
        product_id=PRODUCT,
        state_id="runtime_state:timezone",
        sequence=1,
        revision_id="runtime_state_revision:timezone:1",
        material_hash="a" * 64,
        approval_subject_ref="approval_subject:timezone",
        payload_contract="example.runtime-state/v1",
        payload={"status": "ready"},
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref="actor:timezone",
        approval=ResolvedApprovalReceiptV1(
            receipt_ref="approval:timezone",
            product_id=PRODUCT,
            subject_ref=revision.approval_subject_ref,
            actor_ref="actor:timezone",
            receipt_hash="b" * 64,
            approved_at=offset_time,
        ),
        committed_at=offset_time,
    )

    receipt = request.receipt()
    assert request.committed_at == NOW
    assert request.approval.approved_at == NOW
    assert receipt == type(receipt).model_validate(receipt.model_dump(mode="json"))


def test_empty_preconditions_serialize_out_and_preserve_legacy_identity_material() -> None:
    implicit = _append_request()
    explicit = _append_request(preconditions=())
    assert implicit == explicit
    assert implicit.request_hash == explicit.request_hash
    assert "governed_state_preconditions" not in implicit.model_dump(mode="json")
    assert "governed_state_preconditions" not in implicit.receipt().model_dump(mode="json")


@pytest.mark.asyncio
async def test_governed_state_resolves_exact_historical_receipt_by_revision() -> None:
    from core.engine.core.db import parse_record_id
    from core.engine.core.governed_state import SurrealGovernedStateStore

    revision = GovernedStateRevisionV1(
        state_kind="runtime_state",
        product_id=PRODUCT,
        state_id="runtime_state:history",
        sequence=1,
        revision_id="runtime_state_revision:history-1",
        material_hash="a" * 64,
        approval_subject_ref="approval_subject:history",
        payload_contract="example.runtime-state/v1",
        payload={"status": "ready"},
    )
    receipt = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref="principal:operator",
        approval=ResolvedApprovalReceiptV1(
            receipt_ref="approval:history",
            product_id=PRODUCT,
            subject_ref=revision.approval_subject_ref,
            actor_ref="principal:operator",
            receipt_hash="b" * 64,
            approved_at=NOW,
        ),
        committed_at=NOW,
    ).receipt()

    class _Connection:
        async def query(self, query, params):
            assert "revision_id = $revision_id" in query
            assert params["revision_id"] == revision.revision_id
            assert params["product"] == parse_record_id(PRODUCT)
            return [{"payload": receipt.model_dump(mode="python")}]

    class _Pool:
        @asynccontextmanager
        async def connection(self):
            yield _Connection()

    loaded = await SurrealGovernedStateStore(_Pool()).load_receipt_for_revision(
        revision.revision_id,
        product_id=PRODUCT,
    )
    assert loaded == receipt


def test_preconditions_are_canonical_and_each_head_identity_is_unique() -> None:
    first = GovernedStateHeadPreconditionV1Alpha1.from_head(_head())
    second = GovernedStateHeadPreconditionV1Alpha1.from_head(_head("source_definition", "source_definition:primary"))
    request = _append_request(preconditions=(second, first))
    assert request.governed_state_preconditions == (first, second)
    with pytest.raises(ValidationError, match="at most once"):
        _append_request(preconditions=(first, first))


@pytest.mark.parametrize("failure_kind", ["query_error", "connection_loss"])
@pytest.mark.parametrize("winner_kind", ["exact", "divergent", "none", "reload_failure"])
@pytest.mark.asyncio
async def test_surreal_failed_transaction_classifies_only_one_exact_reloaded_winner(
    failure_kind: str,
    winner_kind: str,
) -> None:
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    request = _append_request(key=f"append:{failure_kind}:{winner_kind}")
    expected = request.receipt()
    divergent = _divergent_append_request(request).receipt()

    class _Connection:
        async def query_raw(self, _query, _params):
            if failure_kind == "connection_loss":
                raise RuntimeError("secret-connection-loss")
            return {
                "result": [
                    {
                        "status": "ERR",
                        "result": "secret-create-only-collision",
                    }
                ]
            }

    class _Pool:
        @asynccontextmanager
        async def connection(self):
            yield _Connection()

    class _ScriptedStore(SurrealImmutableRecordStore):
        def __init__(self):
            super().__init__(_Pool())
            self.receipt_loads = 0

        async def _load_receipt_by_id(self, *args, **kwargs):
            self.receipt_loads += 1
            if self.receipt_loads == 1:
                return None
            if winner_kind == "exact":
                return expected
            if winner_kind == "divergent":
                return divergent
            if winner_kind == "reload_failure":
                raise RuntimeError("secret-reload-failure")
            return None

        async def load_record(self, *args, **kwargs):
            return None

    store = _ScriptedStore()
    if winner_kind == "exact":
        assert await store.append(request) == expected
    elif winner_kind == "divergent":
        with pytest.raises(ImmutableRecordReplayConflict):
            await store.append(request)
    else:
        with pytest.raises(ImmutableRecordPersistenceError) as failure:
            await store.append(request)
        assert "secret" not in str(failure.value)
        assert failure.value.__cause__ is None
    assert store.receipt_loads == 2


@pytest.mark.parametrize("winner_kind", ["exact", "divergent"])
@pytest.mark.asyncio
async def test_surreal_preflight_record_race_reloads_the_complete_receipt_once(
    winner_kind: str,
) -> None:
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    request = _append_request(key=f"append:preflight:{winner_kind}")
    expected = request.receipt()
    winner = expected if winner_kind == "exact" else _divergent_append_request(request).receipt()

    class _UnusedPool:
        @asynccontextmanager
        async def connection(self):
            raise AssertionError("preflight winner classification must not enter a transaction")
            yield

    class _PreflightRaceStore(SurrealImmutableRecordStore):
        def __init__(self):
            super().__init__(_UnusedPool())
            self.receipt_loads = 0

        async def _load_receipt_by_id(self, *args, **kwargs):
            self.receipt_loads += 1
            return None if self.receipt_loads == 1 else winner

        async def load_record(self, *args, **kwargs):
            return request.records[0]

    store = _PreflightRaceStore()
    if winner_kind == "exact":
        assert await store.append(request) == expected
    else:
        with pytest.raises(ImmutableRecordReplayConflict):
            await store.append(request)
    assert store.receipt_loads == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_surreal_append_checks_head_in_transaction_and_restart_replays_historically(db_pool) -> None:
    from ace.core import (
        GovernedStateCommitRequestV1,
        GovernedStateRevisionV1,
        ResolvedApprovalReceiptV1,
    )
    from core.engine.core.governed_state import SurrealGovernedStateStore
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    product_id = f"product:precondition-{uuid4().hex}"
    occurred_at = datetime.now(UTC) - timedelta(minutes=1)
    state_id = "runtime_state:subject"
    governed = SurrealGovernedStateStore(db_pool)

    async def commit(sequence: int, prior: str | None):
        revision_id = f"runtime_state_revision:{uuid4().hex}"
        revision = GovernedStateRevisionV1(
            state_kind="runtime_state",
            product_id=product_id,
            state_id=state_id,
            sequence=sequence,
            revision_id=revision_id,
            material_hash=("a" if sequence == 1 else "b") * 64,
            prior_revision_id=prior,
            approval_subject_ref="runtime_state:approval-subject",
            payload_contract="example.runtime-state/v1",
            payload={"sequence": sequence},
        )
        request = GovernedStateCommitRequestV1(
            revision=revision,
            expected_head_revision_id=prior,
            actor_ref="principal:operator",
            approval=ResolvedApprovalReceiptV1(
                receipt_ref=f"approval:runtime-{sequence}",
                product_id=product_id,
                subject_ref=revision.approval_subject_ref,
                actor_ref="principal:operator",
                receipt_hash="c" * 64,
                approved_at=occurred_at,
            ),
            committed_at=occurred_at + timedelta(seconds=sequence),
        )
        await governed.commit(request)
        head = await governed.load_head(
            state_kind="runtime_state",
            product_id=product_id,
            state_id=state_id,
        )
        assert head is not None
        return head

    first_head = await commit(1, None)
    precondition = GovernedStateHeadPreconditionV1Alpha1.from_head(first_head)

    def request(
        key: str,
        required: GovernedStateHeadPreconditionV1Alpha1 = precondition,
    ) -> AppendOnlyTransactionRequestV1:
        record = ImmutableRecordV1(
            product_id=product_id,
            record_space="precondition_test",
            record_kind="opaque",
            record_key=key,
            payload_contract="example.opaque/v1",
            payload={"key": key},
            as_of=occurred_at,
            available_at=occurred_at + timedelta(seconds=3),
            processing_order=0,
        )
        return AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space="precondition_test",
            transaction_key=key,
            records=(record,),
            submitted_at=occurred_at + timedelta(seconds=3),
            governed_state_preconditions=(required,),
        )

    store = SurrealImmutableRecordStore(db_pool)
    first_request = request("transaction:first")
    first_receipt = await store.append(first_request)
    restarted = SurrealImmutableRecordStore(db_pool)
    assert (
        await restarted.load_transaction_receipt(
            product_id=product_id,
            record_space="precondition_test",
            transaction_key="transaction:first",
        )
        == first_receipt
    )

    second_head = await commit(2, first_head.revision_id)
    assert await restarted.append(first_request) == first_receipt
    stale = request("transaction:stale")
    with pytest.raises(ImmutableRecordPreconditionFailed):
        await restarted.append(stale)
    assert (
        await restarted.load_record(
            str(stale.records[0].storage_id),
            product_id=product_id,
            record_space="precondition_test",
            record_kind="opaque",
        )
        is None
    )

    class _MutatingConnection:
        def __init__(self, db, mutation):
            self.db = db
            self.mutation = mutation
            self.mutated = False

        def __getattr__(self, name):
            return getattr(self.db, name)

        async def query_raw(self, sql, params):
            if not self.mutated:
                self.mutated = True
                await self.mutation()
            return await self.db.query_raw(sql, params)

    class _MutatingPool:
        def __init__(self, mutation):
            self.mutation = mutation

        @asynccontextmanager
        async def connection(self):
            async with db_pool.connection() as db:
                yield _MutatingConnection(db, self.mutation)

    concurrent_request = request(
        "transaction:concurrent-exact",
        GovernedStateHeadPreconditionV1Alpha1.from_head(second_head),
    )

    async def commit_exact_winner_then_advance_head() -> None:
        assert await restarted.append(concurrent_request) == concurrent_request.receipt()
        await commit(3, second_head.revision_id)

    assert (
        await SurrealImmutableRecordStore(_MutatingPool(commit_exact_winner_then_advance_head)).append(
            concurrent_request
        )
        == concurrent_request.receipt()
    )
    third_head = await governed.load_head(
        state_kind="runtime_state",
        product_id=product_id,
        state_id=state_id,
    )
    assert third_head is not None

    divergent_outer = request(
        "transaction:concurrent-divergent",
        GovernedStateHeadPreconditionV1Alpha1.from_head(third_head),
    )
    divergent_winner = _divergent_append_request(divergent_outer)

    async def commit_divergent_winner() -> None:
        assert await restarted.append(divergent_winner) == divergent_winner.receipt()

    with pytest.raises(ImmutableRecordReplayConflict):
        await SurrealImmutableRecordStore(_MutatingPool(commit_divergent_winner)).append(divergent_outer)
    assert (
        await restarted.load_transaction_receipt(
            product_id=product_id,
            record_space="precondition_test",
            transaction_key="transaction:concurrent-divergent",
        )
        == divergent_winner.receipt()
    )

    race_request = request(
        "transaction:in-flight-race",
        GovernedStateHeadPreconditionV1Alpha1.from_head(third_head),
    )

    async def advance_head_without_admission() -> None:
        await commit(4, third_head.revision_id)

    with pytest.raises(ImmutableRecordPreconditionFailed):
        await SurrealImmutableRecordStore(_MutatingPool(advance_head_without_admission)).append(race_request)
    assert (
        await restarted.load_record(
            str(race_request.records[0].storage_id),
            product_id=product_id,
            record_space="precondition_test",
            record_kind="opaque",
        )
        is None
    )
