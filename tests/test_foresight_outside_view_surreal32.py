"""Real SurrealDB parser regression for the outside-view ordered projection."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager

import pytest
from surrealdb import AsyncSurreal

from core.engine.foresight.outside_view import load_outside_view_baseline

pytestmark = pytest.mark.e2e


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 20.0) -> None:
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
    def __init__(self, url: str) -> None:
        self.url = url

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use("outside_view_test", "outside_view_test")
        try:
            yield db
        finally:
            await db.close()


@pytest.mark.asyncio
async def test_surreal32_accepts_ordered_closed_prediction_projection(tmp_path) -> None:
    surreal = os.environ.get("ACE_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")

    port = _port()
    log = (tmp_path / "surreal.log").open("wb")
    process = subprocess.Popen(
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
            "memory",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        await _wait_port(port, process)
        pool = _DirectPool(f"ws://127.0.0.1:{port}")
        async with pool.connection() as db:
            await db.query("DEFINE TABLE prediction_outcome SCHEMALESS")
            await db.query("DEFINE TABLE decision_prediction SCHEMALESS")
            await db.query(
                "CREATE decision_prediction:parser_regression SET "
                "product = product:outside_view, closed = true, horizon_days = 14, "
                "created_at = time::now()"
            )

        baseline = await load_outside_view_baseline(
            product_id="product:outside_view",
            target_capability_ids=["auth"],
            discipline="testing",
            horizon_days=14,
            pool=pool,
        )

        # An invalid ORDER BY projection is caught by the product's fail-open
        # path and reports `unavailable`; clean parsing reaches cold-start.
        assert baseline["state"] == "cold_start"
        assert baseline["reason"] == "no_eligible_settled_analogues"
        assert baseline["reference_class"]["product_id"] == "product:outside_view"
        assert baseline["sample"]["candidate_count"] == 0
    finally:
        await _stop(process)
        log.close()
