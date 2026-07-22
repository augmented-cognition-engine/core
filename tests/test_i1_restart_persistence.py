"""Fresh-process HTTP/MCP persistence proof for I1 closeout.

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
        await _assert_schema_version(db_url, 145)
        await _verify_legacy_rows_survive_v144(db_url)
        client = AceClient(base_url=api_url, token=token, timeout=10)
        thin_tools._client = client

        async def submit_decision(state: str) -> tuple[str, str]:
            task = await thin_tools.ace_task(
                f"Exercise the {state} I1 disposition",
                request_id=f"i1-closeout-{state}-v1",
                decision={
                    "selected_option": f"Preserve the {state} disposition",
                    "scope": "I1 closeout restart acceptance",
                    "assumptions": ["The disposable store is durable across API processes"],
                    "alternatives": ["Lose the disposition on restart"],
                    "reconsideration_conditions": ["The existing contract cannot preserve identity"],
                    "evidence_refs": [f"test:i1-restart:{state}"],
                    "decision_type": "direction",
                },
            )
            task_id = task["id"]
            for _ in range(50):
                status = await thin_tools.ace_status(task_id=task_id)
                if status["task"]["status"] == "completed":
                    receipt = status["task"]["decision_receipt"]
                    return task_id, receipt["decision_id"]
                await asyncio.sleep(0.1)
            raise AssertionError("deterministic task did not complete")

        identities = {state: await submit_decision(state) for state in ("unresolved", "accepted", "edited", "rejected")}
        feedback = await client._ensure_client()
        for state in ("accepted", "edited", "rejected"):
            task_id, _ = identities[state]
            payload = {
                "feedback_human": state,
                "surface": "cli",
                "rationale": f"Recorded {state} in restart fixture",
            }
            if state == "edited":
                payload["edited_output"] = "Human-edited deterministic fixture output."
            response = await feedback.patch(
                f"/tasks/{task_id}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

        task_id, decision_id = identities["accepted"]
        base = await thin_tools.ace_capture(
            observation_type="correction",
            content="Keep the relationship typed and bounded.",
            domain_path="i1.restart",
            confidence=1.0,
            affected_decision_id=decision_id,
            affected_task_id=task_id,
        )
        base_id = base["correction"]["correction_id"]
        superseding = await thin_tools.ace_capture(
            observation_type="correction",
            content="Supersede the original correction without deleting it.",
            domain_path="i1.restart",
            supersedes_correction_id=base_id,
        )
        superseding_id = superseding["correction"]["correction_id"]
        contesting = await thin_tools.ace_capture(
            observation_type="correction",
            content="Contest the superseding correction.",
            domain_path="i1.restart",
            contests_correction_id=superseding_id,
        )
        contesting_id = contesting["correction"]["correction_id"]
        invalidating = await thin_tools.ace_capture(
            observation_type="correction",
            content="Invalidate the contested correction.",
            domain_path="i1.restart",
            invalidates_correction_id=contesting_id,
        )
        invalidating_id = invalidating["correction"]["correction_id"]
        expired = await thin_tools.ace_capture(
            observation_type="correction",
            content="This correction has reached its explicit expiry.",
            domain_path="i1.restart",
            expires_at="2020-01-01T00:00:00Z",
        )
        expired_id = expired["correction"]["correction_id"]
        before_load = await thin_tools.ace_load("i1.restart")
        before = {item["correction_id"]: item for item in before_load["corrections"]}

        await client.close()
        client = None
        thin_tools._client = None
        await _stop(api_process)
        api_process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
        await _wait_health(api_url, api_process)

        fresh_client = AceClient(base_url=api_url, token=token, timeout=10)
        client = fresh_client
        thin_tools._client = fresh_client
        after_load = await thin_tools.ace_load("i1.restart")
        after = {item["correction_id"]: item for item in after_load["corrections"]}

        for state, (state_task_id, state_decision_id) in identities.items():
            after_status = await thin_tools.ace_status(task_id=state_task_id)
            receipt = after_status["task"]["decision_receipt"]
            assert receipt["decision_id"] == state_decision_id
            assert receipt["originating_task_id"] == state_task_id
            assert receipt["human_disposition"]["state"] == state
            assert receipt["completeness"]["state"] == "complete"
            assert receipt["provenance"]["state"] == "complete"

        assert after.keys() >= {base_id, superseding_id, contesting_id, invalidating_id, expired_id}
        for correction_id in (base_id, superseding_id, contesting_id, invalidating_id, expired_id):
            assert after[correction_id]["relationship"] == before[correction_id]["relationship"]
            assert after[correction_id]["provenance"] == before[correction_id]["provenance"]
        assert after[base_id]["lifecycle_state"] == "superseded"
        assert after[base_id]["relationship"]["affected_decision_id"] == decision_id
        assert after[base_id]["relationship"]["affected_task_id"] == task_id
        assert after[superseding_id]["lifecycle_state"] == "contested"
        assert after[contesting_id]["lifecycle_state"] == "invalidated"
        assert after[invalidating_id]["lifecycle_state"] == "active"
        assert after[expired_id]["lifecycle_state"] == "expired"
        assert after[expired_id]["stored_lifecycle_state"] == "active"
    finally:
        thin_tools._client = None
        if client:
            await client.close()
        await _stop(api_process)
        await _stop(db_process)
        api_log.close()
        db_log.close()
