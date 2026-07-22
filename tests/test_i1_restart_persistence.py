"""Fresh-process HTTP/MCP persistence proof for I1-01.

This test starts a disposable SurrealKV store and two separate uvicorn API
processes. The orchestration fixture is deterministic and makes zero model
calls; all writes and reads still traverse the production API and thin client.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest
from surrealdb import AsyncSurreal

from ace_mcp_client import tools as thin_tools
from ace_mcp_client.client import AceClient

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[1]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_health(url: str, process: subprocess.Popen, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("I1 fixture process exited before becoming healthy")
        try:
            response = httpx.get(f"{url}/health", timeout=1)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.2)
    raise RuntimeError(f"I1 fixture did not become healthy at {url}")


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
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


async def _verify_legacy_rows_survive_v144(db_url: str) -> None:
    """Reapply v144 over legacy-shaped rows and prove no captured data changes."""
    from scripts.schema_apply import apply_file

    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        await db.query(
            "UPSERT task:i1legacy SET product = product:i1restart, description = 'legacy task', "
            "status = 'completed', output = 'accepted in prose', created_at = time::now()"
        )
        await db.query(
            "UPSERT decision:i1legacy SET product = product:i1restart, title = 'Legacy decision', "
            "decision_type = 'direction', rationale = 'legacy rationale', outcome = 'accepted', "
            "created_at = time::now()"
        )
        await db.query(
            "UPSERT observation:i1legacy SET product = product:i1restart, observation_type = 'correction', "
            "content = 'legacy correction', confidence = 0.8f, source = 'api', status = 'processed', "
            "created_at = time::now()"
        )
        query = (
            "SELECT id, description, output FROM ONLY task:i1legacy; "
            "SELECT id, title, rationale FROM ONLY decision:i1legacy; "
            "SELECT id, content, confidence FROM ONLY observation:i1legacy;"
        )
        before = json.loads(json.dumps(await db.query(query), default=str, sort_keys=True))
        migration = ROOT / "core/schema/v144_decision_correction_receipt.surql"
        await apply_file(db, 144, migration.name, migration.read_text())
        after = json.loads(json.dumps(await db.query(query), default=str, sort_keys=True))
        assert after == before
    finally:
        await db.close()


async def _assert_schema_version(db_url: str, expected: int) -> None:
    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        rows = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
        assert rows and int(rows[0]["value"]) == expected
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_same_decision_and_correction_relationship_survive_real_api_restart(tmp_path):
    surreal = os.environ.get("ACE_I1_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        for candidate in (Path("/opt/homebrew/bin/surreal"), Path.home() / ".surrealdb/surreal"):
            if candidate.exists():
                surreal = str(candidate)
                break
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    version = subprocess.run(
        [surreal, "version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if required_version := os.environ.get("ACE_I1_REQUIRED_SURREAL_VERSION"):
        assert version.startswith(required_version), f"expected SurrealDB {required_version}, found {version}"

    db_port = _port()
    api_port = _port()
    db_url = f"ws://127.0.0.1:{db_port}"
    api_url = f"http://127.0.0.1:{api_port}"
    store = tmp_path / "surrealkv"
    db_log = (tmp_path / "surreal.log").open("wb")
    api_log = (tmp_path / "api.log").open("wb")
    db_process = subprocess.Popen(
        [
            surreal,
            "start",
            "--no-banner",
            "--username",
            "root",
            "--password",
            "root",
            "--bind",
            f"127.0.0.1:{db_port}",
            f"surrealkv://{store}",
        ],
        cwd=ROOT,
        stdout=db_log,
        stderr=subprocess.STDOUT,
    )
    api_process: subprocess.Popen | None = None
    client: AceClient | None = None
    secret = "i1-disposable-jwt-secret-at-least-32-bytes"
    token = jwt.encode(
        {
            "sub": "user:i1restart",
            "product": "product:i1restart",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    env = os.environ | {
        "SURREAL_URL": db_url,
        "SURREAL_NS": "ace_i1_restart",
        "SURREAL_DB": "ace_i1_restart",
        "SURREAL_USER": "root",
        "SURREAL_PASS": "root",
        "JWT_SECRET": secret,
        "API_KEY": "",
        "LLM_API_KEY": "sk-test-placeholder",
        "ACE_DISABLE_EXTENSIONS": "1",
        "REQUIRE_SUBSCRIPTION": "1",
    }
    command = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "tests.i1_restart_app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
    ]

    try:
        await _wait_port(db_port, db_process)
        api_process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
        await _wait_health(api_url, api_process)
        await _assert_schema_version(db_url, 144)
        await _verify_legacy_rows_survive_v144(db_url)
        client = AceClient(base_url=api_url, token=token, timeout=10)
        thin_tools._client = client

        task = await thin_tools.ace_task(
            "Exercise the structured I1 receipt",
            request_id="i1-restart-fixture-v1",
            decision={
                "selected_option": "Keep the existing eleven-tool contract",
                "scope": "I1-01 restart acceptance",
                "assumptions": ["The disposable store is durable across API processes"],
                "alternatives": ["Add a twelfth tool"],
                "reconsideration_conditions": ["The existing contract cannot preserve identity"],
                "evidence_refs": ["test:i1-restart"],
                "decision_type": "direction",
            },
        )
        task_id = task["id"]
        for _ in range(50):
            status = await thin_tools.ace_status(task_id=task_id)
            if status["task"]["status"] == "completed":
                break
            await asyncio.sleep(0.1)
        else:
            raise AssertionError("deterministic task did not complete")
        decision_id = status["task"]["decision_receipt"]["decision_id"]
        unresolved = status["task"]["decision_receipt"]["human_disposition"]
        assert unresolved["state"] == "unresolved"
        assert unresolved["actor"] is None
        assert unresolved["recorded_at"] is None

        feedback = await client._ensure_client()
        response = await feedback.patch(
            f"/tasks/{task_id}",
            json={"feedback_human": "accepted", "surface": "cli", "rationale": "Reviewed in restart fixture"},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        captured = await thin_tools.ace_capture(
            observation_type="correction",
            content="Keep the relationship typed and bounded.",
            domain_path="i1.restart",
            confidence=1.0,
            affected_decision_id=decision_id,
            affected_task_id=task_id,
        )
        correction_id = captured["correction"]["correction_id"]
        before_load = await thin_tools.ace_load("i1.restart")
        before = next(item for item in before_load["corrections"] if item["correction_id"] == correction_id)

        await client.close()
        client = None
        thin_tools._client = None
        await _stop(api_process)
        api_process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
        await _wait_health(api_url, api_process)

        fresh_client = AceClient(base_url=api_url, token=token, timeout=10)
        client = fresh_client
        thin_tools._client = fresh_client
        after_status = await thin_tools.ace_status(task_id=task_id)
        after_load = await thin_tools.ace_load("i1.restart")
        after = next(item for item in after_load["corrections"] if item["correction_id"] == correction_id)

        assert after_status["task"]["decision_receipt"]["decision_id"] == decision_id
        assert after_status["task"]["decision_receipt"]["originating_task_id"] == task_id
        assert after_status["task"]["decision_receipt"]["human_disposition"]["state"] == "accepted"
        assert after["correction_id"] == correction_id
        assert after["relationship"] == before["relationship"]
        assert after["relationship"]["affected_decision_id"] == decision_id
        assert after["relationship"]["affected_task_id"] == task_id
    finally:
        thin_tools._client = None
        if client:
            await client.close()
        await _stop(api_process)
        await _stop(db_process)
        api_log.close()
        db_log.close()
