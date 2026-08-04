"""Disposable SurrealKV restart proof for TP1A synthesis outcome receipts."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from core.engine.capture.lifecycle import load_outcome_receipt, persist_outcome_receipt
from core.engine.capture.outcomes import (
    SYNTHESIS_POLICY_VERSION,
    SYNTHESIS_PROCESSOR_VERSION,
    SYNTHESIS_SCHEMA_VERSION,
    ObservationSynthesisOutcomeV1,
    ProcessingState,
    SuccessfulDisposition,
    SynthesisOutcomeReceiptV1,
    SynthesisProvenanceV1,
    build_attempt_id,
    build_receipt_id,
)
from core.engine.core.db import parse_one
from scripts.schema_apply import apply_file

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[1]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
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


class _DirectPool:
    def __init__(self, url: str):
        self.url = url

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use("ace_tp1a_restart", "ace_tp1a_restart")
        try:
            yield db
        finally:
            await db.close()


def _start(surreal: str, *, port: int, store: Path, log) -> subprocess.Popen:
    return subprocess.Popen(
        [
            surreal,
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


@pytest.mark.asyncio
async def test_receipt_and_references_survive_real_database_restart(tmp_path):
    surreal = os.environ.get("ACE_TP1A_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    url = f"ws://127.0.0.1:{port}"
    store = tmp_path / "surrealkv"
    log = (tmp_path / "surreal.log").open("wb")
    process: subprocess.Popen | None = _start(surreal, port=port, store=store, log=log)
    product_a = "product:tp1a_restart_a"
    product_b = "product:tp1a_restart_b"
    observation_id = "observation:tp1a_restart"
    insight_id = "insight:tp1a_restart"

    try:
        await _wait_port(port, process)
        pool = _DirectPool(url)
        async with pool.connection() as db:
            for statement in (
                "DEFINE TABLE IF NOT EXISTS product SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS observation SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS insight SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS conflict SCHEMALESS",
            ):
                await db.query(statement)
            migration = ROOT / "core/schema/v161_synthesis_outcome_receipt.surql"
            await apply_file(db, 161, migration.name, migration.read_text())
            await db.query("CREATE product:tp1a_restart_a SET name = 'A'")
            await db.query("CREATE product:tp1a_restart_b SET name = 'B'")
            await db.query(
                "CREATE observation:tp1a_restart SET product = product:tp1a_restart_a, "
                "content = 'restart input', observation_type = 'fact', confidence = 0.8, "
                "status = 'pending', created_at = time::now()"
            )
            await db.query(
                "CREATE insight:tp1a_restart SET product = product:tp1a_restart_a, "
                "content = 'restart insight', insight_type = 'fact'"
            )

        now = datetime.now(timezone.utc)
        attempt_id = build_attempt_id(
            product_id=product_a,
            observation_id=observation_id,
            attempt_count=1,
            route="restart_test",
        )
        receipt = SynthesisOutcomeReceiptV1(
            receipt_id=build_receipt_id(product_id=product_a, attempt_id=attempt_id),
            product_id=product_a,
            observation_id=observation_id,
            attempt_id=attempt_id,
            attempt_count=1,
            processing_state=ProcessingState.SUCCEEDED,
            outcome=ObservationSynthesisOutcomeV1(
                observation_id=observation_id,
                disposition=SuccessfulDisposition.INSIGHT_CREATED,
                created_insight_refs=(insight_id,),
            ),
            retryable=False,
            processor_version=SYNTHESIS_PROCESSOR_VERSION,
            policy_version=SYNTHESIS_POLICY_VERSION,
            schema_version=SYNTHESIS_SCHEMA_VERSION,
            material_hash="c" * 64,
            started_at=now,
            completed_at=now,
            provenance=SynthesisProvenanceV1(route="restart_test"),
            explainable_terminal=True,
        )
        assert await persist_outcome_receipt(pool, receipt) == receipt

        await _stop(process)
        process = _start(surreal, port=port, store=store, log=log)
        await _wait_port(port, process)

        restarted_pool = _DirectPool(url)
        loaded = await load_outcome_receipt(
            restarted_pool,
            receipt_id=receipt.receipt_id,
            product_id=product_a,
        )
        assert loaded == receipt
        assert (
            await load_outcome_receipt(
                restarted_pool,
                receipt_id=receipt.receipt_id,
                product_id=product_b,
            )
            is None
        )
        async with restarted_pool.connection() as db:
            observation = parse_one(
                await db.query("SELECT id FROM ONLY observation:tp1a_restart WHERE product = product:tp1a_restart_a")
            )
            insight = parse_one(
                await db.query("SELECT id FROM ONLY insight:tp1a_restart WHERE product = product:tp1a_restart_a")
            )
        assert str(observation["id"]) == observation_id
        assert str(insight["id"]) == insight_id
        assert loaded.outcome and loaded.outcome.created_insight_refs == (insight_id,)
    finally:
        await _stop(process)
        log.close()
