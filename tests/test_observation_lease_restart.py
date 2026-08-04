"""Disposable SurrealKV crash/restart proof for TP1B processing leases."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from core.engine.capture.leases import claim_next_observation
from core.engine.capture.lifecycle import load_outcome_receipt, process_observation_attempt
from core.engine.capture.outcomes import ObservationSynthesisOutcomeV1, SuccessfulDisposition
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
        await db.use("ace_tp1b_restart", "ace_tp1b_restart")
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


class _SkipSynthesizer:
    def __init__(self, **_kwargs):
        self._db_pool = None
        self._attempt_id = None

    async def add_observation(self, observation):
        outcome = ObservationSynthesisOutcomeV1(
            observation_id=str(observation["id"]),
            disposition=SuccessfulDisposition.SKIPPED,
            reason="provider-free restart recovery proof",
        )
        return {
            "new_insights": 0,
            "updates": 0,
            "conflicts": 0,
            "skipped": 1,
            "outcomes": [outcome.model_dump(mode="json")],
        }

    async def flush(self):
        return {"new_insights": 0, "updates": 0, "conflicts": 0, "skipped": 0, "outcomes": []}


@pytest.mark.asyncio
async def test_expired_processing_attempt_recovers_and_survives_database_restart(tmp_path):
    surreal = os.environ.get("ACE_TP1B_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    url = f"ws://127.0.0.1:{port}"
    store = tmp_path / "surrealkv"
    log = (tmp_path / "surreal.log").open("wb")
    process: subprocess.Popen | None = _start(surreal, port=port, store=store, log=log)
    product_a = "product:tp1b_restart_a"
    product_b = "product:tp1b_restart_b"
    observation_id = "observation:tp1b_restart"
    now = datetime.now(timezone.utc)

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
            for version, name in (
                (161, "v161_synthesis_outcome_receipt.surql"),
                (162, "v162_observation_processing_leases.surql"),
            ):
                migration = ROOT / "core/schema" / name
                await apply_file(db, version, migration.name, migration.read_text())
            await db.query("CREATE product:tp1b_restart_a SET name = 'A'")
            await db.query("CREATE product:tp1b_restart_b SET name = 'B'")
            await db.query(
                """
                CREATE observation:tp1b_restart SET
                    product = product:tp1b_restart_a,
                    content = 'crashed attempt input',
                    observation_type = 'pattern',
                    confidence = 0.8,
                    status = 'pending',
                    processing_state = 'processing',
                    processing_attempt_count = 1,
                    retry_count = 0,
                    processing_started_at = $started_at,
                    processing_route = 'worker_leased',
                    processing_lease_id = $lease_id,
                    processing_lease_owner = 'worker:crashed:restart',
                    processing_lease_generation = 1,
                    processing_lease_acquired_at = $started_at,
                    processing_lease_heartbeat_at = $heartbeat_at,
                    processing_lease_expires_at = $expires_at,
                    processing_lease_recovered = false,
                    processing_lease_prior_state = 'pending',
                    created_at = $started_at,
                    updated_at = $started_at
                """,
                {
                    "started_at": now - timedelta(minutes=10),
                    "heartbeat_at": now - timedelta(minutes=9),
                    "expires_at": now - timedelta(minutes=8),
                    "lease_id": f"observation_lease:{'d' * 32}",
                },
            )

        # Simulate process/database death while the attempt is marked active.
        await _stop(process)
        process = _start(surreal, port=port, store=store, log=log)
        await _wait_port(port, process)
        restarted_pool = _DirectPool(url)

        assert (
            await claim_next_observation(
                restarted_pool,
                product_id=product_b,
                owner_id="worker:foreign:restart",
                lease_seconds=10,
            )
            is None
        )
        recovered = await claim_next_observation(
            restarted_pool,
            product_id=product_a,
            owner_id="worker:replacement:restart",
            lease_seconds=10,
        )
        assert recovered is not None
        assert recovered.lease.recovered_attempt is True
        assert recovered.lease.generation == 2
        assert (
            await claim_next_observation(
                restarted_pool,
                product_id=product_a,
                owner_id="worker:second:restart",
                lease_seconds=10,
            )
            is None
        )

        receipt = await process_observation_attempt(
            recovered.observation,
            db_pool=restarted_pool,
            route="worker_leased",
            synthesizer_factory=_SkipSynthesizer,
            scope_prevalidated=True,
            lease_id=recovered.lease.lease_id,
            lease_owner=recovered.lease.owner_id,
            lease_recovered=True,
        )
        assert receipt.attempt_count == 1

        # Restart again to prove the recovered terminal state and receipt are durable.
        await _stop(process)
        process = _start(surreal, port=port, store=store, log=log)
        await _wait_port(port, process)
        final_pool = _DirectPool(url)
        async with final_pool.connection() as db:
            observation = parse_one(await db.query("SELECT * FROM ONLY observation:tp1b_restart"))
        assert observation["status"] == "processed"
        assert observation["processing_state"] == "succeeded"
        assert observation["processing_attempt_count"] == 1
        assert observation.get("processing_lease_id") is None
        assert (
            await load_outcome_receipt(
                final_pool,
                receipt_id=receipt.receipt_id,
                product_id=product_a,
            )
            == receipt
        )
    finally:
        await _stop(process)
        log.close()
