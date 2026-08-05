#!/usr/bin/env python3
"""Run the frozen extension-first K1-K3 Fjord Operations product journey."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from surrealdb import AsyncSurreal

from core.engine.candidates import CandidateRequestV1, CandidateSignal
from core.engine.core.db import parse_one
from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BoundedEvidencePackV1,
    EpistemicAssertionProposalV1,
    EpistemicAssertionV1,
    EpistemicRelation,
    ProjectionTargetV1,
    ReviewAuthority,
    ReviewDisposition,
)
from core.engine.grounded_state.belief_persistence import BeliefStateStore
from core.engine.grounded_state.beliefs import (
    build_projection,
    freeze_evidence_pack,
    resolve_assertion,
)
from core.engine.grounded_state.contracts import (
    CausalStrength,
    ProbabilityEstimateV1,
    RolloutBranchKind,
    TransitionReviewState,
    canonical_hash,
)
from core.engine.grounded_state.evidence_query import resolve_evidence_query
from core.engine.grounded_state.ingestion_contracts import BatchIngestionReceiptV1
from core.engine.grounded_state.persistence import GroundedStateStore
from core.engine.grounded_state.promotion import PromotionService
from core.engine.grounded_state.promotion_contracts import PromotionReceiptV1, PromotionReviewV1
from core.engine.grounded_state.retrieval import GroundedStateCandidateService
from core.engine.grounded_state.rollout_contracts import (
    EvidenceQueryV1,
    ReasoningEvidencePackV1,
    RolloutOutcomeObservationV1,
)
from core.engine.grounded_state.rollouts import ConsequenceRolloutService
from core.engine.grounded_state.transition_contracts import (
    ConditionOperator,
    StateAssignmentV1,
    StateConditionV1,
    StateValueType,
    StateVariableV1,
    TransitionDerivationRoute,
    TransitionHypothesisProposalV1,
    TransitionTriggerKind,
    TransitionTriggerV1,
)
from core.engine.grounded_state.transitions import TransitionHypothesisService, TransitionResolutionError
from evaluations.state_engine_product_journey import (
    PRODUCTIZED_CONFIG_CONTRACT,
    PRODUCTIZED_RESULT_CONTRACT,
    STATE_ENGINE_RESULT_CONTRACT,
    acceptance_hash,
    load_product_journey_config,
    product_journey_config_hash,
    render_product_journey_markdown,
    validate_product_journey_result,
)
from scripts.schema_apply import apply_file, get_current_version, validate_schema

ROOT = Path(__file__).parents[1]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_product_journey_v1.json"
TERMINAL_TASK_STATES = {"completed", "failed", "degraded"}
HOST_SITE_PACKAGES = next(Path(path) for path in sys.path if path.endswith("site-packages") and Path(path).is_dir())


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
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return time.perf_counter() - started
        except OSError:
            await asyncio.sleep(0.05)
    raise TimeoutError(f"port {port} was not ready within {timeout}s")


async def _wait_http(url: str, process: subprocess.Popen, timeout: float = 45) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    deadline = started + timeout
    async with httpx.AsyncClient(timeout=2) as client:
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"process exited before {url} was ready: {process.returncode}")
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return time.perf_counter() - started, response.json()
            except (httpx.HTTPError, ValueError):
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
        python: Path,
        store: Path,
        surreal: str,
        work_dir: Path,
        namespace: str,
        database: str,
        config: dict[str, Any],
    ) -> None:
        self.python = str(python)
        self.store = store
        self.surreal = surreal
        self.work_dir = work_dir
        self.namespace = namespace
        self.database = database
        self.config = config
        self.db_port = _free_port()
        self.api_port = _free_port()
        self.worker_port = _free_port()
        self.db: subprocess.Popen | None = None
        self.api: subprocess.Popen | None = None
        self.worker: subprocess.Popen | None = None
        self._handles: list[Any] = []
        self.secret = "fjord-product-journey-disposable-jwt-secret-at-least-32-bytes"
        self.interrupt_marker = self.work_dir / "restart-interruption.marker"

    @property
    def db_url(self) -> str:
        return f"ws://127.0.0.1:{self.db_port}"

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    def token(self, product_id: str) -> str:
        return jwt.encode(
            {
                "sub": self.config["scenario"]["user_id"],
                "product": product_id,
                "feature_flags": ["state-engine-tp6", "state-engine-tp7"],
                "authorities": ["state-engine-promotion-review"],
                "exp": datetime.now(UTC) + timedelta(hours=3),
            },
            self.secret,
            algorithm="HS256",
        )

    def _log(self, name: str):
        path = self.work_dir / name
        handle = path.open("ab")
        self._handles.append(handle)
        return handle

    def env(self, product_id: str) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("ACE_DISABLE_EXTENSIONS", None)
        env.pop("ACE_EXTENSIONS", None)
        root_path = os.pathsep.join((str(ROOT), str(HOST_SITE_PACKAGES)))
        if env.get("PYTHONPATH"):
            root_path = root_path + os.pathsep + env["PYTHONPATH"]
        env.update(
            {
                "PYTHONPATH": root_path,
                "SURREAL_URL": self.db_url,
                "SURREAL_NS": self.namespace,
                "SURREAL_DB": self.database,
                "SURREAL_USER": "root",
                "SURREAL_PASS": "root",
                "JWT_SECRET": self.secret,
                "API_KEY": "",
                "LLM_API_KEY": "sk-test-placeholder",
                "REQUIRE_SUBSCRIPTION": "1",
                "ACE_PRODUCT_ID": product_id,
                "ACE_WORKER_HOST": "127.0.0.1",
                "ACE_WORKER_PORT": str(self.worker_port),
                "ACE_URL": self.api_url,
                "ACE_TOKEN": self.token(product_id),
                "ACE_PRODUCT_JOURNEY_INTERRUPT_MARKER": str(self.interrupt_marker),
                "ENGINE_LOG_LEVEL": "WARNING",
            }
        )
        return env

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

    async def start_runtime(self, *, product_id: str, label: str) -> dict[str, Any]:
        env = self.env(product_id)
        self.api = subprocess.Popen(
            [
                self.python,
                "-m",
                "uvicorn",
                "evaluations.state_engine_product_journey_app:app",
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
        api_seconds, health = await _wait_http(f"{self.api_url}/health/live", self.api)
        self.worker = subprocess.Popen(
            [self.python, str(ROOT / "core/engine/worker/start.py")],
            cwd=ROOT,
            env=env,
            stdout=self._log(f"{label}-worker.log"),
            stderr=subprocess.STDOUT,
        )
        worker_seconds, worker_health = await _wait_http(
            f"http://127.0.0.1:{self.worker_port}/health",
            self.worker,
        )
        return {
            "api_pid": self.api.pid,
            "worker_pid": self.worker.pid,
            "api_start_seconds": round(api_seconds, 6),
            "worker_start_seconds": round(worker_seconds, 6),
            "api_health": health,
            "worker_health": worker_health,
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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _run_checked(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float = 180
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout[-800:]}\n{completed.stderr[-800:]}"
        )
    return completed


def _install_clean_extension(work_dir: Path, config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    extension_root = ROOT / "examples/ace_ext_fjord_operations"
    extension_build_root = work_dir / "extension-source"
    shutil.copytree(extension_root, extension_build_root)
    wheel_dir = work_dir / "wheelhouse"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    build = _run_checked(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(extension_build_root),
        ],
        cwd=work_dir,
        env=os.environ.copy(),
    )
    wheels = sorted(wheel_dir.glob("ace_ext_fjord_operations-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one Fjord Operations wheel, found {len(wheels)}")

    venv_dir = work_dir / "clean-extension-runtime"
    _run_checked(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    python = venv_dir / "bin/python"
    install_env = os.environ.copy()
    install_env["PIP_CACHE_DIR"] = str(work_dir / "pip-cache")
    install = _run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(wheels[0]),
        ],
        cwd=work_dir,
        env=install_env,
    )
    probe_code = """
