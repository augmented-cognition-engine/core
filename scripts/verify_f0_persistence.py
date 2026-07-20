#!/usr/bin/env python3
"""F0.1 disposable-SurrealDB persistence, migration, concurrency, and restart proof.

This verifier never touches the configured ACE database. It creates two temporary
SurrealKV stores: one fresh install and one v141-to-v142 upgrade. Both stores and
their server/API processes are removed when the run finishes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from schema_apply import SCHEMA_DIR, _split_statements, get_current_version
from surrealdb import AsyncSurreal

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.graph.assertions import RelationshipProposal, persist_resolution, rebuild_projection
from core.engine.graph.legacy_migration import migrate_legacy_edges

ROOT = Path(__file__).resolve().parent.parent


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Pool:
    def __init__(self, url: str, namespace: str, database: str):
        self.url, self.namespace, self.database = url, namespace, database

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use(self.namespace, self.database)
        try:
            yield db
        finally:
            await db.close()


class DisposableSurreal:
    def __init__(self, root: Path, label: str, docker_image: str | None = None):
        self.root = root / label
        self.port = _port()
        self.url = f"ws://127.0.0.1:{self.port}"
        self.process: subprocess.Popen | None = None
        self.log = self.root.parent / f"{label}.log"
        self.docker_image = docker_image
        self.container_name = f"ace-f0-{label}-{uuid.uuid4().hex[:8]}"

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.docker_image:
            self.root.chmod(0o777)  # disposable mount must be writable by the image's non-root user
        handle = self.log.open("ab")
        if self.docker_image:
            command = [
                "docker",
                "run",
                "--rm",
                "--user",
                "0:0",
                "--name",
                self.container_name,
                "-p",
                f"127.0.0.1:{self.port}:8000",
                "-v",
                f"{self.root}:/data",
                self.docker_image,
                "start",
                "--no-banner",
                "--username",
                "root",
                "--password",
                "root",
                "--bind",
                "0.0.0.0:8000",
                "surrealkv:///data/db",
            ]
        else:
            binary = shutil.which("surreal")
            if not binary:
                raise RuntimeError("surreal binary is required for F0.1 verification")
            command = [
                binary,
                "start",
                "--no-banner",
                "--username",
                "root",
                "--password",
                "root",
                "--bind",
                f"127.0.0.1:{self.port}",
                f"surrealkv://{self.root}",
            ]
        self.process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"SurrealDB exited early; see {self.log}")
            try:
                db = AsyncSurreal(self.url)
                await db.connect()
                await db.signin({"username": "root", "password": "root"})
                await db.close()
                return
            except Exception:
                await asyncio.sleep(0.2)
        raise RuntimeError(f"SurrealDB did not become ready; see {self.log}")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        if self.docker_image:
            subprocess.run(
                ["docker", "stop", "-t", "5", self.container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
        self.process = None


async def apply_schema(pool: Pool, *, through: int) -> int:
    async with pool.connection() as db:
        current = await get_current_version(db)
        for path in sorted(SCHEMA_DIR.glob("v*.surql")):
            version = int(path.name.split("_", 1)[0][1:])
            if version <= current or version > through:
                continue
            for statement in _split_statements(path.read_text()):
                result = await db.query(statement)
                if isinstance(result, str):
                    # Historical migrations contain audited compatibility events.
                    from schema_apply import _is_known_legacy_compatibility_error

                    if not _is_known_legacy_compatibility_error(version, result):
                        raise RuntimeError(f"{path.name} failed: {result}")
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', value = $v WHERE key = 'schema_version'",
                {"v": str(version)},
            )
        return await get_current_version(db)


async def seed_legacy(pool: Pool) -> None:
    async with pool.connection() as db:
        for record_id in ("insight:a", "insight:b", "insight:c", "insight:d"):
            await db.query("UPSERT type::record($id) SET content = $content", {"id": record_id, "content": record_id})
        await db.query(
            "RELATE $source -> depends_on:f0_legacy -> $target "
            "SET source = 'cognify', confidence = 0.91, created_at = time::now()",
            {"source": parse_record_id("insight:a"), "target": parse_record_id("insight:b")},
        )


def _proposal(
    provider: str, predicate: str, subject: str = "insight:c", object_: str = "insight:d"
) -> RelationshipProposal:
    return RelationshipProposal(
        subject=subject,
        predicate=predicate,
        object=object_,
        provider=provider,
        model=f"fixture-{provider}",
        workflow="f0.1.concurrent.v1",
        evidence_refs=["observation:f0-concurrency"],
        proposal_confidence=0.9,
    )


async def snapshot(pool: Pool) -> dict[str, Any]:
    async with pool.connection() as db:
        assertions = parse_rows(
            await db.query(
                "SELECT id, subject, predicate, object, status, proposal_ids, evidence_refs, "
                "ontology_version, resolver_version, projection_eligible FROM relationship_assertion ORDER BY id"
            )
        )
        operational = parse_rows(
            await db.query(
                "SELECT id, in, out, predicate, assertion_id, ontology_version, resolver_version, projection_version "
                "FROM operational_relationship ORDER BY id"
            )
        )
        proposals = parse_rows(await db.query("SELECT id FROM relationship_proposal ORDER BY id"))

    def normalize(rows):
        return json.loads(json.dumps(rows, sort_keys=True, default=str))

    return {
        "assertions": normalize(assertions),
        "operational": normalize(operational),
        "proposal_ids": normalize(proposals),
    }


async def restart_api(url: str, namespace: str, database: str) -> dict[str, Any]:
    port = _port()
    env = os.environ | {
        "SURREAL_URL": url,
        "SURREAL_NS": namespace,
        "SURREAL_DB": database,
        "SURREAL_USER": "root",
        "SURREAL_PASS": "root",
        "LLM_API_KEY": "sk-test",
        "JWT_SECRET": "f0-disposable-only-secret-32-bytes",
        "REQUIRE_SUBSCRIPTION": "0",
        "ACE_DISABLE_EXTENSIONS": "1",
    }
    command = [sys.executable, "-m", "uvicorn", "core.engine.api.main:app", "--host", "127.0.0.1", "--port", str(port)]
    statuses = []
    for _ in range(2):
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("disposable API exited before health check")
                try:
                    response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    if response.status_code == 200:
                        statuses.append(response.status_code)
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("disposable API health check timed out")
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
    return {"starts": len(statuses), "health_statuses": statuses}


async def exercise_store(pool: Pool) -> dict[str, Any]:
    await seed_legacy(pool)
    dry_one = asdict(await migrate_legacy_edges(pool=pool, dry_run=True))
    dry_two = asdict(await migrate_legacy_edges(pool=pool, dry_run=True))
    apply_one = asdict(await migrate_legacy_edges(pool=pool, dry_run=False))
    first = await snapshot(pool)
    apply_two = asdict(await migrate_legacy_edges(pool=pool, dry_run=False))
    second = await snapshot(pool)
    if dry_one != dry_two or first != second:
        raise AssertionError("legacy migration is not byte-idempotent")

    equivalent = [_proposal("api", "requires"), _proposal("local", "enables", "insight:d", "insight:c")]
    await asyncio.gather(*(persist_resolution([p], pool=pool) for p in equivalent))
    equivalent_snapshot = await snapshot(pool)
    matching = [
        a for a in equivalent_snapshot["assertions"] if a["predicate"] == "depends_on" and a["subject"] == "insight:c"
    ]
    if len(matching) != 1 or len(matching[0]["proposal_ids"]) != 2:
        raise AssertionError(
            "concurrent equivalent proposals did not converge with both provenance events: "
            + json.dumps(equivalent_snapshot, sort_keys=True)
        )

    conflicts = [
        _proposal("api", "improves", "insight:a", "insight:d"),
        _proposal("local", "breaks", "insight:a", "insight:d"),
    ]
    await asyncio.gather(*(persist_resolution([p], pool=pool) for p in conflicts))
    conflict_snapshot = await snapshot(pool)
    pair = [a for a in conflict_snapshot["assertions"] if a["subject"] == "insight:a" and a["object"] == "insight:d"]
    if {a["status"] for a in pair} != {"contested"} or any(a["projection_eligible"] for a in pair):
        raise AssertionError("concurrent conflict did not become non-operational contested state")
    return {
        "migration": {
            "dry_run_1": dry_one,
            "dry_run_2": dry_two,
            "apply_1": apply_one,
            "apply_2": apply_two,
            "byte_idempotent": first == second,
        },
        "equivalent_assertion_id": matching[0]["id"],
        "equivalent_proposal_ids": matching[0]["proposal_ids"],
        "conflict_assertion_ids": sorted(a["id"] for a in pair),
        "before_restart": conflict_snapshot,
    }


async def verify(keep: bool = False, docker_image: str | None = None) -> dict[str, Any]:
    temp = Path(tempfile.mkdtemp(prefix="ace-f0-closeout-", dir="/tmp"))
    if docker_image:
        temp.chmod(0o777)
    fresh = DisposableSurreal(temp, "fresh", docker_image=docker_image)
    upgrade = DisposableSurreal(temp, "upgrade", docker_image=docker_image)
    try:
        await fresh.start()
        fresh_pool = Pool(fresh.url, "ace_f0", "fresh")
        if await apply_schema(fresh_pool, through=142) != 142:
            raise AssertionError("fresh schema did not reach v142")
        fresh_result = await exercise_store(fresh_pool)

        await upgrade.start()
        upgrade_pool = Pool(upgrade.url, "ace_f0", "upgrade")
        if await apply_schema(upgrade_pool, through=141) != 141:
            raise AssertionError("upgrade baseline did not reach v141")
        await seed_legacy(upgrade_pool)
        if await apply_schema(upgrade_pool, through=142) != 142:
            raise AssertionError("v141 upgrade did not reach v142")
        upgrade_result = await exercise_store_without_seed(upgrade_pool)
        if fresh_result["before_restart"] != upgrade_result["before_restart"]:
            raise AssertionError("fresh and v141-upgrade paths produced different canonical bytes")

        before = await snapshot(fresh_pool)
        await fresh.restart()
        fresh_pool = Pool(fresh.url, "ace_f0", "fresh")
        persisted = await snapshot(fresh_pool)
        async with fresh_pool.connection() as db:
            await rebuild_projection(db=db)
        rebuilt = await snapshot(fresh_pool)
        if before != persisted or persisted != rebuilt:
            raise AssertionError("restart or projection rebuild changed canonical bytes")
        api = await restart_api(fresh.url, "ace_f0", "fresh")
        after_api_restart = await snapshot(fresh_pool)
        if rebuilt != after_api_restart:
            raise AssertionError("API restart changed persisted assertion or projection bytes")
        return {
            "status": "passed",
            "surreal_version": docker_image
            or subprocess.check_output([shutil.which("surreal"), "version"], text=True).strip(),
            "fresh_schema": 142,
            "upgrade_schema": {"from": 141, "to": 142},
            "fresh": {k: v for k, v in fresh_result.items() if k != "before_restart"},
            "upgrade": {k: v for k, v in upgrade_result.items() if k != "before_restart"},
            "restart_byte_identical": before == persisted,
            "rebuild_byte_identical": persisted == rebuilt,
            "fresh_upgrade_byte_identical": fresh_result["before_restart"] == upgrade_result["before_restart"],
            "api_restart_byte_identical": rebuilt == after_api_restart,
            "api_restart": api,
            "artifact_root": str(temp) if keep else None,
        }
    finally:
        await fresh.stop()
        await upgrade.stop()
        if not keep:
            shutil.rmtree(temp, ignore_errors=True)


async def exercise_store_without_seed(pool: Pool) -> dict[str, Any]:
    # Upgrade fixture was inserted before v142; exercise the same closeout without duplicating it.
    dry_one = asdict(await migrate_legacy_edges(pool=pool, dry_run=True))
    dry_two = asdict(await migrate_legacy_edges(pool=pool, dry_run=True))
    await migrate_legacy_edges(pool=pool, dry_run=False)
    first = await snapshot(pool)
    await migrate_legacy_edges(pool=pool, dry_run=False)
    second = await snapshot(pool)
    if dry_one != dry_two or first != second:
        raise AssertionError("upgrade migration is not byte-idempotent")
    equivalent = [_proposal("api", "requires"), _proposal("local", "enables", "insight:d", "insight:c")]
    await asyncio.gather(*(persist_resolution([p], pool=pool) for p in equivalent))
    conflicts = [
        _proposal("api", "improves", "insight:a", "insight:d"),
        _proposal("local", "breaks", "insight:a", "insight:d"),
    ]
    await asyncio.gather(*(persist_resolution([p], pool=pool) for p in conflicts))
    final = await snapshot(pool)
    matching = [a for a in final["assertions"] if a["predicate"] == "depends_on" and a["subject"] == "insight:c"]
    pair = [a for a in final["assertions"] if a["subject"] == "insight:a" and a["object"] == "insight:d"]
    if len(matching) != 1 or len(matching[0]["proposal_ids"]) != 2 or {a["status"] for a in pair} != {"contested"}:
        raise AssertionError("upgrade concurrency semantics failed")
    return {
        "migration": {"dry_run_1": dry_one, "dry_run_2": dry_two, "byte_idempotent": first == second},
        "equivalent_assertion_id": matching[0]["id"],
        "equivalent_proposal_ids": matching[0]["proposal_ids"],
        "conflict_assertion_ids": sorted(a["id"] for a in pair),
        "before_restart": final,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep disposable stores for debugging")
    parser.add_argument("--docker-image", help="Run disposable servers from this pinned image")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(verify(keep=args.keep, docker_image=args.docker_image)), indent=2, sort_keys=True, default=str
        )
    )
