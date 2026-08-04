#!/usr/bin/env python3
"""Run the frozen K1-K3 State Engine readiness audit on disposable local infrastructure."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from surrealdb import AsyncSurreal

from core.engine.core.db import parse_one
from core.engine.grounded_state.belief_contracts import BoundedEvidencePackV1, ReviewAuthority
from core.engine.grounded_state.contracts import RolloutBranchKind, canonical_hash
from core.engine.grounded_state.promotion import PromotionService
from core.engine.grounded_state.promotion_contracts import PromotionReceiptV1
from core.engine.grounded_state.rollout_contracts import (
    ReasoningEvidencePackV1,
    RolloutOutcomeObservationV1,
)
from core.engine.grounded_state.rollouts import ConsequenceRolloutService
from evaluations.state_engine_readiness import (
    compile_readiness_result,
    latency_summary,
    load_readiness_config,
    measure_k2,
    readiness_config_hash,
    revalidate_k1,
    validate_readiness_result,
)
from scripts.schema_apply import _REQUIRED_TABLES, get_current_version, validate_schema

ROOT = Path(__file__).parents[1]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_k1_k3_readiness_v1.json"


class SingleConnectionPool:
    def __init__(self, connection) -> None:
        self.connection_value = connection

    @asynccontextmanager
    async def connection(self):
        yield self.connection_value


async def _connect(url: str, namespace: str, database: str) -> tuple[Any, SingleConnectionPool]:
    db = AsyncSurreal(url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use(namespace, database)
    return db, SingleConnectionPool(db)


async def _reconcile_retained_schema_receipt(
    *,
    url: str,
    namespace: str,
    database: str,
    expected_version: int,
) -> dict[str, Any]:
    """Validate TP8's retained schema objects before repairing its stale version receipt."""

    db, _ = await _connect(url, namespace, database)
    try:
        before = await get_current_version(db)
        code_head = max(
            int(match.group(1))
            for path in (ROOT / "core/schema").glob("v*.surql")
            if (match := re.match(r"v(\d+)", path.name))
        )
        if code_head != expected_version:
            raise RuntimeError(
                f"frozen readiness target expects schema v{expected_version}, but code head is v{code_head}"
            )

        required_tables = set(_REQUIRED_TABLES)
        for version in (142, 163, 164, 165, 166, 167, 168):
            paths = tuple((ROOT / "core/schema").glob(f"v{version:03d}_*.surql"))
            if len(paths) != 1:
                raise RuntimeError(f"expected one schema source for v{version}, found {len(paths)}")
            required_tables.update(
                match.group(1)
                for match in re.finditer(
                    r"DEFINE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS|\s+OVERWRITE)?\s+([A-Za-z0-9_]+)",
                    paths[0].read_text(encoding="utf-8"),
                    re.IGNORECASE,
                )
            )

        raw_info = await db.query("INFO FOR DB")
        info = raw_info[0] if isinstance(raw_info, list) and raw_info else raw_info
        if isinstance(info, list):
            info = info[0] if info else {}
        available_tables = set((info or {}).get("tables", {})) if isinstance(info, dict) else set()
        missing_before = sorted(required_tables - available_tables)
        repairable = {"discipline", "framework", "reasoning_event"}
        unexpected_missing = sorted(set(missing_before) - repairable)
        if unexpected_missing:
            raise RuntimeError(f"retained TP8 store is missing required schema tables: {', '.join(unexpected_missing)}")

        repair_statements = {
            "discipline": (
                "DEFINE TABLE IF NOT EXISTS discipline SCHEMAFULL",
                "DEFINE FIELD IF NOT EXISTS slug ON TABLE discipline TYPE string",
                "DEFINE FIELD IF NOT EXISTS name ON TABLE discipline TYPE string",
                "DEFINE FIELD IF NOT EXISTS description ON TABLE discipline TYPE string DEFAULT ''",
                "DEFINE FIELD IF NOT EXISTS created_at ON TABLE discipline TYPE datetime DEFAULT time::now()",
                "DEFINE INDEX IF NOT EXISTS idx_disc_slug ON TABLE discipline FIELDS slug UNIQUE",
            ),
            "framework": (
                "DEFINE TABLE IF NOT EXISTS framework SCHEMAFULL",
                "DEFINE FIELD IF NOT EXISTS product ON framework TYPE option<record<product>>",
                "DEFINE FIELD IF NOT EXISTS slug ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS name ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS family ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS tier ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS description ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS system_prompt ON framework TYPE string",
                "DEFINE FIELD IF NOT EXISTS activation_signals ON framework TYPE array",
                "DEFINE FIELD IF NOT EXISTS archetype_affinity ON framework TYPE object FLEXIBLE",
                "DEFINE FIELD IF NOT EXISTS mode_affinity ON framework TYPE object FLEXIBLE",
                "DEFINE FIELD IF NOT EXISTS composability ON framework TYPE object FLEXIBLE",
                "DEFINE FIELD IF NOT EXISTS created_at ON framework TYPE datetime DEFAULT time::now()",
                "DEFINE INDEX IF NOT EXISTS idx_fw_slug ON framework FIELDS product, slug UNIQUE",
                "DEFINE INDEX IF NOT EXISTS idx_fw_family ON framework FIELDS product, family",
            ),
            "reasoning_event": (
                "DEFINE TABLE IF NOT EXISTS reasoning_event SCHEMALESS",
                "DEFINE FIELD IF NOT EXISTS run ON reasoning_event TYPE record<reasoning_run>",
                "DEFINE FIELD IF NOT EXISTS seq ON reasoning_event TYPE int",
                "DEFINE FIELD IF NOT EXISTS event_type ON reasoning_event TYPE string",
                "DEFINE FIELD IF NOT EXISTS payload ON reasoning_event TYPE option<object>",
                "DEFINE FIELD IF NOT EXISTS created_at ON reasoning_event TYPE datetime DEFAULT time::now()",
                "DEFINE INDEX IF NOT EXISTS idx_re_run_seq ON reasoning_event FIELDS run, seq",
            ),
        }
        materialized_tables: list[str] = []
        for table in missing_before:
            for statement in repair_statements[table]:
                result = await db.query(statement)
                if isinstance(result, str):
                    raise RuntimeError(f"failed to materialize retained runtime table {table}: {result}")
            materialized_tables.append(table)

        raw_info = await db.query("INFO FOR DB")
        info = raw_info[0] if isinstance(raw_info, list) and raw_info else raw_info
        if isinstance(info, list):
            info = info[0] if info else {}
        available_tables = set((info or {}).get("tables", {})) if isinstance(info, dict) else set()
        missing_after = sorted(required_tables - available_tables)
        if missing_after:
            raise RuntimeError(
                f"retained TP8 schema completion left required tables missing: {', '.join(missing_after)}"
            )

        reconciled = before != expected_version
        if reconciled:
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', value = $version WHERE key = 'schema_version'",
                {"version": str(expected_version)},
            )
        await validate_schema(db, expected_version)
        after = await get_current_version(db)
        return {
            "status": "passed",
            "schema_version_before": before,
            "schema_version_after": after,
            "schema_head": code_head,
            "required_tables": len(required_tables),
            "available_tables": len(available_tables),
            "missing_tables_before": missing_before,
            "materialized_tables": materialized_tables,
            "missing_tables_after": missing_after,
            "receipt_reconciled": reconciled,
            "reason": (
                "TP8 retained the State Engine v168 planes but omitted three base-runtime tables and "
                "did not advance the production config_entry receipt; K3 completed only those additive "
                "runtime definitions, verified the required objects, and advanced the receipt on the "
                "disposable clone."
                if reconciled
                else "The disposable clone already carried the expected production schema receipt."
            ),
        }
    finally:
        await db.close()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 30) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited before port {port} was ready: {process.returncode}")
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return time.perf_counter() - started
        except OSError:
            await asyncio.sleep(0.05)
    raise TimeoutError(f"port {port} was not ready within {timeout}s")