import json
import logging
from importlib import metadata
logging.basicConfig(level=logging.INFO)
from core.engine.extensions.loader import load_extensions
from core.engine.extensions.registry import registered_grounded_state_adapters, registered_task_actions
loaded = load_extensions()
entry_points = sorted(ep.name for ep in metadata.entry_points(group='ace.extensions'))
distribution = metadata.distribution('ace-ext-fjord-operations')
print(json.dumps({
    'distribution': distribution.metadata['Name'],
    'version': distribution.version,
    'entry_points': entry_points,
    'loaded': loaded,
    'adapters': [list(key) for key in sorted(registered_grounded_state_adapters())],
    'actions': [list(key) for key in sorted(registered_task_actions())],
}, sort_keys=True))
"""
    probe_env = os.environ.copy()
    probe_env.pop("ACE_DISABLE_EXTENSIONS", None)
    probe_env.pop("ACE_EXTENSIONS", None)
    probe_env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HOST_SITE_PACKAGES)))
    probe_env["JWT_SECRET"] = "fjord-clean-install-probe-secret-at-least-32-bytes"
    probe = _run_checked([str(python), "-c", probe_code], cwd=work_dir, env=probe_env)
    details = json.loads(probe.stdout.splitlines()[-1])
    expected_adapter = [config["extension"]["extension_id"], config["extension"]["adapter_name"]]
    expected_actions = {
        [config["extension"]["extension_id"], "evidence-query"][1],
        [config["extension"]["extension_id"], "promotion-review"][1],
    }
    actual_action_names = {item[1] for item in details["actions"] if item[0] == config["extension"]["extension_id"]}
    if (
        config["extension"]["entry_point"] not in details["entry_points"]
        or config["extension"]["entry_point"] not in details["loaded"]
        or expected_adapter not in details["adapters"]
        or expected_actions - actual_action_names
    ):
        raise RuntimeError(
            "clean extension installation did not expose the frozen entry point, adapter, and actions: "
            + json.dumps(
                {
                    "details": details,
                    "expected_adapter": expected_adapter,
                    "expected_actions": sorted(expected_actions),
                    "actual_action_names": sorted(actual_action_names),
                    "probe_stderr": probe.stderr,
                },
                sort_keys=True,
            )
        )
    details["install_output"] = install.stdout.splitlines()[-1] if install.stdout.splitlines() else "installed"
    details["build_output"] = build.stdout.splitlines()[-1] if build.stdout.splitlines() else "built"
    details["wheel"] = wheels[0].name
    return python, details


async def _apply_frozen_schema_head(
    processes: ProcessSet,
    *,
    product_id: str,
    target_version: int,
) -> tuple[float, str]:
    """Apply only the schema files bound by the frozen product-journey fixture."""

    started = time.perf_counter()
    db, _pool = await _connect(processes.db_url, processes.namespace, processes.database)
    applied = 0
    compatibility_events: list[str] = []
    try:
        current = await get_current_version(db)
        for version, path in _schema_files_through(target_version):
            if version <= current:
                continue
            compatibility_events.extend(await apply_file(db, version, path.name, path.read_text(encoding="utf-8")))
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', value = $version WHERE key = 'schema_version'",
                {"version": str(version)},
            )
            applied += 1
        await validate_schema(db, target_version)
    finally:
        await db.close()
    summary = (
        f"Done — applied {applied} file(s); frozen schema v{target_version} validated "
        f"({len(compatibility_events)} audited legacy compatibility events)."
    )
    return time.perf_counter() - started, summary


def _schema_files_through(version: int) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in (ROOT / "core/schema").glob("v*.surql"):
        match = re.match(r"v(\d+)", path.name)
        if match and int(match.group(1)) <= version:
            found.append((int(match.group(1)), path))
    return sorted(found, key=lambda item: (item[0], item[1].name))


async def _prepare_upgrade_base(processes: ProcessSet, *, from_version: int, product_id: str) -> dict[str, Any]:
    db, _pool = await _connect(processes.db_url, processes.namespace, processes.database)
    compatibility_events: list[str] = []
    try:
        for version, path in _schema_files_through(from_version):
            compatibility_events.extend(await apply_file(db, version, path.name, path.read_text(encoding="utf-8")))
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', value = $version WHERE key = 'schema_version'",
                {"version": str(version)},
            )
        await validate_schema(db, from_version)
        await db.query(
            "UPSERT product:fjord_upgrade_sentinel SET name = 'Fjord upgrade sentinel', tenant = tenant:test, settings = {}"
        )
        return {
            "from_version": await get_current_version(db),
            "migration_files": len(_schema_files_through(from_version)),
            "compatibility_events": len(compatibility_events),
            "sentinel_product_id": "product:fjord_upgrade_sentinel",
        }
    finally:
        await db.close()


async def _verify_schema_paths(
    *,
    python: Path,
    surreal: str,
    work_dir: Path,
    config: dict[str, Any],
) -> tuple[ProcessSet, dict[str, Any]]:
    product_id = config["scenario"]["product_id"]
    main = ProcessSet(
        python=python,
        store=work_dir / "main-store",
        surreal=surreal,
        work_dir=work_dir,
        namespace="ace_fjord_journey",
        database="ace_fjord_journey",
        config=config,
    )
    await main.start_db("schema-zero")
    schema_zero_seconds, schema_zero_summary = await _apply_frozen_schema_head(
        main,
        product_id=product_id,
        target_version=config["acceptance"]["schema_head"],
    )
    db, _pool = await _connect(main.db_url, main.namespace, main.database)
    try:
        schema_zero_version = await get_current_version(db)
        await validate_schema(db, config["acceptance"]["schema_head"])
    finally:
        await db.close()

    upgrade = ProcessSet(
        python=python,
        store=work_dir / "upgrade-store",
        surreal=surreal,
        work_dir=work_dir / "upgrade-logs",
        namespace="ace_fjord_upgrade",
        database="ace_fjord_upgrade",
        config=config,
    )
    upgrade.work_dir.mkdir(parents=True, exist_ok=True)
    try:
        await upgrade.start_db("v160-base")
        prepared = await _prepare_upgrade_base(
            upgrade,
            from_version=config["acceptance"]["supported_upgrade_from"],
            product_id=product_id,
        )
        upgrade_seconds, upgrade_summary = await _apply_frozen_schema_head(
            upgrade,
            product_id=product_id,
            target_version=config["acceptance"]["schema_head"],
        )
        db, _pool = await _connect(upgrade.db_url, upgrade.namespace, upgrade.database)
        try:
            to_version = await get_current_version(db)
            await validate_schema(db, config["acceptance"]["schema_head"])
            sentinel = parse_one(await db.query("SELECT id, name FROM ONLY product:fjord_upgrade_sentinel"))
        finally:
            await db.close()
    finally:
        await upgrade.close()
    return main, {
        "schema_zero": {
            "version": schema_zero_version,
            "latency_seconds": round(schema_zero_seconds, 6),
            "summary": schema_zero_summary,
        },
        "upgrade": {
            **prepared,
            "to_version": to_version,
            "latency_seconds": round(upgrade_seconds, 6),
            "summary": upgrade_summary,
            "sentinel_preserved": bool(sentinel and sentinel.get("name") == "Fjord upgrade sentinel"),
        },
    }


async def _ingest_and_replay(
    pool,
    config: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    product_state_capabilities: dict[str, Any],
) -> tuple[dict[str, Any], BoundedEvidencePackV1]:
    corpus_path = ROOT / config["extension"]["corpus_path"]
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    scenario = config["scenario"]
    request = {
        "contract_version": "ace.product-state.ingestion/v1",
        "extension_id": config["extension"]["extension_id"],
        "extension_version": config["extension"]["extension_version"],
        "adapter_name": config["extension"]["adapter_name"],
        "manifest_external_id": scenario["manifest_external_id"],
        "extraction_run_id": scenario["extraction_run_id"],
        "submitted_at": scenario["submitted_at"],
        "records": corpus["records"],
    }
    initial_response = await client.post("/product-state/ingestions", json=request)
    initial_response.raise_for_status()
    replay_response = await client.post("/product-state/ingestions", json=request)
    replay_response.raise_for_status()
    initial_payload = initial_response.json()
    replay_payload = replay_response.json()
    initial = BatchIngestionReceiptV1.model_validate(initial_payload["receipt"])
    replay = BatchIngestionReceiptV1.model_validate(replay_payload["receipt"])
    adapter_manifest = next(
        (
            item
            for item in product_state_capabilities.get("adapters", [])
            if item.get("extension_id") == config["extension"]["extension_id"]
            and item.get("adapter_name") == config["extension"]["adapter_name"]
        ),
        None,
    )
    if adapter_manifest is None:
        raise RuntimeError("the Product State capability receipt omitted the installed Fjord adapter")
    records = await GroundedStateCandidateService(pool).records(product_id=scenario["product_id"])
    foreign_records = await GroundedStateCandidateService(pool).records(product_id=scenario["foreign_product_id"])
    version_lineage = (
        initial.lineage_edges_persisted >= 1
        and bool(initial.lineage_ids)
        and any(record.source_version == "v2" and record.supersedes for record in records)
    )
    query = EvidenceQueryV1(
        product_id=scenario["product_id"],
        task_id="task:fjord-projection-freeze-v1",
        invocation_id="invocation:fjord-projection-freeze-v1",
        authorization_scope_hash=canonical_hash("fjord-product-builder-authority-v1"),
        question=("Fjord cooling circuit chamber temperature active standby monitoring plan independent sensor drill"),
        as_of=datetime.fromisoformat(scenario["as_of"].replace("Z", "+00:00")),
        max_candidates=200,
        max_records=200,
        max_chars=64_000,
    )
    context = await resolve_evidence_query(query, pool=pool)
    query_pack = context.evidence_pack
    if len(query_pack.items) < 6:
        raise RuntimeError(f"the frozen product query selected only {len(query_pack.items)} evidence records")

    # Freeze the transition challenge from an explicit two-signal search.  The
    # general evidence-query surface also records unavailable optional signals;
    # those remain visible in ``query_pack`` but must not be silently carried
    # into the separate complete-challenge positive case.
    challenge_request = CandidateRequestV1(
        product_id=scenario["product_id"],
        content=query.question,
        enabled_signals=(CandidateSignal.LEXICAL, CandidateSignal.VECTOR),
        k=50,
        max_candidates=200,
    )
    candidate_service = GroundedStateCandidateService(pool)
    challenge_candidates = await candidate_service.find_candidates(challenge_request)
    grounded_store = GroundedStateStore(pool)
    challenge_records = [
        record
        for item in challenge_candidates.candidates
        if (
            record := await grounded_store.load_any_record(
                item.record_id,
                product_id=scenario["product_id"],
            )
        )
        is not None
    ]
    challenge_created_at = await grounded_store.ace_created_times_for_ids(
        (str(record.record_id) for record in challenge_records),
        product_id=scenario["product_id"],
    )
    pack = freeze_evidence_pack(
        product_id=scenario["product_id"],
        as_of=query.as_of,
        candidate_receipt=challenge_candidates,
        records=challenge_records,
        ace_created_at_by_record=challenge_created_at,
        max_records=200,
        max_chars=64_000,
    )
    await BeliefStateStore(pool).persist(pack)
    if pack.truncated or pack.omissions or pack.failures or pack.degraded_reasons:
        raise RuntimeError(
            "the frozen exact transition challenge pack is incomplete: "
            + json.dumps(
                {
                    "truncated": pack.truncated,
                    "omissions": pack.omissions,
                    "failures": pack.failures,
                    "degraded_reasons": pack.degraded_reasons,
                },
                sort_keys=True,
            )
        )
    unavailable_query = EvidenceQueryV1.model_validate(
        {
            **query.model_dump(mode="python", exclude={"query_id", "query_hash"}),
            "product_id": scenario["foreign_product_id"],
            "task_id": "task:fjord-unavailable-evidence-v1",
            "invocation_id": "invocation:fjord-unavailable-evidence-v1",
            "authorization_scope_hash": canonical_hash("fjord-foreign-authority-v1"),
        }
    )
    unavailable = await resolve_evidence_query(unavailable_query, pool=pool)
    item_times = [
        item for item in query_pack.items if item.compact_content and "controlled drill" in item.compact_content
    ]
    if not item_times:
        raise RuntimeError("the four-time cooling drill evidence was not selected into the frozen pack")
    timed = item_times[0]
    time_meanings = {
        "event_or_valid_time": timed.temporal.model_dump(mode="json"),
        "published_at": timed.published_at.isoformat() if timed.published_at else None,
        "ingested_at": timed.ingested_at.isoformat(),
        "extracted_at": timed.extracted_at.isoformat() if timed.extracted_at else None,
        "ace_created_at": timed.ace_created_at.isoformat(),
    }
    distinct_times = {
        value for key, value in time_meanings.items() if key != "event_or_valid_time" and isinstance(value, str)
    }
    ingestion = {
        "transport": "POST /product-state/ingestions",
        "contract_version": initial_payload["contract_version"],
        "extension_loader_names": [config["extension"]["extension_id"]],
        "extension_version": adapter_manifest["extension_version"],
        "adapter_id": adapter_manifest["adapter_id"],
        "adapter_version": adapter_manifest["adapter_version"],
        "adapter_manifest": adapter_manifest,
        "authority": initial_payload["authority"],
        "manifest_id": str(initial.manifest_id),
        "manifest_hash": str(initial.manifest_hash),
        "receipt_id": str(initial.receipt_id),
        "item_counts": initial.item_counts.model_dump(mode="json"),
        "record_counts": initial.record_counts.model_dump(mode="json"),
        "persisted_by_kind": initial.persisted_by_kind.model_dump(mode="json"),
        "stable_record_ids": list(initial.stable_record_ids),
        "lineage_ids": list(initial.lineage_ids),
        "source_items": len(corpus["records"]),
        "persisted_semantic_records": len(records),
        "primary_model_calls": initial.primary_model_calls,
        "exact_replay": initial == replay,
        "counts_reconciled": (
            initial.item_counts.inputs == len(corpus["records"])
            and initial.persisted_by_kind.total() == len(records)
            and set(initial.stable_record_ids) == {str(record.record_id) for record in records}
        ),
        "version_lineage": version_lineage,
        "product_isolation": not foreign_records,
        "time_meanings": time_meanings,
        "distinct_non_event_times": len(distinct_times),
        "evidence_pack_id": str(pack.pack_id),
        "evidence_pack_hash": str(pack.pack_hash),
        "evidence_selected": pack.selected_count,
        "evidence_candidates": pack.candidate_count,
        "query_evidence_pack_id": str(query_pack.pack_id),
        "query_degraded_reasons": list(query_pack.degraded_reasons),
        "unavailable_evidence_selected": unavailable.evidence_pack.selected_count,
    }
    return ingestion, pack


def _assertion_material(
    *,
    pack: BoundedEvidencePackV1,
) -> tuple[
    tuple[EpistemicAssertionProposalV1, ...],
    tuple[AssertionReviewV1, ...],
    tuple[EpistemicAssertionV1, ...],
    tuple[ProjectionTargetV1, ...],
]:
    items = list(pack.items)
    subject = next((item.endpoint for item in items if item.endpoint.kind.value == "entity"), items[0].endpoint)
    objects = [item.endpoint for item in items if item.endpoint.record_id != subject.record_id]
    evidence_refs = [item.endpoint.record_id for item in items]
    origins = [item.publisher_id for item in items]
    as_of = pack.as_of

    def proposal(
        *,
        predicate: str,
        value: str,
        relation: EpistemicRelation,
        object_index: int,
        supporting: tuple[str, ...],
        contrary: tuple[str, ...] = (),
        supersedes: tuple[str, ...] = (),
    ) -> EpistemicAssertionProposalV1:
        return EpistemicAssertionProposalV1(
            product_id=pack.product_id,
            subject=subject,
            relation=relation,
            object=objects[object_index],
            belief_subject=subject,
            belief_predicate=predicate,
            belief_value=value,
            supersedes_assertion_refs=supersedes,
            proposed_at=as_of,
            evidence_pack_id=str(pack.pack_id),
            evidence_pack_hash=str(pack.pack_hash),
            supporting_evidence_refs=supporting,
            contrary_evidence_refs=contrary,
            source_origin_ids=tuple(sorted(set(origins[: max(1, len(supporting))]))),
            source_confidence=0.9,
            epistemic_confidence=0.8,
            freshness=0.95,
            rationale=f"Frozen Fjord Operations {predicate} assertion.",
            proposer_authority="deterministic_policy",
            proposer_ref="policy:fjord-operations-belief-compiler/v1",
        )

    supported = proposal(
        predicate="cooling_state",
        value="active",
        relation=EpistemicRelation.SUPPORTS,
        object_index=0,
        supporting=(evidence_refs[0], evidence_refs[1]),
    )
    provisional = proposal(
        predicate="standby_test_status",
        value="pending",
        relation=EpistemicRelation.SUPPORTS,
        object_index=1,
        supporting=(evidence_refs[2],),
    )
    contested = proposal(
        predicate="temperature_risk",
        value="elevated",
        relation=EpistemicRelation.CONTRADICTS,
        object_index=2,
        supporting=(evidence_refs[3],),
        contrary=(evidence_refs[4],),
    )
    old = proposal(
        predicate="monitoring_policy_revision",
        value="recorded",
        relation=EpistemicRelation.SUPPORTS,
        object_index=3,
        supporting=(evidence_refs[4],),
    )
    successor = proposal(
        predicate="monitoring_policy_revision",
        value="recorded",
        relation=EpistemicRelation.SUPERSEDES,
        object_index=4,
        supporting=(evidence_refs[5],),
        supersedes=(old.assertion_id(),),
    )
    proposals = (supported, provisional, contested, old, successor)
    dispositions = (
        ReviewDisposition.ACCEPTED,
        ReviewDisposition.PROPOSED,
        ReviewDisposition.ACCEPTED,
        ReviewDisposition.ACCEPTED,
        ReviewDisposition.ACCEPTED,
    )
    reviews = tuple(
        AssertionReviewV1(
            product_id=pack.product_id,
            proposal_id=str(item.proposal_id),
            assertion_id=item.assertion_id(),
            reviewed_material_hash=item.review_material_hash(),
            disposition=disposition,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:fjord-operations-belief-review/v1",
            reviewed_at=as_of,
            rationale=f"Frozen Fjord Operations {disposition.value} review.",
            policy_version=item.assertion_policy_version,
        )
        for item, disposition in zip(proposals, dispositions, strict=True)
    )
    assertions = tuple(
        resolve_assertion(item, review, evidence_pack=pack) for item, review in zip(proposals, reviews, strict=True)
    )
    targets = (ProjectionTargetV1(subject=subject, predicate="inspection_state"),)
    return proposals, reviews, assertions, targets


async def _build_belief_and_transition(
    pool,
    *,
    pack: BoundedEvidencePackV1,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], TransitionHypothesisProposalV1, Any]:
    proposals, reviews, assertions, targets = _assertion_material(pack=pack)
    projection = build_projection(
        product_id=pack.product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=assertions,
        targets=targets,
    )
    await BeliefStateStore(pool).persist_all((pack, *proposals, *reviews, *assertions, projection))
    statuses = sorted({entry.status.value for entry in projection.entries})
    supported_entry = next(
        entry
        for entry in projection.entries
        if entry.predicate == "cooling_state" and entry.status.value == "supported"
    )
    source_variable = StateVariableV1(
        subject=supported_entry.subject,
        predicate=supported_entry.predicate,
        value_type=StateValueType.CATEGORICAL,
        allowed_values=("active", "disconnected"),
    )
    target_variable = StateVariableV1(
        subject=supported_entry.subject,
        predicate="chamber_temperature_risk",
        value_type=StateValueType.CATEGORICAL,
        allowed_values=("elevated", "low"),
    )
    proposal = TransitionHypothesisProposalV1(
        product_id=pack.product_id,
        projection_id=str(projection.projection_id),
        projection_hash=str(projection.projection_hash),
        projection_entry_refs=(str(supported_entry.entry_id),),
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        as_of=pack.as_of,
        source=StateConditionV1(
            variable=source_variable,
            operator=ConditionOperator.EQ,
            value="active",
        ),
        target=StateAssignmentV1(variable=target_variable, value="elevated"),
        trigger=TransitionTriggerV1(
            kind=TransitionTriggerKind.ACTION,
            description="Disconnect the active cooling circuit under an explicit operator decision.",
            trigger_ref="fjord-operations:disconnect-active-cooling/v1",
        ),
        mechanism="Disconnecting active cooling permits chamber temperature to rise after thermal lag.",
        delay_min_seconds=3_600,
        delay_max_seconds=86_400,
        probability=ProbabilityEstimateV1(lower=0.55, expected=0.75, upper=0.9),
        causal_strength=CausalStrength.MECHANISTIC,
        derivation_routes=(TransitionDerivationRoute.EXTENSION_DYNAMICS,),
        supporting_evidence_refs=tuple(item.endpoint.record_id for item in pack.items[:2]),
        contrary_evidence_refs=(),
        supporting_assertion_refs=(supported_entry.accepted_assertion_id,),
        proposer_authority=ReviewAuthority.DETERMINISTIC_POLICY,
        proposer_ref="extension:fjord-operations/dynamics-v1",
    )
    transition_service = TransitionHypothesisService(pool)
    revision = await transition_service.resolve_and_persist(
        proposal,
        disposition=TransitionReviewState.PROVISIONAL,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:fjord-operations-transition-review/v1",
        reviewed_at=pack.as_of,
        rationale="The frozen mechanism and complete challenge are provisionally rollout eligible.",
    )
    branch_input = await transition_service.freeze_branch_input(str(revision.revision_id), product_id=pack.product_id)
    causal_payload = proposal.model_dump(mode="python", exclude={"proposal_id"})
    causal_payload["causal_strength"] = CausalStrength.CAUSAL
    causal = TransitionHypothesisProposalV1.model_validate(causal_payload)
    causal_error = ""
    try:
        await transition_service.resolve_and_persist(
            causal,
            disposition=TransitionReviewState.ACCEPTED,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:fjord-unsupported-causality-control/v1",
            reviewed_at=pack.as_of,
            rationale="Negative control: deterministic policy must not accept causal authority.",
        )
    except TransitionResolutionError as exc:
        causal_error = str(exc)
    belief = {
        "projection_id": str(projection.projection_id),
        "projection_hash": str(projection.projection_hash),
        "as_of": projection.as_of.isoformat(),
        "evidence_pack_id": projection.evidence_pack_id,
        "evidence_pack_hash": projection.evidence_pack_hash,
        "statuses": statuses,
        "entries": [
            {
                "entry_id": str(entry.entry_id),
                "predicate": entry.predicate,
                "status": entry.status.value,
                "operational": entry.operational,
                "assertion_revision_id": entry.assertion_revision_id,
                "supporting_evidence_refs": list(entry.supporting_evidence_refs),
                "contradicting_evidence_refs": list(entry.contradicting_evidence_refs),
                "superseding_assertion_refs": list(entry.superseding_assertion_refs),
                "missing_evidence": list(entry.missing_evidence),
            }
            for entry in projection.entries
        ],
        "provider_usage": projection.provider_usage.model_dump(mode="json"),
    }
    transition = {
        "proposal_id": str(proposal.proposal_id),
        "revision_id": str(revision.revision_id),
        "revision_hash": str(revision.revision_hash),
        "hypothesis_id": revision.hypothesis_id,
        "mechanism": revision.mechanism,
        "preconditions": [revision.source.model_dump(mode="json")],
        "time_horizon_seconds": [revision.delay_min_seconds, revision.delay_max_seconds],
        "uncertainty": revision.probability.model_dump(mode="json"),
        "supporting_evidence_refs": list(revision.supporting_evidence_refs),
        "contrary_evidence_refs": list(revision.contrary_evidence_refs),
        "challenge_receipt_id": revision.challenge_receipt_id,
        "challenge_completed": revision.challenge_completed,
        "review_id": revision.review_id,
        "review_state": revision.review_state.value,
        "review_authority": revision.review_authority.value,
        "rollout_eligible": revision.rollout_eligible,
        "causal_strength": revision.causal_strength.value,
        "causal_limit": "mechanistic_hypothesis_not_causal_fact",
        "branch_input_id": str(branch_input.input_id),
        "branch_input_applicable": branch_input.applicable,
        "unsupported_causality_error": causal_error,
        "provider_usage": revision.provider_usage.model_dump(mode="json"),
    }
    return belief, transition, proposal, revision


def _decision(kind: str, evidence_refs: list[str]) -> dict[str, Any]:
    if kind == "control":
        selected = "Keep the no-action monitoring baseline."
        alternatives = ["Disconnect active cooling", "Stage standby cooling first"]
    elif kind == "correction":
        selected = "Monitor active and standby cooling circuits."
        alternatives = ["Monitor only the active cooling circuit"]
    else:
        selected = "Disconnect active cooling with explicit temperature monitoring."
        alternatives = ["Keep the no-action baseline", "Stage standby cooling first"]
    return {
        "selected_option": selected,
        "scope": "Fjord Operations bounded cooling decision",
        "assumptions": ["The frozen belief projection remains the starting state"],
        "alternatives": alternatives,
        "reconsideration_conditions": ["A later observation contradicts the simulated consequence"],
        "evidence_refs": evidence_refs,
        "rationale": "Frozen provider-free Fjord Operations decision.",
        "decision_type": "direction",
    }


def _evidence_envelope(
    *,
    config: dict[str, Any],
    belief: dict[str, Any],
    transition: dict[str, Any],
    mode: str,
    suffix: str,
    control_task_id: str | None = None,
    correction_id: str | None = None,
    prior_receipt_id: str | None = None,
    wait_seconds: float = 2,
    question: str = "What happens if Fjord Operations disconnects the active cooling circuit?",
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "state_engine_mode": mode,
        "context_source": "projection",
        "as_of": belief["as_of"],
        "starting_projection_id": belief["projection_id"],
        "structured_decision": _decision(
            "correction" if correction_id else mode,
            [correction_id] if correction_id else [belief["evidence_pack_id"]],
        ),
    }
    if control_task_id:
        parameters["matched_control_task_id"] = control_task_id
    if suffix == "restart-interruption":
        parameters["restart_interruption"] = True
    if mode == "rollout":
        intervention_branch = (
            {
                "branch_id": f"branch:fjord-{suffix}-alternative",
                "kind": "alternative",
                "action": "Stage standby cooling before disconnecting active cooling.",
                "transition_hypothesis_ids": [transition["hypothesis_id"]],
            }
            if correction_id
            else {
                "branch_id": f"branch:fjord-{suffix}-action",
                "kind": "action",
                "action": "Disconnect active cooling.",
                "transition_hypothesis_ids": [transition["hypothesis_id"]],
            }
        )
        parameters["rollout"] = {
            "transition_revision_ids": [transition["revision_id"]],
            "horizon": config["scenario"]["horizon"],
            "max_steps": 2,
            "max_transitions": 1,
            "branches": [
                intervention_branch,
                {"branch_id": f"branch:fjord-{suffix}-no-action", "kind": "no_action"},
            ],
        }
        parameters["promotion_material"] = {
            "target_kind": "correction" if correction_id else "durable_conclusion",
            "origin_meaning": "human_correction" if correction_id else "grounded_reasoning_conclusion",
            "memory_meaning": "correction" if correction_id else "durable_conclusion",
            "content": (
                "Monitor both active and standby Fjord cooling circuits."
                if correction_id
                else "A disconnected active Fjord cooling circuit requires explicit temperature monitoring."
            ),
            "domain_path": "operations",
            "tags": ["fjord-operations", "cooling", "monitoring"],
        }
        if correction_id:
            parameters["correction_observation_id"] = correction_id
            parameters["prior_promotion_receipt_ids"] = [prior_receipt_id]
    return {
        "contract_version": "extension-invocation-v1",
        "extension_id": config["extension"]["extension_id"],
        "extension_version": config["extension"]["extension_version"],
        "action": "evidence-query",
        "workspace_id": config["scenario"]["workspace_id"],
        "question": question,
        "references": [
            {
                "namespace": "fjord-operations",
                "kind": "evidence_query",
                "id": f"query:fjord-{suffix}",
                "version": "1",
            }
        ],
        "parameters": parameters,
        "correlation_id": f"invocation:fjord-{suffix}",
        "idempotency_key": f"fjord-{suffix}-v1",
        "wait_seconds": wait_seconds,
    }


def _review_envelope(
    *,
    config: dict[str, Any],
    proposal_id: str,
    suffix: str,
) -> dict[str, Any]:
    reviewed_at = datetime.fromisoformat(config["scenario"]["as_of"].replace("Z", "+00:00")) + timedelta(
        seconds=30 if suffix == "correction" else 10
    )
    return {
        "contract_version": "extension-invocation-v1",
        "extension_id": config["extension"]["extension_id"],
        "extension_version": config["extension"]["extension_version"],
        "action": "promotion-review",
        "workspace_id": config["scenario"]["workspace_id"],
        "question": "Apply the authenticated Fjord Operations promotion disposition.",
        "references": [
            {
                "namespace": "fjord-operations",
                "kind": "promotion_proposal",
                "id": proposal_id,
                "version": "ace.grounded-state.promotion-proposal/v1",
            }
        ],
        "parameters": {
            "disposition": "accepted",
            "rationale": "Authenticated frozen Fjord Operations acceptance.",
            "reviewed_at": reviewed_at.isoformat(),
        },
        "correlation_id": f"invocation:fjord-{suffix}-review",
        "idempotency_key": f"fjord-{suffix}-review-v1",
        "wait_seconds": 2,
    }


async def _terminal(client: httpx.AsyncClient, task: dict[str, Any]) -> dict[str, Any]:
    if task.get("status") in TERMINAL_TASK_STATES:
        return task
    for _ in range(200):
        response = await client.get(f"/tasks/{task['id']}")
        response.raise_for_status()
        task = response.json()
        if task.get("status") in TERMINAL_TASK_STATES:
            return task
        await asyncio.sleep(0.05)
    return task


async def _post_task(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
    *,
    wait_terminal: bool = True,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.post(path, json=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:2_000]}") from exc
    task = response.json()
    if wait_terminal:
        task = await _terminal(client, task)
    return task, (time.perf_counter() - started) * 1000


async def _receipt_for_proposal(pool, *, product_id: str, proposal_id: str) -> PromotionReceiptV1:
    receipts = await PromotionService(pool).store.list_records(PromotionReceiptV1, product_id=product_id)
    matches = [item for item in receipts if item.proposal_id == proposal_id]
    if len(matches) != 1:
        raise RuntimeError("promotion review did not produce exactly one receipt")
    return matches[0]


async def _reconcile_outcomes(
    pool,
    *,
    product_id: str,
    rollout_id: str,
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
    observed_at = predicted.latest_at
    observed_pack = BoundedEvidencePackV1.model_validate(
        {
            **source_pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
            "as_of": observed_at,
            "query_hash": canonical_hash("fjord-frozen-later-outcome-v1"),
            "candidate_receipt_id": "candidate_receipt:fjord_later_outcome_v1",
            "candidate_receipt_hash": canonical_hash("fjord-later-outcome-receipt-v1"),
        }
    )
    await service.belief_store.persist(observed_pack)
    common = {
        "product_id": product_id,
        "rollout_revision_id": str(rollout.rollout_revision_id),
        "rollout_revision_hash": str(rollout.rollout_revision_hash),
        "predicted_outcome_id": str(predicted.outcome_id),
        "branch_id": action.branch_id,
        "observed_at": observed_at,
        "evidence_pack_id": str(observed_pack.pack_id),
        "evidence_pack_hash": str(observed_pack.pack_hash),
        "evidence_refs": (observed_pack.items[0].endpoint.record_id,),
        "authority": ReviewAuthority.DETERMINISTIC_POLICY,
    }
    incomplete = RolloutOutcomeObservationV1(
        **common,
        observer_ref="policy:fjord-incomplete-observation-control/v1",
        rationale="The observer reported no compatible assignment; reconciliation must remain incomplete.",
    )
    incomplete_receipt = await service.reconcile_and_persist(
        incomplete,
        reconciled_at=observed_at + timedelta(seconds=1),
    )
    matched = RolloutOutcomeObservationV1(
        **common,
        observed_assignment=predicted.expected_assignment,
        foresight_prediction_ref="decision_prediction:fjord-product-journey-v1",
        foresight_resolution_ref="prediction_outcome:fjord-product-journey-v1",
        observer_ref="policy:fjord-frozen-observed-outcome/v1",
        rationale="The fictional later observation matches the frozen action consequence.",
    )
    matched_receipt = await service.reconcile_and_persist(
        matched,
        reconciled_at=observed_at + timedelta(seconds=2),
    )
    replayed = await service.replay_rollout(rollout_id, product_id=product_id)
    return {
        "observation_id": str(matched.observation_id),
        "observation_hash": str(matched.observation_hash),
        "observed_evidence_pack_id": str(observed_pack.pack_id),
        "observed_evidence_pack_hash": str(observed_pack.pack_hash),
        "incomplete_observation_id": str(incomplete.observation_id),
        "incomplete_receipt_id": str(incomplete_receipt.receipt_id),
        "incomplete_disposition": incomplete_receipt.disposition.value,
        "incomplete_degraded_reasons": list(incomplete_receipt.degraded_reasons),
        "matched_receipt_id": str(matched_receipt.receipt_id),
        "matched_receipt_hash": str(matched_receipt.receipt_hash),
        "matched_disposition": matched_receipt.disposition.value,
        "matched_score": matched_receipt.score,
        "original_rollout_preserved": replayed.rollout_revision_hash == rollout.rollout_revision_hash,
        "record_meanings": sorted(
            {
                consequence.record_meaning
                for execution in rollout.execution_receipts
                for consequence in execution.consequences
            }
        ),
    }


async def _run_fresh_client(
    processes: ProcessSet,
    *,
    product_id: str,
    command: str,
) -> dict[str, Any]:
    output = processes.work_dir / f"thin-client-{command}.json"
    started = time.perf_counter()
    completed = await asyncio.to_thread(
        _run_checked,
        [
            processes.python,
            "-m",
            "evaluations.state_engine_product_journey_client",
            command,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=processes.env(product_id),
        timeout=60,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    result["process_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    result["stderr"] = completed.stderr[-500:]
    return result


def _provider_usage(tasks: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    calls = sum(int((task.get("model_calls") or {}).get("actual") or 0) for task in tasks)
    retries = sum(int((task.get("model_calls") or {}).get("retry_count") or 0) for task in tasks)
    input_tokens = sum(int((task.get("token_usage") or {}).get("input_tokens") or 0) for task in tasks)
    output_tokens = sum(int((task.get("token_usage") or {}).get("output_tokens") or 0) for task in tasks)
    return {
        "route": config["provider_budget"]["route"],
        "exact_model": config["provider_budget"]["exact_model"],
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": 0,
        "cost_usd": 0.0,
        "retries": retries,
        "failures": [],
        "billing_semantics": "deterministic_no_model_call",
    }


def _latency_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    p50 = ordered[max(0, math.ceil(len(ordered) * 0.5) - 1)]
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {
        "count": len(ordered),
        "p50": round(p50, 3),
        "p95": round(p95, 3),
        "max": round(max(ordered), 3),
    }


def _store_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


async def _exercise_restart_interruption(
    processes: ProcessSet,
    *,
    config: dict[str, Any],
    belief: dict[str, Any],
    transition: dict[str, Any],
) -> dict[str, Any]:
    product_id = config["scenario"]["product_id"]
    headers = {"Authorization": f"Bearer {processes.token(product_id)}"}
    envelope = _evidence_envelope(
        config=config,
        belief=belief,
        transition=transition,
        mode="control",
        suffix="restart-interruption",
        wait_seconds=0,
        question="Fjord restart interruption acceptance: hold this task until the runtime is stopped.",
    )
    async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
        predecessor, _latency = await _post_task(
            client,
            "/extension-invocations",
            envelope,
            wait_terminal=False,
        )
        deadline = time.perf_counter() + 10
        while time.perf_counter() < deadline and not processes.interrupt_marker.exists():
            await asyncio.sleep(0.05)
        if not processes.interrupt_marker.exists():
            raise RuntimeError("restart-interruption task did not enter the held orchestration path")
    await processes.stop_runtime()
    await processes.stop_db()
    restart_started = time.perf_counter()
    await processes.start_db("restart-interruption")
    restarted = await processes.start_runtime(product_id=product_id, label="restart-interruption")
    restart_seconds = time.perf_counter() - restart_started
    async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
        prior_response = await client.get(f"/tasks/{predecessor['id']}")
        prior_response.raise_for_status()
        prior = prior_response.json()
        successor, _latency = await _post_task(
            client,
            f"/extension-invocations/{predecessor['id']}/resume",
            {"reason": "fresh-process product-journey recovery", "policy_version": "fjord-retry-v1"},
        )
    return {
        "predecessor_task_id": predecessor["id"],
        "predecessor_status_after_restart": prior["status"],
        "successor_task_id": successor["id"],
        "successor_status": successor["status"],
        "attempt_number": (successor.get("extension_invocation_receipt") or {}).get("attempt_number"),
        "restart_seconds": round(restart_seconds, 6),
        "processes": restarted,
        "passed": prior["status"] == "degraded" and successor["status"] == "completed",
    }


async def _run_journey(
    *,
    config_path: Path,
    output: Path | None,
    markdown_output: Path | None,
    work_dir: Path,
    surreal: str,
) -> dict[str, Any]:
    config = load_product_journey_config(config_path)
    productized = config["contract_version"] == PRODUCTIZED_CONFIG_CONTRACT
    started_at = datetime.now(UTC)
    work_dir.mkdir(parents=True, exist_ok=True)
    clean_python, install = _install_clean_extension(work_dir, config)
    processes, schema = await _verify_schema_paths(
        python=clean_python,
        surreal=surreal,
        work_dir=work_dir,
        config=config,
    )
    product_id = config["scenario"]["product_id"]
    foreign_product_id = config["scenario"]["foreign_product_id"]
    all_tasks: list[dict[str, Any]] = []
    task_latencies: list[float] = []
    unexpected_failures: list[str] = []
    try:
        initial_runtime = await processes.start_runtime(product_id=product_id, label="initial-runtime")
        loaded_names = set(initial_runtime["api_health"].get("loaded_extensions") or [])
        headers = {"Authorization": f"Bearer {processes.token(product_id)}"}
        foreign_headers = {"Authorization": f"Bearer {processes.token(foreign_product_id)}"}
        async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
            product_state_capabilities_response = await client.get("/product-state/capabilities")
            product_state_capabilities_response.raise_for_status()
            product_state_capabilities = product_state_capabilities_response.json()
            db, pool = await _connect(processes.db_url, processes.namespace, processes.database)
            try:
                await db.query(
                    "UPSERT type::record('product', $product_key) SET name = 'Fjord Operations', tenant = tenant:test, settings = {}",
                    {"product_key": product_id.split(":", 1)[1]},
                )
                ingestion, pack = await _ingest_and_replay(
                    pool,
                    config,
                    client=client,
                    product_state_capabilities=product_state_capabilities,
                )
                belief, transition, transition_proposal, transition_revision = await _build_belief_and_transition(
                    pool,
                    pack=pack,
                    config=config,
                )
            finally:
                await db.close()
            capabilities_response = await client.get("/extension-invocations/capabilities")
            capabilities_response.raise_for_status()
            capabilities = capabilities_response.json()["capabilities"]
            fjord_capabilities = [
                item for item in capabilities if item["extension_id"] == config["extension"]["extension_id"]
            ]
            control, control_ms = await _post_task(
                client,
                "/extension-invocations",
                _evidence_envelope(
                    config=config,
                    belief=belief,
                    transition=transition,
                    mode="control",
                    suffix="control",
                ),
            )
            rollout_task, rollout_ms = await _post_task(
                client,
                "/extension-invocations",
                _evidence_envelope(
                    config=config,
                    belief=belief,
                    transition=transition,
                    mode="rollout",
                    suffix="initial",
                    control_task_id=control["id"],
                ),
            )
            runtime = rollout_task.get("state_engine_runtime") or {}
            review_task, review_ms = await _post_task(
                client,
                "/extension-invocations",
                _review_envelope(
                    config=config,
                    proposal_id=runtime["promotion_proposal_id"],
                    suffix="initial",
                ),
            )
        all_tasks.extend((control, rollout_task, review_task))
        task_latencies.extend((control_ms, rollout_ms, review_ms))

        db, pool = await _connect(processes.db_url, processes.namespace, processes.database)
        try:
            initial_receipt = await _receipt_for_proposal(
                pool,
                product_id=product_id,
                proposal_id=runtime["promotion_proposal_id"],
            )
            initial_review = await PromotionService(pool).store.require(
                PromotionReviewV1,
                initial_receipt.review_id,
                product_id=product_id,
            )
            reconciliation = await _reconcile_outcomes(
                pool,
                product_id=product_id,
                rollout_id=runtime["rollout_revision_id"],
            )
        finally:
            await db.close()

        await processes.stop_runtime()
        await processes.stop_db()
        restart_started = time.perf_counter()
        await processes.start_db("first-continuity-restart")
        first_restarted = await processes.start_runtime(product_id=product_id, label="first-continuity-restart")
        first_restart_seconds = time.perf_counter() - restart_started
        later = await _run_fresh_client(processes, product_id=product_id, command="later-use")
        all_tasks.append(later["task"])
        task_latencies.append(float(later["task_latency_ms"]))
        correction_id = later["correction"]["correction"]["correction_id"]

        async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
            persisted = await client.get(f"/tasks/{rollout_task['id']}")
            persisted.raise_for_status()
            async with httpx.AsyncClient(
                base_url=processes.api_url,
                headers=foreign_headers,
                timeout=15,
            ) as foreign_client:
                foreign_task = await foreign_client.get(f"/tasks/{rollout_task['id']}")
            correction_task, correction_ms = await _post_task(
                client,
                "/extension-invocations",
                _evidence_envelope(
                    config=config,
                    belief=belief,
                    transition=transition,
                    mode="rollout",
                    suffix="correction",
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
                    config=config,
                    proposal_id=correction_runtime["promotion_proposal_id"],
                    suffix="correction",
                ),
            )
        all_tasks.extend((correction_task, correction_review))
        task_latencies.extend((correction_ms, correction_review_ms))

        db, pool = await _connect(processes.db_url, processes.namespace, processes.database)
        try:
            correction_receipt = await _receipt_for_proposal(
                pool,
                product_id=product_id,
                proposal_id=correction_runtime["promotion_proposal_id"],
            )
            authoritative = await PromotionService(pool).retrieve(product_id=product_id, domain_path="operations")
            foreign_memories = await PromotionService(pool).retrieve(
                product_id=foreign_product_id,
                domain_path="operations",
            )
            foreign_records = await GroundedStateCandidateService(pool).records(product_id=foreign_product_id)
            simulation_row = parse_one(
                await db.query(
                    "SELECT count() AS count FROM observation WHERE id = <record>$rollout GROUP ALL",
                    {"rollout": runtime["rollout_revision_id"]},
                )
            )
        finally:
            await db.close()

        await processes.stop_runtime()
        await processes.stop_db()
        second_restart_started = time.perf_counter()
        await processes.start_db("post-correction-restart")
        second_restarted = await processes.start_runtime(product_id=product_id, label="post-correction-restart")
        second_restart_seconds = time.perf_counter() - second_restart_started
        post = await _run_fresh_client(processes, product_id=product_id, command="post-correction")
        all_tasks.append(post["task"])
        task_latencies.append(float(post["task_latency_ms"]))
        interruption = await _exercise_restart_interruption(
            processes,
            config=config,
            belief=belief,
            transition=transition,
        )

        db, pool = await _connect(processes.db_url, processes.namespace, processes.database)
        try:
            stale_at = datetime.fromisoformat(config["scenario"]["as_of"].replace("Z", "+00:00")) + timedelta(days=2)
            stale_revision = await TransitionHypothesisService(pool).resolve_and_persist(
                transition_proposal,
                disposition=TransitionReviewState.STALE,
                authority=ReviewAuthority.DETERMINISTIC_POLICY,
                reviewer_ref="policy:fjord-stale-transition-control/v1",
                reviewed_at=stale_at,
                rationale="The frozen negative control explicitly marks the hypothesis stale.",
                prior_revision=transition_revision,
                stale_at=stale_at,
            )
            stale_input = await TransitionHypothesisService(pool).freeze_branch_input(
                str(stale_revision.revision_id),
                product_id=product_id,
            )
        finally:
            await db.close()

        later_use_receipt = later["task"].get("intelligence_use_receipt") or {}
        post_use_receipt = post["task"].get("intelligence_use_receipt") or {}
        rollout_receipt = rollout_task.get("extension_invocation_receipt") or {}
        rollout_record = await _load_rollout_record(processes, product_id, runtime["rollout_revision_id"])
        correction_rollout_record = await _load_rollout_record(
            processes,
            product_id,
            correction_runtime["rollout_revision_id"],
        )
        branch_kinds = sorted(
            {
                item["branch_kind"]
                for record in (rollout_record, correction_rollout_record)
                for item in record["execution_receipts"]
            }
        )
        source_authority = bool(
            ((rollout_receipt.get("outcome") or {}).get("data") or {}).get("source_instruction_authority")
        )
        decision_receipt = rollout_task.get("decision_receipt") or {}
        async with httpx.AsyncClient(base_url=processes.api_url, headers=headers, timeout=15) as client:
            landscape_response = await client.get("/product/landscape")
            landscape_response.raise_for_status()
            landscape = landscape_response.json()
        inspected_state = landscape.get("state_engine") or {}
        inspected_tasks = (landscape.get("work") or {}).get("tasks") or []
        inspection_checks = {
            "ingestions": bool(inspected_state.get("ingestions")),
            "belief_projections": bool(inspected_state.get("belief_projections")),
            "transition_revisions": bool(inspected_state.get("transition_revisions")),
            "reasoning_evidence_packs": bool(inspected_state.get("reasoning_evidence_packs")),
            "reasoning_use_receipts": bool(inspected_state.get("reasoning_use_receipts")),
            "consequence_rollouts": bool(inspected_state.get("consequence_rollouts")),
            "promotion_receipts": bool((inspected_state.get("promotion") or {}).get("receipts")),
            "decision_receipt": any(task.get("decision_receipt") for task in inspected_tasks),
            "deliberation_receipt": any(task.get("deliberation_receipt") for task in inspected_tasks),
            "intelligence_use_receipt": any(task.get("intelligence_use_receipt") for task in inspected_tasks),
        }
        failure_cases = [
            {
                "case": "unavailable_evidence",
                "passed": ingestion["unavailable_evidence_selected"] == 0,
                "outcome": "foreign-scope query returned an explicit empty bounded evidence pack",
            },
            {
                "case": "unsupported_causality",
                "passed": "human authority" in transition["unsupported_causality_error"],
                "outcome": transition["unsupported_causality_error"],
            },
            {
                "case": "product_isolation",
                "passed": (
                    foreign_task.status_code == 404
                    and not foreign_memories
                    and not foreign_records
                    and ingestion["product_isolation"]
                ),
                "outcome": "foreign task read returned 404 and foreign evidence/memory reads returned no rows",
            },
            {
                "case": "stale_state",
                "passed": not stale_input.applicable and "transition_stale" in stale_input.degraded_reasons,
                "outcome": "stale transition revision remained non-applicable with transition_stale degradation",
            },
            {
                "case": "restart_interruption",
                "passed": interruption["passed"],
                "outcome": "interrupted attempt degraded after restart and resumed as an immutable successor",
            },
            {
                "case": "incomplete_reconciliation",
                "passed": (
                    reconciliation["incomplete_disposition"] == "unresolved"
                    and "observed_assignment_unavailable" in reconciliation["incomplete_degraded_reasons"]
                ),
                "outcome": "missing observed assignment remained unresolved and unscored",
            },
        ]
        provider_usage = _provider_usage(all_tasks, config)
        actual_tools = later["thin_mcp_tools"]
        restart_max = max(first_restart_seconds, second_restart_seconds, interruption["restart_seconds"])
        checks = {
            "clean_extension_install_and_discovery": (
                config["extension"]["entry_point"] in install["loaded"]
                and config["extension"]["entry_point"] in loaded_names
                and len(fjord_capabilities) == 2
            ),
            "schema_zero_and_upgrade": (
                schema["schema_zero"]["version"] == config["acceptance"]["schema_head"]
                and schema["upgrade"]["from_version"] == config["acceptance"]["supported_upgrade_from"]
                and schema["upgrade"]["to_version"] == config["acceptance"]["schema_head"]
                and schema["upgrade"]["sentinel_preserved"]
            ),
            "ingestion_replay_lineage_counts_isolation": all(
                ingestion[key] for key in ("exact_replay", "counts_reconciled", "version_lineage", "product_isolation")
            ),
            "product_state_supported_ingestion_surface": (
                product_state_capabilities.get("contract_version") == "ace.product-state.capabilities/v1"
                and ingestion["contract_version"] == "ace.product-state.ingestion/v1"
                and ingestion["extension_version"] == config["extension"]["extension_version"]
                and ingestion["authority"]["product_scope"] == "authenticated_token_only"
            ),
            "product_state_inspection_connects_receipts": all(inspection_checks.values()),
            "five_time_meanings_separate": ingestion["distinct_non_event_times"] == 4,
            "belief_state_complete": set(config["acceptance"]["required_belief_states"]) <= set(belief["statuses"]),
            "transition_inspectable_and_causally_bounded": (
                transition["rollout_eligible"]
                and transition["challenge_completed"]
                and bool(transition["unsupported_causality_error"])
            ),
            "three_way_rollout_and_decision": (
                set(branch_kinds) == set(config["acceptance"]["required_rollout_branches"])
                and bool(decision_receipt.get("decision_id"))
                and runtime.get("decision_material_count", 0) >= 1
            ),
            "source_data_has_no_instruction_authority": not source_authority,
            "immutable_outcome_reconciliation": (
                reconciliation["matched_disposition"] == "matched" and reconciliation["original_rollout_preserved"]
            ),
            "restart_fresh_client_material_use": (
                persisted.json()["id"] == rollout_task["id"]
                and bool(later_use_receipt.get("material_intelligence_ids"))
            ),
            "correction_supersession_and_later_use": (
                str(initial_receipt.receipt_id) in correction_receipt.supersedes_receipt_ids
                and len(authoritative) == 1
                and bool(post_use_receipt.get("material_intelligence_ids"))
            ),
            "simulation_never_observation": int((simulation_row or {}).get("count", 0)) == 0,
            "failure_matrix": all(item["passed"] for item in failure_cases),
            "provider_budget": (
                provider_usage["calls"] == provider_usage["input_tokens"] == provider_usage["output_tokens"] == 0
                and provider_usage["retries"] == 0
                and provider_usage["cost_usd"] == 0.0
            ),
            "thin_mcp_exact": actual_tools == config["acceptance"]["thin_mcp_tools"],
            "restart_budget": restart_max <= config["acceptance"]["maximum_restart_seconds"],
            "no_benefit_claim": not bool(
                (later_use_receipt.get("impact") or {}).get("beneficial_impact_supported")
                or (post_use_receipt.get("impact") or {}).get("beneficial_impact_supported")
            ),
        }
        journey_steps = [
            {"ordinal": 1, "name": "install and discover ACE plus product extension", "status": "passed"},
            {
                "ordinal": 2,
                "name": "ingest bounded public-safe temporal corpus through Product State API",
                "status": "passed",
            },
            {
                "ordinal": 3,
                "name": "replay ingestion and reconcile identity, lineage, counts, and scope",
                "status": "passed",
            },
            {"ordinal": 4, "name": "freeze five-meaning as-of belief projection", "status": "passed"},
            {"ordinal": 5, "name": "challenge and review inspectable transition hypothesis", "status": "passed"},
            {"ordinal": 6, "name": "compare action, no-action, and named alternative rollouts", "status": "passed"},
            {"ordinal": 7, "name": "persist structured decision and I3 use receipt", "status": "passed"},
            {"ordinal": 8, "name": "capture and reconcile incomplete then matched later outcomes", "status": "passed"},
            {"ordinal": 9, "name": "accept correction and append-only supersession lineage", "status": "passed"},
            {"ordinal": 10, "name": "restart database, API, and worker; invoke fresh thin client", "status": "passed"},
            {"ordinal": 11, "name": "exercise honest failure and degraded cases", "status": "passed"},
            {
                "ordinal": 12,
                "name": "inspect the integrated receipt chain through the Living Product Graph",
                "status": "passed",
            },
            {"ordinal": 13, "name": "reverify unchanged eleven-tool public MCP boundary", "status": "passed"},
        ]
        completed_at = datetime.now(UTC)
        decisions = {"K1": "passed", "K2": "passed", "K3": "passed"}
        if productized:
            decisions["Productized State"] = "passed"
        result: dict[str, Any] = {
            "contract_version": PRODUCTIZED_RESULT_CONTRACT if productized else STATE_ENGINE_RESULT_CONTRACT,
            "acceptance_id": config["acceptance_id"],
            "status": "passed" if all(checks.values()) else "failed",
            "decisions": decisions,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "fixture": {
                "config_path": str(config_path.relative_to(ROOT)),
                "config_sha256": product_journey_config_hash(config_path),
                "fixture_status": config["fixture_status"],
                "corpus_path": config["extension"]["corpus_path"],
                "corpus_sha256": config["extension"]["corpus_sha256"],
            },
            "environment": {
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "surreal_binary": surreal,
                "surreal_version": _surreal_version(surreal),
                "source_revision": _source_revision(),
                "topology": "one database, one API, one worker, bounded synchronous clients",
            },
            "extension": {
                "distribution": install["distribution"],
                "distribution_version": install["version"],
                "extension_id": config["extension"]["extension_id"],
                "extension_version": config["extension"]["extension_version"],
                "entry_point": config["extension"]["entry_point"],
                "entry_point_discovered": config["extension"]["entry_point"] in install["entry_points"],
                "clean_install": True,
                "loaded_extensions": sorted(loaded_names),
                "adapter": [config["extension"]["extension_id"], config["extension"]["adapter_name"]],
                "capabilities": [
                    {
                        key: item.get(key)
                        for key in ("extension_id", "extension_version", "action", "input_contract", "output_contract")
                    }
                    for item in fjord_capabilities
                ],
            },
            "schema": schema,
            "ingestion": ingestion,
            "belief_state": belief,
            "transition": transition,
            "rollout": {
                "control_task_id": control["id"],
                "task_id": rollout_task["id"],
                "task_status": rollout_task["status"],
                "rollout_revision_id": runtime["rollout_revision_id"],
                "rollout_revision_hash": runtime["rollout_revision_hash"],
                "branch_kinds": branch_kinds,
                "decision_receipt_id": decision_receipt.get("decision_id"),
                "reasoning_use_receipt_id": runtime["reasoning_use_receipt_id"],
                "decision_material_count": runtime.get("decision_material_count", 0),
                "source_instruction_authority": source_authority,
                "record_meanings": reconciliation["record_meanings"],
            },
            "promotion": {
                "initial_proposal_id": runtime["promotion_proposal_id"],
                "initial_receipt_id": str(initial_receipt.receipt_id),
                "initial_receipt_hash": str(initial_receipt.receipt_hash),
                "initial_memory_id": initial_receipt.memory_id,
                "authority": initial_review.authority.value,
                "disposition": initial_receipt.disposition.value,
            },
            "reconciliation": reconciliation,
            "restart": {
                "initial_processes": initial_runtime,
                "first_restart_processes": first_restarted,
                "second_restart_processes": second_restarted,
                "first_restart_seconds": round(first_restart_seconds, 6),
                "second_restart_seconds": round(second_restart_seconds, 6),
                "interruption_restart_seconds": interruption["restart_seconds"],
                "same_task_identity": persisted.json()["id"] == rollout_task["id"],
                "interruption": interruption,
            },
            "later_use": {
                "before_correction_task_id": later["task"]["id"],
                "after_correction_task_id": post["task"]["id"],
                "before_correction_material_ids": later_use_receipt.get("material_intelligence_ids") or [],
                "after_correction_material_ids": post_use_receipt.get("material_intelligence_ids") or [],
                "beneficial_impact_supported": bool(
                    (later_use_receipt.get("impact") or {}).get("beneficial_impact_supported")
                    or (post_use_receipt.get("impact") or {}).get("beneficial_impact_supported")
                ),
                "fresh_client_pids": [later["process_pid"], post["process_pid"]],
            },
            "correction": {
                "observation_id": correction_id,
                "task_id": correction_task["id"],
                "proposal_id": correction_runtime["promotion_proposal_id"],
                "receipt_id": str(correction_receipt.receipt_id),
                "receipt_hash": str(correction_receipt.receipt_hash),
                "memory_id": correction_receipt.memory_id,
                "supersedes_initial": str(initial_receipt.receipt_id) in correction_receipt.supersedes_receipt_ids,
                "authoritative_memory_ids": [item.memory_id for item in authoritative],
                "authoritative_contents": [item.content for item in authoritative],
            },
            "failure_cases": failure_cases,
            "surfaces": {
                "adapter_registry": "Registry.register_grounded_state_adapter",
                "product_state_http": [
                    "GET /product-state/capabilities",
                    "POST /product-state/ingestions",
                    "GET /product/landscape",
                ],
                "product_state_cli": [
                    "ace state capabilities",
                    "ace state ingest",
                    "ace state invoke",
                    "ace state correct",
                    "ace state inspect",
                ],
                "extension_invocation_http": [
                    "GET /extension-invocations/capabilities",
                    "POST /extension-invocations",
                    "POST /extension-invocations/{task_id}/resume",
                    "GET /tasks/{task_id}",
                ],
                "thin_mcp_tools": actual_tools,
                "thin_mcp_tool_count": later["thin_mcp_tool_count"],
                "broad_engine_mcp_used": False,
            },
            "product_state_inspection": {
                "contract_version": "ace.product-state.inspection/v1",
                "snapshot_id": landscape.get("snapshot_id"),
                "projection_state": landscape.get("projection_state"),
                "ingestion_receipts": len(inspected_state.get("ingestions") or []),
                "belief_projections": len(inspected_state.get("belief_projections") or []),
                "transition_revisions": len(inspected_state.get("transition_revisions") or []),
                "reasoning_evidence_packs": len(inspected_state.get("reasoning_evidence_packs") or []),
                "reasoning_use_receipts": len(inspected_state.get("reasoning_use_receipts") or []),
                "consequence_rollouts": len(inspected_state.get("consequence_rollouts") or []),
                "promotion_receipts": len((inspected_state.get("promotion") or {}).get("receipts") or []),
                "tasks_with_decision_receipt": sum(bool(item.get("decision_receipt")) for item in inspected_tasks),
                "tasks_with_deliberation_receipt": sum(
                    bool(item.get("deliberation_receipt")) for item in inspected_tasks
                ),
                "tasks_with_intelligence_use_receipt": sum(
                    bool(item.get("intelligence_use_receipt")) for item in inspected_tasks
                ),
                "authority": landscape.get("authority"),
                "checks": inspection_checks,
            },
            "provider_usage": provider_usage,
            "resource_use": {
                "duration_seconds": round((completed_at - started_at).total_seconds(), 6),
                "task_latency_ms": _latency_summary(task_latencies),
                "store_bytes": _store_bytes(processes.store),
                "stable_record_count": ingestion["persisted_semantic_records"],
                "evidence_selected": ingestion["evidence_selected"],
                "restart_seconds_max": round(restart_max, 6),
                "unexpected_failures": unexpected_failures,
            },
            "journey_steps": journey_steps,
            "checks": checks,
            "limitations": config["limitations"],
        }
        result["acceptance_hash"] = acceptance_hash(result)
        validate_product_journey_result(result, config=config)
        if output:
            _write_json(output, result)
        if markdown_output:
            markdown_output.parent.mkdir(parents=True, exist_ok=True)
            markdown_output.write_text(render_product_journey_markdown(result, config=config), encoding="utf-8")
        return result
    except Exception as exc:
        unexpected_failures.append(f"{type(exc).__name__}:{str(exc)[:500]}")
        raise
    finally:
        await processes.close()


async def _load_rollout_record(processes: ProcessSet, product_id: str, rollout_id: str) -> dict[str, Any]:
    db, pool = await _connect(processes.db_url, processes.namespace, processes.database)
    try:
        rollout = await ConsequenceRolloutService(pool).replay_rollout(rollout_id, product_id=product_id)
        return rollout.model_dump(mode="json")
    finally:
        await db.close()


def _surreal_version(surreal: str) -> str:
    completed = subprocess.run([surreal, "version"], capture_output=True, text=True, timeout=10)
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _source_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


async def _main_async(args) -> int:
    config_path = Path(args.config).resolve()
    if args.command == "freeze-check":
        config = load_product_journey_config(config_path)
        result = {
            "status": "passed",
            "acceptance_id": config["acceptance_id"],
            "config_sha256": product_journey_config_hash(config_path),
            "corpus_sha256": config["extension"]["corpus_sha256"],
            "fixture_status": config["fixture_status"],
            "extension_id": config["extension"]["extension_id"],
            "product_id": config["scenario"]["product_id"],
            "required_belief_states": config["acceptance"]["required_belief_states"],
            "required_failure_cases": config["acceptance"]["required_failure_cases"],
            "thin_mcp_tool_count": len(config["acceptance"]["thin_mcp_tools"]),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    surreal = args.surreal_bin or shutil.which("surreal")
    if not surreal:
        raise RuntimeError("SurrealDB executable is required for the real restart journey")
    if args.work_dir:
        result = await _run_journey(
            config_path=config_path,
            output=Path(args.output).resolve() if args.output else None,
            markdown_output=Path(args.markdown_output).resolve() if args.markdown_output else None,
            work_dir=Path(args.work_dir).resolve(),
            surreal=surreal,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="ace-fjord-product-journey-") as temp:
            result = await _run_journey(
                config_path=config_path,
                output=Path(args.output).resolve() if args.output else None,
                markdown_output=Path(args.markdown_output).resolve() if args.markdown_output else None,
                work_dir=Path(temp),
                surreal=surreal,
            )
    if not args.output:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze-check")
    run = subparsers.add_parser("run")
    run.add_argument("--output")
    run.add_argument("--markdown-output")
    run.add_argument("--work-dir")
    run.add_argument("--surreal-bin", default=shutil.which("surreal"))
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(_main_async(_parser().parse_args())))


if __name__ == "__main__":
    main()
