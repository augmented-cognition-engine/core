"""PI9 delivery e2e: confirmed deletion covers workspace derivatives and survives a real restart.

Kills and respawns an actual disposable SurrealDB process against the same on-disk
store (the arm-B restart-continuity pattern) and proves:
(a) a confirmed deletion — primary records AND workspace derivatives (graph rows,
    edges, vectors) — does not resurrect after the database process restarts; and
(b) the ownership journey resumes across the restart: the idempotent confirmation
    replay reproduces the byte-identical deletion proof from the reopened store.

Requires a local ``surreal`` binary; skips cleanly otherwise.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from ace.application.personal_intelligence_ownership import PersonalIntelligenceOwnershipService
from ace.core.personal_intelligence_ownership import (
    PersonalIntelligenceDeleteConfirmationV1Alpha1,
    PersonalIntelligenceDeletePreviewRequestV1Alpha1,
)
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from core.engine.core.db import parse_record_id
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.personal_intelligence_derivative_erasure import SurrealWorkspaceDerivativeErasure
from core.engine.core.recovery import DatabaseTarget
from core.engine.search.vector_store import VectorStore

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[2]
PRODUCT = "product:personal-ownership-delivery"
GRAPH_ID = "delivery_workspace"
NOW = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise RuntimeError("disposable SurrealDB did not accept connections")


async def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, 10)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait)


class _SingleConnectionPool:
    def __init__(self, target: DatabaseTarget) -> None:
        self.target = target
        self.db: AsyncSurreal | None = None

    async def open(self) -> None:
        db = AsyncSurreal(self.target.endpoint)
        await db.connect()
        await db.signin({"username": self.target.username, "password": self.target.password})
        await db.use(self.target.namespace, self.target.database)
        self.db = db

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    @asynccontextmanager
    async def connection(self):
        if self.db is None:
            raise RuntimeError("fixture pool is closed")
        yield self.db


def _surreal_process(binary: str, port: int, store: Path, log) -> subprocess.Popen:
    return subprocess.Popen(
        [
            binary,
            "start",
            "--no-banner",
            "--username",
            "root",
            "--password",
            "root",
            "--bind",
            f"127.0.0.1:{port}",
            f"surrealkv://{store}",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


class _AllowOwner:
    async def authorize(self, **kwargs) -> None:
        return None


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="actor:owner",
        authentication_receipt_ref="authentication_receipt:personal-owner",
        authentication_receipt_digest=f"sha256:{'1' * 64}",
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _record(*, key: str, secret: str, order: int) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="live",
        record_kind="brief",
        record_key=key,
        payload_contract="example.intelligence/v1",
        payload={"secret": secret, "source_ref": f"source:{key}"},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=1),
        processing_order=order,
    )


async def _define_tables(pool: _SingleConnectionPool) -> None:
    """The production store runs against the applied schema; mirror the tables it SELECTs from.

    SurrealDB v2 raises NotFoundError on SELECT from a never-created table, so the
    disposable instance needs the store/graph tables defined (schemaless) up front.
    """

    tables = (
        "immutable_record",
        "append_only_transaction_receipt",
        "governed_state_head",
        "graph",
        "graph_file",
        "graph_function",
        "imports",
        "related_to",
        "produced",
        "improves",
    )
    async with pool.connection() as db:
        for table in tables:
            await db.query(f"DEFINE TABLE IF NOT EXISTS {table} SCHEMALESS")


async def _seed_primary(store: SurrealImmutableRecordStore) -> None:
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT,
            record_space="live",
            transaction_key="seed-0",
            records=(_record(key="brief:1", secret="alpha", order=0), _record(key="brief:2", secret="beta", order=1)),
            submitted_at=NOW,
        )
    )


async def _seed_workspace(pool: _SingleConnectionPool, vectors: VectorStore) -> None:
    """A co-activated Code Intelligence workspace: graph rows, edges, and vectors."""

    async with pool.connection() as db:
        await db.query(
            "UPSERT type::record('graph', $gid) CONTENT "
            "{graph_id: $gid, name: 'delivery', repo_path: '/w', mode: 'temporary', product: $product}",
            {"gid": GRAPH_ID, "product": parse_record_id(PRODUCT)},
        )
        for slug, path in (("a_py", "a.py"), ("b_py", "b.py")):
            await db.query(
                "UPSERT type::record('graph_file', $slug) CONTENT "
                "{path: $path, name: $path, extension: '.py', language: 'python', graph_id: $gid}",
                {"slug": slug, "path": path, "gid": GRAPH_ID},
            )
        await db.query(
            "UPSERT type::record('graph_function', 'a_py_fn') CONTENT "
            "{name: 'fn', file: type::record('graph_file', 'a_py'), kind: 'function', graph_id: $gid}",
            {"gid": GRAPH_ID},
        )
        await db.query(
            "RELATE (type::record('graph_file', 'a_py'))->imports->(type::record('graph_file', 'b_py')) "
            "SET import_name = 'b', source = 'scanner'"
        )
    await vectors.upsert("a.py", [1.0, 0.0, 0.0, 0.0], {"path": "a.py", "graph_id": GRAPH_ID})
    await vectors.upsert("b.py", [0.0, 1.0, 0.0, 0.0], {"path": "b.py", "graph_id": GRAPH_ID})
    await vectors.upsert("a.py::fn", [0.0, 0.0, 1.0, 0.0], {"file": "a.py", "name": "fn", "kind": "function"})


async def _graph_row_count(pool: _SingleConnectionPool) -> int:
    total = 0
    async with pool.connection() as db:
        for table in ("graph", "graph_file", "graph_function", "imports"):
            rows = await db.query(f"SELECT count() AS n FROM {table} GROUP ALL")
            if isinstance(rows, list) and rows:
                first = rows[0]
                if isinstance(first, dict) and "result" in first:
                    first = (first.get("result") or [{}])[0] if first.get("result") else {}
                total += int(first.get("n", 0)) if isinstance(first, dict) else 0
    return total


def _service(pool: _SingleConnectionPool, vectors: VectorStore) -> PersonalIntelligenceOwnershipService:
    store = SurrealImmutableRecordStore(pool)
    return PersonalIntelligenceOwnershipService(
        store=store,
        authorization=_AllowOwner(),
        derivatives=SurrealWorkspaceDerivativeErasure(pool=pool, vector_store=vectors),
    )


@pytest.mark.asyncio
async def test_confirmed_deletion_covers_derivatives_and_survives_a_real_restart(tmp_path):
    surreal = os.environ.get("ACE_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")

    port = _port()
    data_dir = tmp_path / "store"
    log = (tmp_path / "surreal.log").open("w")
    target = DatabaseTarget(
        endpoint=f"ws://127.0.0.1:{port}",
        namespace="ace_pi9_delivery",
        database="ace_pi9_delivery",
        username="root",
        password="root",
    )
    process: subprocess.Popen | None = None
    pool: _SingleConnectionPool | None = None
    vectors = VectorStore(dimensions=4)
    try:
        process = _surreal_process(surreal, port, data_dir, log)
        await _wait_port(port, process)
        pool = _SingleConnectionPool(target)
        await pool.open()
        await _define_tables(pool)
        store = SurrealImmutableRecordStore(pool)
        await _seed_primary(store)
        await _seed_workspace(pool, vectors)

        service = _service(pool, vectors)
        preview = await service.preview_delete(
            PersonalIntelligenceDeletePreviewRequestV1Alpha1(
                authenticated_context=_context(),
                requested_at=NOW,
                expires_at=NOW + timedelta(minutes=15),
            )
        )
        by_kind = {entry.artifact_kind: entry for entry in preview.derived_artifacts}
        assert by_kind["graph_projection"].enumerated_count == 4  # graph + 2 files + 1 function
        assert by_kind["graph_edge"].enumerated_count == 1
        assert by_kind["embedding"].enumerated_count == 2
        assert by_kind["vector_material"].enumerated_count == 1
        assert all(entry.covered for entry in preview.derived_artifacts)

        confirmation = PersonalIntelligenceDeleteConfirmationV1Alpha1(
            authenticated_context=_context(),
            preview=preview,
            confirmation_digest=str(preview.confirmation_digest),
            confirmed_at=NOW + timedelta(minutes=1),
        )
        result = await service.confirm_delete(confirmation)
        assert {entry.artifact_kind for entry in result.proof.derived_artifact_erasure} == {
            "embedding",
            "vector_material",
            "graph_projection",
            "graph_edge",
            "cache",
            "summary",
        }
        assert await _graph_row_count(pool) == 0
        assert await vectors.count_by_payload("graph_id", [GRAPH_ID]) == 0
        assert await vectors.count_by_payload("file", ["a.py", "b.py"]) == 0

        # ------- kill the database process and respawn it on the same on-disk store -------
        await pool.close()
        pool = None
        await _stop(process)
        process = _surreal_process(surreal, port, data_dir, log)
        await _wait_port(port, process)
        pool = _SingleConnectionPool(target)
        await pool.open()

        reopened = SurrealImmutableRecordStore(pool)
        survivors = await reopened.scan_product_records(product_id=PRODUCT)
        assert all(item.record_space == "personal_intelligence_ownership" for item in survivors), (
            "deleted personal records resurrected after a database restart"
        )
        assert await _graph_row_count(pool) == 0, "workspace graph rows resurrected after restart"

        # journey resumes: the idempotent replay reopens the identical proof from the restarted store
        replay_service = _service(pool, vectors)
        replay = await replay_service.confirm_delete(confirmation)
        assert replay.proof == result.proof
        assert replay.transaction_receipt_ref == result.transaction_receipt_ref
    finally:
        if pool is not None:
            await pool.close()
        await _stop(process)
        log.close()