async def _wait_http(url: str, process: subprocess.Popen, timeout: float = 45) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    async with httpx.AsyncClient(timeout=2) as client:
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"process exited before {url} was ready: {process.returncode}")
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return time.perf_counter() - started
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise TimeoutError(f"{url} was not ready within {timeout}s")


async def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, 15)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait, 5)


class ProcessSet:
    def __init__(
        self,
        *,
        store: Path,
        surreal: str,
        raw_dir: Path,
        namespace: str,
        database: str,
    ) -> None:
        self.store = store
        self.surreal = surreal
        self.raw_dir = raw_dir
        self.namespace = namespace
        self.database = database
        self.db_port = _free_port()
        self.api_port = _free_port()
        self.worker_port = _free_port()
        self.db: subprocess.Popen | None = None
        self.api: subprocess.Popen | None = None
        self.worker: subprocess.Popen | None = None
        self._handles: list[Any] = []
        self.secret = "k1-k3-readiness-disposable-jwt-secret-at-least-32-bytes"

    @property
    def db_url(self) -> str:
        return f"ws://127.0.0.1:{self.db_port}"

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    def token(self, product_id: str) -> str:
        return jwt.encode(
            {
                "sub": "user:k1-k3-readiness",
                "product": product_id,
                "feature_flags": ["state-engine-tp6", "state-engine-tp7"],
                "authorities": ["state-engine-promotion-review"],
                "exp": datetime.now(UTC) + timedelta(hours=2),
            },
            self.secret,
            algorithm="HS256",
        )

    def _log(self, name: str):
        path = self.raw_dir / name
        handle = path.open("ab")
        self._handles.append(handle)
        return handle

    def env(self, product_id: str) -> dict[str, str]:
        return os.environ | {
            "SURREAL_URL": self.db_url,
            "SURREAL_NS": self.namespace,
            "SURREAL_DB": self.database,
            "SURREAL_USER": "root",
            "SURREAL_PASS": "root",
            "JWT_SECRET": self.secret,
            "API_KEY": "",
            "LLM_API_KEY": "sk-test-placeholder",
            "REQUIRE_SUBSCRIPTION": "1",
            "ACE_DISABLE_EXTENSIONS": "1",
            "ACE_PRODUCT_ID": product_id,
            "ACE_WORKER_HOST": "127.0.0.1",
            "ACE_WORKER_PORT": str(self.worker_port),
            "ACE_URL": self.api_url,
            "ACE_TOKEN": self.token(product_id),
            "ENGINE_LOG_LEVEL": "WARNING",
        }

    async def start_db(self, label: str) -> float:
        self.db = subprocess.Popen(
            [
                self.surreal,
                "start",
                "--no-banner",
                "--username",
                "root",
                "--password",
                "root",
                "--bind",
                f"127.0.0.1:{self.db_port}",
                f"surrealkv://{self.store}",
            ],
            cwd=ROOT,
            stdout=self._log(f"{label}-database.log"),
            stderr=subprocess.STDOUT,
        )
        return await _wait_port(self.db_port, self.db)

    async def start_runtime(self, *, product_id: str, label: str) -> dict[str, float | int]:
        env = self.env(product_id)
        self.api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "evaluations.state_engine_readiness_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.api_port),
            ],
            cwd=ROOT,
            env=env,
            stdout=self._log(f"{label}-api.log"),
            stderr=subprocess.STDOUT,
        )
        api_seconds = await _wait_http(f"{self.api_url}/health/live", self.api)
        self.worker = subprocess.Popen(
            [sys.executable, str(ROOT / "core/engine/worker/start.py")],
            cwd=ROOT,
            env=env,
            stdout=self._log(f"{label}-worker.log"),
            stderr=subprocess.STDOUT,
        )
        worker_seconds = await _wait_http(f"http://127.0.0.1:{self.worker_port}/health", self.worker)
        return {
            "api_pid": self.api.pid,
            "worker_pid": self.worker.pid,
            "api_start_seconds": round(api_seconds, 6),
            "worker_start_seconds": round(worker_seconds, 6),
        }

    async def stop_runtime(self) -> None:
        await _stop(self.worker)
        await _stop(self.api)
        self.worker = None
        self.api = None

    async def stop_db(self) -> None:
        await _stop(self.db)
        self.db = None

    async def close(self) -> None:
        await self.stop_runtime()
        await self.stop_db()
        for handle in self._handles:
            handle.close()
        self._handles.clear()


