"""Real SurrealKV and fresh-process proof for durable cancellation reconciliation."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from core.engine.core.db import parse_one
from core.engine.extensions.invocation import normalize_extension_receipt

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
        await db.use("ace_t1a_cancel", "ace_t1a_cancel")
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


def _runtime_env(url: str) -> dict[str, str]:
    return os.environ | {
        "SURREAL_URL": url,
        "SURREAL_NS": "ace_t1a_cancel",
        "SURREAL_DB": "ace_t1a_cancel",
        "SURREAL_USER": "root",
        "SURREAL_PASS": "root",
        "JWT_SECRET": "t1a-disposable-jwt-secret-at-least-32-bytes",
        "ACE_DISABLE_EXTENSIONS": "1",
    }


def _restart_runtime(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-c",
            (
                "import asyncio; "
                "from core.engine.api.tasks import initialize_task_runtime; "
                "print(asyncio.run(initialize_task_runtime()))"
            ),
        ],
        cwd=ROOT,
        env=_runtime_env(url),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.asyncio
async def test_pending_cancellation_reconciles_across_a_fresh_runtime_process(tmp_path):
    surreal = os.environ.get("ACE_T1A_CANCEL_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    url = f"ws://127.0.0.1:{port}"
    store = tmp_path / "surrealkv"
    log = (tmp_path / "surreal.log").open("wb")
    process: subprocess.Popen | None = _start(surreal, port=port, store=store, log=log)
    pool = _DirectPool(url)

    metadata = {
        "contract_version": "extension-invocation-v1",
        "correlation_id": "corr:t1a-restart",
        "capability": {
            "extension_id": "restart_fixture",
            "extension_version": "1.0.0",
            "action": "cooperative-action",
            "input_contract": "extension-invocation-v1",
            "output_contract": "restart-outcome-v1",
            "cancellation_supported": True,
        },
        "request": {"references": []},
        "envelope_hash": "sha256:t1a-restart-fixture",
        "context_resolution": [],
        "attempt": {
            "number": 1,
            "retry_of_task_id": None,
            "resumed_by_task_id": None,
            "root_invocation_id": None,
            "retry_reason": None,
            "retry_actor": None,
            "retry_requested_at": None,
            "retry_policy_version": None,
        },
    }
    task = {
        "contract_version": "async-receipt-v1",
        "status": "running",
        "runtime_id": "runtime-before-restart",
        "product": "product:t1a_restart",
        "user": "user:t1a_restart",
        "workspace": "workspace:t1a_restart",
        "extension_invocation": metadata,
        "extension_receipt": {"attempt": {"status": "running", "terminal": False}},
        "cancellation": {
            "state": "requested",
            "requested_at": "2026-08-09T12:00:00Z",
            "acknowledged_at": None,
            "actor": "user:t1a_restart",
            "reason": "operator requested stop",
        },
        "execution": {"state": "running", "usable_output": False},
    }

    try:
        await _wait_port(port, process)
        async with pool.connection() as db:
            await db.query("DEFINE TABLE task SCHEMALESS")
            await db.query("CREATE task:t1a_restart CONTENT $task", {"task": task})

        first = await asyncio.to_thread(_restart_runtime, url)
        assert first.returncode == 0, first.stderr
        assert first.stdout.strip().endswith("1")

        async with pool.connection() as db:
            reconciled = parse_one(await db.query("SELECT * FROM ONLY task:t1a_restart"))
        assert reconciled["status"] == "degraded"
        assert reconciled["error"]["code"] == "cancellation_process_unavailable"
        assert reconciled["execution"]["state"] == "interrupted"
        assert reconciled["execution"]["usable_output"] is False
        assert reconciled["cancellation"]["state"] == "process_stopped_during_cancellation"
        assert reconciled["cancellation"]["actor"] == "user:t1a_restart"
        assert reconciled["cancellation"]["reason"] == "operator requested stop"
        receipt = reconciled["extension_receipt"]
        assert receipt["attempt"]["status"] == "degraded"
        assert receipt["attempt"]["terminal"] is True
        assert receipt["cancellation"]["state"] == "process_stopped_during_cancellation"
        assert receipt["raw_core_output"]["available"] is False
        public_receipt = normalize_extension_receipt(receipt, task=reconciled)
        assert public_receipt["raw_core_output"] == {"available": False, "content": None}

        terminal_fact = {
            "status": reconciled["status"],
            "cancellation": reconciled["cancellation"],
            "extension_receipt": receipt,
        }
        second = await asyncio.to_thread(_restart_runtime, url)
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip().endswith("0")
        async with pool.connection() as db:
            replayed = parse_one(await db.query("SELECT * FROM ONLY task:t1a_restart"))
        assert {
            "status": replayed["status"],
            "cancellation": replayed["cancellation"],
            "extension_receipt": replayed["extension_receipt"],
        } == terminal_fact
    finally:
        await _stop(process)
        log.close()