async def _terminal(client: httpx.AsyncClient, task: dict[str, Any]) -> dict[str, Any]:
    if task.get("status") in {"completed", "failed", "degraded"}:
        return task
    for _ in range(100):
        response = await client.get(f"/tasks/{task['id']}")
        response.raise_for_status()
        task = response.json()
        if task.get("status") in {"completed", "failed", "degraded"}:
            return task
        await asyncio.sleep(0.05)
    return task


async def _post_task(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.post(path, json=payload)
    response.raise_for_status()
    task = await _terminal(client, response.json())
    return task, (time.perf_counter() - started) * 1000


def _decision(kind: str, evidence_refs: list[str]) -> dict[str, Any]:
    if kind == "control":
        selected = "Keep the no-action monitoring baseline."
        alternatives = ["Use the bounded action branch"]
    elif kind == "correction":
        selected = "Monitor active and standby cooling circuits."
        alternatives = ["Monitor only the active circuit"]
    else:
        selected = "Use the bounded action branch and monitor the predicted cooling failure."
        alternatives = ["Keep the no-action baseline"]
    return {
        "selected_option": selected,
        "scope": "K3 repeated fresh-process readiness journey",
        "assumptions": [],
        "alternatives": alternatives,
        "reconsideration_conditions": ["The frozen later outcome contradicts the simulation"],
        "evidence_refs": evidence_refs,
        "rationale": "Frozen provider-free K3 readiness decision.",
        "decision_type": "direction",
    }


def _evidence_envelope(
    *,
    repetition: int,
    coordinates: dict[str, Any],
    mode: str,
    control_task_id: str | None = None,
    correction_id: str | None = None,
    prior_receipt_id: str | None = None,
) -> dict[str, Any]:
    suffix = "correction" if correction_id else mode
    as_of = datetime.fromisoformat(coordinates["as_of"])
    parameters: dict[str, Any] = {
        "state_engine_mode": mode,
        "context_source": "projection",
        "as_of": coordinates["as_of"],
        "starting_projection_id": coordinates["projection_id"],
        "structured_decision": _decision(
            "correction" if correction_id else mode,
            [correction_id] if correction_id else [coordinates["evidence_pack_id"]],
        ),
    }
    if control_task_id:
        parameters["matched_control_task_id"] = control_task_id
    if mode == "rollout":
        parameters["rollout"] = {
            "transition_revision_ids": [coordinates["revision_id"]],
            "horizon": (as_of + timedelta(days=7)).isoformat(),
            "branches": [
                {
                    "branch_id": f"branch:k3-{repetition:02d}-{suffix}-action",
                    "kind": "action",
                    "action": "Disconnect active cooling.",
                    "transition_hypothesis_ids": [coordinates["hypothesis_id"]],
                },
                {
                    "branch_id": f"branch:k3-{repetition:02d}-{suffix}-no-action",
                    "kind": "no_action",
                },
            ],
        }
        parameters["promotion_material"] = {
            "target_kind": "correction" if correction_id else "durable_conclusion",
            "origin_meaning": "human_correction" if correction_id else "grounded_reasoning_conclusion",
            "memory_meaning": "correction" if correction_id else "durable_conclusion",
            "content": (
                f"K3 repetition {repetition}: monitor active and standby cooling circuits."
                if correction_id
                else f"K3 repetition {repetition}: a disconnected active cooling circuit requires explicit monitoring."
            ),
            "domain_path": "engineering",
            "tags": ["engineering", "cooling", f"k3-{repetition:02d}"],
        }
        if correction_id:
            parameters["correction_observation_id"] = correction_id
            parameters["prior_promotion_receipt_ids"] = [prior_receipt_id]
    return {
        "contract_version": "extension-invocation-v1",
        "extension_id": "product",
        "extension_version": "0.2.0",
        "action": "evidence-query",
        "workspace_id": f"workspace:k3-{repetition:02d}",
        "question": "What happens if the cooling circuit is disconnected?",
        "references": [
            {
                "namespace": "product",
                "kind": "evidence_query",
                "id": f"query:k3-{repetition:02d}-{suffix}",
                "version": "1",
            }
        ],
        "parameters": parameters,
        "correlation_id": f"invocation:k3-{repetition:02d}-{suffix}",
        "idempotency_key": f"k3-{repetition:02d}-{suffix}-v1",
        "wait_seconds": 2,
    }


def _review_envelope(*, repetition: int, proposal_id: str, suffix: str) -> dict[str, Any]:
    reviewed_at = datetime(2026, 8, 5, tzinfo=UTC) + timedelta(
        minutes=repetition,
        seconds=30 if suffix == "correction" else 0,
    )
    return {
        "contract_version": "extension-invocation-v1",
        "extension_id": "product",
        "extension_version": "0.2.0",
        "action": "promotion-review",
        "workspace_id": f"workspace:k3-{repetition:02d}",
        "question": "Apply the authenticated frozen K3 promotion disposition.",
        "references": [
            {
                "namespace": "product",
                "kind": "promotion_proposal",
                "id": proposal_id,
                "version": "ace.grounded-state.promotion-proposal/v1",
            }
        ],
        "parameters": {
            "disposition": "accepted",
            "rationale": "Authenticated frozen K3 readiness acceptance.",
            "reviewed_at": reviewed_at.isoformat(),
        },
        "correlation_id": f"invocation:k3-{repetition:02d}-{suffix}-review",
        "idempotency_key": f"k3-{repetition:02d}-{suffix}-review-v1",
        "wait_seconds": 2,
    }


async def _receipt_for_proposal(pool, *, product_id: str, proposal_id: str) -> PromotionReceiptV1:
    receipts = await PromotionService(pool).store.list_records(PromotionReceiptV1, product_id=product_id)
    matches = [item for item in receipts if item.proposal_id == proposal_id]
    if len(matches) != 1:
        raise RuntimeError("promotion review did not produce exactly one receipt")
    return matches[0]


async def _reconcile_frozen_outcome(
    pool,
    *,
    product_id: str,
    rollout_id: str,
    repetition: int,
) -> dict[str, Any]:
    service = ConsequenceRolloutService(pool)
    rollout = await service.replay_rollout(rollout_id, product_id=product_id)
    action = next(item for item in rollout.execution_receipts if item.branch_kind is RolloutBranchKind.ACTION)
    predicted = action.consequences[0].falsifiable_outcome
    context_pack = await service.rollout_store.require(
        ReasoningEvidencePackV1,
        rollout.context_pack_id,
        product_id=product_id,
    )
    source_pack = await service.belief_store.require(
        BoundedEvidencePackV1,
        str(context_pack.evidence_pack.pack_id),
        product_id=product_id,
    )
    if source_pack.pack_hash != context_pack.evidence_pack.pack_hash:
        raise RuntimeError("rollout context pack does not bind the exact persisted evidence pack")
    observed_at = predicted.latest_at
    observed_pack = BoundedEvidencePackV1.model_validate(
        {
            **source_pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
            "as_of": observed_at,
            "query_hash": canonical_hash(f"k3-frozen-later-outcome:{repetition}"),
            "candidate_receipt_id": f"candidate_receipt:k3_later_{repetition:02d}",
            "candidate_receipt_hash": canonical_hash(f"k3-frozen-later-receipt:{repetition}"),
        }
    )
    await service.belief_store.persist(observed_pack)
    observation = RolloutOutcomeObservationV1(
        product_id=product_id,
        rollout_revision_id=str(rollout.rollout_revision_id),
        rollout_revision_hash=str(rollout.rollout_revision_hash),
        predicted_outcome_id=str(predicted.outcome_id),
        branch_id=action.branch_id,
        observed_at=observed_at,
        observed_assignment=predicted.expected_assignment,
        evidence_pack_id=str(observed_pack.pack_id),
        evidence_pack_hash=str(observed_pack.pack_hash),
        evidence_refs=(observed_pack.items[0].endpoint.record_id,),
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        observer_ref="policy:k1-k3-readiness-frozen-outcome/v1",
        rationale="Predeclared synthetic later outcome for the K3 readiness gate.",
    )
    reconciliation = await service.reconcile_and_persist(
        observation,
        reconciled_at=observed_at + timedelta(seconds=1),
    )
    replayed = await service.replay_rollout(rollout_id, product_id=product_id)
    return {
        "observation_id": str(observation.observation_id),
        "observation_hash": str(observation.observation_hash),
        "reconciliation_id": str(reconciliation.receipt_id),
        "reconciliation_hash": str(reconciliation.receipt_hash),
        "disposition": reconciliation.disposition.value,
        "score": reconciliation.score,
        "original_rollout_preserved": replayed.rollout_revision_hash == rollout.rollout_revision_hash,
        "action_branch_present": any(
            item.branch_kind is RolloutBranchKind.ACTION for item in rollout.execution_receipts
        ),
        "no_action_branch_present": any(
            item.branch_kind is RolloutBranchKind.NO_ACTION for item in rollout.execution_receipts
        ),
        "record_meanings": sorted(
            {
                consequence.record_meaning
                for execution in rollout.execution_receipts
                for consequence in execution.consequences
            }
        ),
    }


async def _run_client(
    processes: ProcessSet,
    *,
    product_id: str,
    repetition: int,
    command: str,
    output: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    completed = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-m",
            "evaluations.state_engine_readiness_client",
            command,
            "--repetition",
            str(repetition),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=processes.env(product_id),
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"thin client failed: {completed.stderr[-500:]}")
    result = json.loads(output.read_text(encoding="utf-8"))
    result["process_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def _provider_usage(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    calls = sum(int((task.get("model_calls") or {}).get("actual") or 0) for task in tasks)
    retries = sum(int((task.get("model_calls") or {}).get("retry_count") or 0) for task in tasks)
    input_tokens = sum(int((task.get("token_usage") or {}).get("input_tokens") or 0) for task in tasks)
    output_tokens = sum(int((task.get("token_usage") or {}).get("output_tokens") or 0) for task in tasks)
    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "retries": retries,
        "cost_usd": 0.0,
        "billing_semantics": "deterministic_no_model_call",
    }


async def run_k3(args, config: dict[str, Any]) -> dict[str, Any]:
    k2 = json.loads(Path(args.k2_result).read_text(encoding="utf-8"))
    by_repetition = {
        item["repetition"]: item
        for item in k2["case_results"]
        if item.get("domain") == "mechanistic_systems" and item.get("matched")
    }
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processes = ProcessSet(
        store=Path(args.store),
        surreal=args.surreal_bin,
        raw_dir=raw_dir,
        namespace=args.namespace,
        database=args.database,
    )
    repetitions: list[dict[str, Any]] = []
    task_latencies: list[float] = []
    promotion_latencies: list[float] = []
    retrieval_latencies: list[float] = []
    all_tasks: list[dict[str, Any]] = []
    failures: list[str] = []

    try:
        await processes.start_db("initial")
        schema_receipt = await _reconcile_retained_schema_receipt(
            url=processes.db_url,
            namespace=args.namespace,
            database=args.database,
            expected_version=config["k1"]["schema_head_expected"],
        )
        for repetition in range(1, config["k3"]["repetitions"] + 1):
            product_id = by_repetition[repetition]["product_id"]
            coordinates = {**by_repetition[repetition]["provenance"], **by_repetition[repetition]["revision"]}
            entry: dict[str, Any] = {
                "repetition": repetition,
                "product_id": product_id,
                "coordinates": coordinates,
                "failures": [],
                "retries": 0,
                "degraded_states": [],
            }
            try:
                entry["initial_processes"] = await processes.start_runtime(
                    product_id=product_id,
                    label=f"repetition-{repetition:02d}-initial",
                )
                headers = {"Authorization": f"Bearer {processes.token(product_id)}"}
                async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
                    control, control_ms = await _post_task(
                        client,
                        "/extension-invocations",
                        _evidence_envelope(repetition=repetition, coordinates=coordinates, mode="control"),
                    )
                    rollout, rollout_ms = await _post_task(
                        client,
                        "/extension-invocations",
                        _evidence_envelope(
                            repetition=repetition,
                            coordinates=coordinates,
                            mode="rollout",
                            control_task_id=control["id"],
                        ),
                    )
                    runtime = rollout.get("state_engine_runtime") or {}
                    review, review_ms = await _post_task(
                        client,
                        "/extension-invocations",
                        _review_envelope(
                            repetition=repetition,
                            proposal_id=runtime["promotion_proposal_id"],
                            suffix="initial",
                        ),
                    )
                entry["initial_tasks"] = {
                    "control": control,
                    "rollout": rollout,
                    "review": review,
                }
                entry["latencies_ms"] = {
                    "control_task": round(control_ms, 3),
                    "rollout_task": round(rollout_ms, 3),
                    "initial_promotion": round(review_ms, 3),
                }
                task_latencies.extend((control_ms, rollout_ms))
                promotion_latencies.append(review_ms)
                all_tasks.extend((control, rollout, review))

                db, pool = await _connect(processes.db_url, args.namespace, args.database)
                try:
                    initial_receipt = await _receipt_for_proposal(
                        pool,
                        product_id=product_id,
                        proposal_id=runtime["promotion_proposal_id"],
                    )
                    entry["initial_promotion"] = initial_receipt.model_dump(mode="json")
                    entry["reconciliation"] = await _reconcile_frozen_outcome(
                        pool,
                        product_id=product_id,
                        rollout_id=runtime["rollout_revision_id"],
                        repetition=repetition,
                    )
                finally:
                    await db.close()

                await processes.stop_runtime()
                await processes.stop_db()
                restart_started = time.perf_counter()
                await processes.start_db(f"repetition-{repetition:02d}-restart-1")
                restarted = await processes.start_runtime(
                    product_id=product_id,
                    label=f"repetition-{repetition:02d}-restart-1",
                )
                restarted["total_restart_seconds"] = round(time.perf_counter() - restart_started, 6)
                entry["restart_before_later_use"] = restarted

                later_output = raw_dir / f"k3-repetition-{repetition:02d}-thin-later-use.json"
                later = await _run_client(
                    processes,
                    product_id=product_id,
                    repetition=repetition,
                    command="later-use",
                    output=later_output,
                )
                entry["later_use"] = later
                retrieval_latencies.append(float(later["retrieval_latency_ms"]))
                task_latencies.append(float(later["task_latency_ms"]))
                all_tasks.append(later["task"])
                correction_id = later["correction"]["correction"]["correction_id"]

                async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
                    persisted_rollout = await client.get(f"/tasks/{rollout['id']}")
                    persisted_rollout.raise_for_status()
                    correction_task, correction_ms = await _post_task(
                        client,
                        "/extension-invocations",
                        _evidence_envelope(
                            repetition=repetition,
                            coordinates=coordinates,
                            mode="rollout",
                            control_task_id=control["id"],
                            correction_id=correction_id,
                            prior_receipt_id=str(initial_receipt.receipt_id),
                        ),
                    )
                    correction_runtime = correction_task.get("state_engine_runtime") or {}
                    correction_review, correction_review_ms = await _post_task(
                        client,
                        "/extension-invocations",
                        _review_envelope(
                            repetition=repetition,
                            proposal_id=correction_runtime["promotion_proposal_id"],
                            suffix="correction",
                        ),
                    )
                entry["durable_task_identity"] = {
                    "task_id": rollout["id"],
                    "same_after_restart": persisted_rollout.json()["id"] == rollout["id"],
                    "status_after_restart": persisted_rollout.json()["status"],
                }
                entry["correction_tasks"] = {
                    "rollout": correction_task,
                    "review": correction_review,
                }
                entry["latencies_ms"].update(
                    {
                        "correction_task": round(correction_ms, 3),
                        "correction_promotion": round(correction_review_ms, 3),
                    }
                )
                task_latencies.append(correction_ms)
                promotion_latencies.append(correction_review_ms)
                all_tasks.extend((correction_task, correction_review))

                db, pool = await _connect(processes.db_url, args.namespace, args.database)
                try:
                    correction_receipt = await _receipt_for_proposal(
                        pool,
                        product_id=product_id,
                        proposal_id=correction_runtime["promotion_proposal_id"],
                    )
                    authoritative = await PromotionService(pool).retrieve(
                        product_id=product_id,
                        domain_path="engineering",
                    )
                    foreign = await PromotionService(pool).retrieve(
                        product_id=f"product:k123-k3-foreign-{repetition:02d}",
                        domain_path="engineering",
                    )
                    rollout_service = ConsequenceRolloutService(pool)
                    foreign_rollout = await rollout_service.rollout_store.load(
                        type(
                            await rollout_service.replay_rollout(
                                correction_runtime["rollout_revision_id"],
                                product_id=product_id,
                            )
                        ),
                        correction_runtime["rollout_revision_id"],
                        product_id=f"product:k123-k3-foreign-{repetition:02d}",
                    )
                    async with pool.connection() as connection:
                        simulated_observation = parse_one(
                            await connection.query(
                                "SELECT count() AS count FROM observation WHERE id = <record>$rollout GROUP ALL",
                                {"rollout": correction_runtime["rollout_revision_id"]},
                            )
                        )
                    entry["correction"] = {
                        "correction_observation_id": correction_id,
                        "receipt": correction_receipt.model_dump(mode="json"),
                        "supersedes_initial": str(initial_receipt.receipt_id)
                        in correction_receipt.supersedes_receipt_ids,
                        "authoritative_memory_ids": [item.memory_id for item in authoritative],
                        "authoritative_contents": [item.content for item in authoritative],
                    }
                    entry["product_isolation"] = {
                        "foreign_promoted_memories": len(foreign),
                        "foreign_rollout_visible": foreign_rollout is not None,
                    }
                    entry["simulation_separation"] = {
                        "simulated_as_observation_rows": int((simulated_observation or {}).get("count", 0)),
                        "rollout_record_meanings": entry["reconciliation"]["record_meanings"],
                    }
                finally:
                    await db.close()

                await processes.stop_runtime()
                await processes.stop_db()
                restart_started = time.perf_counter()
                await processes.start_db(f"repetition-{repetition:02d}-restart-2")
                restarted = await processes.start_runtime(
                    product_id=product_id,
                    label=f"repetition-{repetition:02d}-restart-2",
                )
                restarted["total_restart_seconds"] = round(time.perf_counter() - restart_started, 6)
                entry["restart_after_correction"] = restarted
                post_output = raw_dir / f"k3-repetition-{repetition:02d}-thin-post-correction.json"
                post = await _run_client(
                    processes,
                    product_id=product_id,
                    repetition=repetition,
                    command="post-correction",
                    output=post_output,
                )
                entry["post_correction"] = post
                retrieval_latencies.append(float(post["retrieval_latency_ms"]))
                task_latencies.append(float(post["task_latency_ms"]))
                all_tasks.append(post["task"])

                later_receipt = later["task"].get("intelligence_use_receipt") or {}
                post_receipt = post["task"].get("intelligence_use_receipt") or {}
                entry["material_later_use"] = {
                    "before_correction": later_receipt.get("material_intelligence_ids") or [],
                    "after_correction": post_receipt.get("material_intelligence_ids") or [],
                    "beneficial_impact_supported": bool(
                        (later_receipt.get("impact") or {}).get("beneficial_impact_supported")
                        or (post_receipt.get("impact") or {}).get("beneficial_impact_supported")
                    ),
                }
                task_statuses = [
                    task.get("status")
                    for task in (
                        *entry["initial_tasks"].values(),
                        later["task"],
                        *entry["correction_tasks"].values(),
                        post["task"],
                    )
                ]
                entry["degraded_states"] = [status for status in task_statuses if status != "completed"]
                entry["provider_usage"] = _provider_usage(
                    [*entry["initial_tasks"].values(), later["task"], *entry["correction_tasks"].values(), post["task"]]
                )
                entry["passed"] = (
                    not entry["degraded_states"]
                    and entry["initial_tasks"]["rollout"]["state_engine_runtime"]["decision_material_count"] >= 1
                    and bool(entry["material_later_use"]["before_correction"])
                    and bool(entry["material_later_use"]["after_correction"])
                    and not entry["material_later_use"]["beneficial_impact_supported"]
                    and entry["durable_task_identity"]["same_after_restart"]
                    and entry["correction"]["supersedes_initial"]
                    and len(entry["correction"]["authoritative_memory_ids"]) == 1
                    and entry["reconciliation"]["disposition"] == config["k3"]["later_outcomes"][repetition - 1]
                    and entry["reconciliation"]["original_rollout_preserved"]
                    and entry["reconciliation"]["action_branch_present"]
                    and entry["reconciliation"]["no_action_branch_present"]
                    and entry["product_isolation"]["foreign_promoted_memories"] == 0
                    and not entry["product_isolation"]["foreign_rollout_visible"]
                    and entry["simulation_separation"]["simulated_as_observation_rows"] == 0
                    and entry["provider_usage"]["calls"] == 0
                    and entry["provider_usage"]["input_tokens"] == 0
                    and entry["provider_usage"]["output_tokens"] == 0
                    and entry["provider_usage"]["retries"] == 0
                    and later["thin_mcp_tool_count"] == post["thin_mcp_tool_count"] == 11
                )
            except Exception as exc:
                category = f"{type(exc).__name__}:{str(exc)[:300]}"
                entry["failures"].append(category)
                entry["passed"] = False
                failures.append(f"{repetition}:{category}")
            finally:
                await processes.stop_runtime()
            repetitions.append(entry)
            _write(raw_dir / f"k3-repetition-{repetition:02d}.json", entry)

        provider = _provider_usage(all_tasks)
        summary = {
            "journeys_evaluated": len(repetitions),
            "journeys_passed": sum(item.get("passed", False) for item in repetitions),
            "failures": len(failures),
            "retries": provider["retries"],
            "degraded_states": sum(len(item.get("degraded_states") or []) for item in repetitions),
            "task_reasoning_latency": latency_summary(task_latencies),
            "promotion_latency": latency_summary(promotion_latencies),
            "fresh_retrieval_latency": latency_summary(retrieval_latencies),
            "maximum_restart_seconds": max(
                (
                    max(
                        float((item.get("restart_before_later_use") or {}).get("total_restart_seconds") or 0),
                        float((item.get("restart_after_correction") or {}).get("total_restart_seconds") or 0),
                    )
                    for item in repetitions
                ),
                default=0,
            ),
            "product_isolation_violations": sum(
                int((item.get("product_isolation") or {}).get("foreign_promoted_memories", 0) > 0)
                + int(bool((item.get("product_isolation") or {}).get("foreign_rollout_visible")))
                for item in repetitions
            ),
            "simulated_as_observed_violations": sum(
                int((item.get("simulation_separation") or {}).get("simulated_as_observation_rows", 0))
                for item in repetitions
            ),
            "durable_task_identity_failures": sum(
                not (item.get("durable_task_identity") or {}).get("same_after_restart", False) for item in repetitions
            ),
            "promotion_lineage_failures": sum(
                not (item.get("correction") or {}).get("supersedes_initial", False) for item in repetitions
            ),
            "restart_continuity_failures": sum(
                not item.get("reconciliation", {}).get("original_rollout_preserved", False) for item in repetitions
            ),
            "material_later_use_failures": sum(
                not (item.get("material_later_use") or {}).get("before_correction")
                or not (item.get("material_later_use") or {}).get("after_correction")
                for item in repetitions
            ),
            "reconciliations": sum(bool(item.get("reconciliation")) for item in repetitions),
            "corrections_or_supersessions": sum(
                bool((item.get("correction") or {}).get("supersedes_initial")) for item in repetitions
            ),
            "provider_usage": provider,
        }
        threshold = config["k3"]["thresholds"]
        passed = (
            summary["journeys_evaluated"] == threshold["journeys_evaluated"]
            and summary["journeys_passed"] == threshold["journeys_passed"]
            and summary["failures"] <= threshold["failures_max"]
            and summary["retries"] <= threshold["retries_max"]
            and summary["degraded_states"] <= threshold["degraded_states_max"]
            and summary["task_reasoning_latency"]["p95_ms"] <= threshold["task_reasoning_latency_p95_ms_max"]
            and summary["promotion_latency"]["p95_ms"] <= threshold["promotion_latency_p95_ms_max"]
            and summary["fresh_retrieval_latency"]["p95_ms"] <= threshold["fresh_retrieval_latency_p95_ms_max"]
            and summary["maximum_restart_seconds"] <= threshold["api_worker_client_restart_seconds_max"]
            and summary["product_isolation_violations"] <= threshold["product_isolation_violations_max"]
            and summary["simulated_as_observed_violations"] <= threshold["simulated_as_observed_violations_max"]
            and summary["durable_task_identity_failures"] <= threshold["durable_task_identity_failures_max"]
            and summary["promotion_lineage_failures"] <= threshold["promotion_lineage_failures_max"]
            and summary["restart_continuity_failures"] <= threshold["restart_continuity_failures_max"]
            and summary["material_later_use_failures"] <= threshold["material_later_use_failures_max"]
            and summary["reconciliations"] == threshold["reconciliations"]
            and summary["corrections_or_supersessions"] == threshold["corrections_or_supersessions"]
            and provider["calls"] <= threshold["provider_calls_max"]
            and provider["input_tokens"] + provider["output_tokens"] <= threshold["provider_tokens_max"]
            and provider["cost_usd"] <= threshold["provider_cost_usd_max"]
        )
        return {
            "status": "passed" if passed else "failed",
            "decision": "ready" if passed else "candidate",
            "schema_receipt": schema_receipt,
            "summary": summary,
            "repetitions": repetitions,
            "failures": failures,
        }
    finally:
        await processes.close()


async def _main_async(args) -> int:
    config = load_readiness_config(args.config)
    if args.command == "freeze-check":
        result = {
            "status": "passed",
            "config_file_sha256": readiness_config_hash(args.config),
            "fixture_status": config["fixture_status"],
            "k2_repetitions": config["k2"]["repetitions"],
            "k3_repetitions": config["k3"]["repetitions"],
        }
    elif args.command in {"k1", "k2"}:
        db, pool = await _connect(args.url, args.namespace, args.database)
        try:
            result = await (
                revalidate_k1(pool, config)
                if args.command == "k1"
                else measure_k2(pool, config, product_prefix=args.product_prefix)
            )
        finally:
            await db.close()
    elif args.command == "k3":
        result = await run_k3(args, config)
    elif args.command == "summarize":
        k1 = json.loads(Path(args.k1_result).read_text(encoding="utf-8"))
        k2 = json.loads(Path(args.k2_result).read_text(encoding="utf-8"))
        k3 = json.loads(Path(args.k3_result).read_text(encoding="utf-8"))
        result = compile_readiness_result(
            config=config,
            k1=k1,
            k2=k2,
            k3=k3,
            commands=[
                "uv run python scripts/run_state_engine_readiness.py freeze-check",
                "uv run python scripts/run_state_engine_readiness.py --url <disposable> k1",
                "uv run python scripts/run_state_engine_readiness.py --url <disposable> k2",
                "uv run python scripts/run_state_engine_readiness.py k3 --store <disposable-copy>",
                "uv run python scripts/run_state_engine_readiness.py summarize",
            ],
        )
        validate_readiness_result(result)
    else:
        raise AssertionError(args.command)
    if args.output:
        _write(Path(args.output), result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status", "passed") == "passed" and result.get("passed", True) else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output")
    parser.add_argument("--url", default="ws://127.0.0.1:18009")
    parser.add_argument("--namespace", default="ace_tp8")
    parser.add_argument("--database", default="ace_tp8")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze-check")
    subparsers.add_parser("k1")
    k2 = subparsers.add_parser("k2")
    k2.add_argument("--product-prefix", default="k123-k2")
    k3 = subparsers.add_parser("k3")
    k3.add_argument("--store", required=True)
    k3.add_argument("--surreal-bin", default=shutil.which("surreal") or "/opt/homebrew/bin/surreal")
    k3.add_argument("--raw-dir", required=True)
    k3.add_argument("--k2-result", required=True)
    summary = subparsers.add_parser("summarize")
    summary.add_argument("--k1-result", required=True)
    summary.add_argument("--k2-result", required=True)
    summary.add_argument("--k3-result", required=True)
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(_main_async(_parser().parse_args())))


if __name__ == "__main__":
    main()
