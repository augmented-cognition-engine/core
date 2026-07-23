"""Fresh-process HTTP/MCP persistence proof for I1, I2, I3, and F1 closeout.

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


async def _seed_interrupted_extension_invocation(db_url: str, source_task_id: str) -> str:
    """Clone durable invocation coordinates into a prior-runtime running attempt."""
    interrupted_id = "task:i1extensioninterrupted"
    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        rows = await db.query(
            "SELECT extension_invocation FROM ONLY <record>$source",
            {"source": source_task_id},
        )
        row = rows if isinstance(rows, dict) else rows[0]
        assert isinstance(row.get("extension_invocation"), dict)
        await db.query(
            "UPSERT <record>$task SET "
            "product = product:i1restart, workspace = workspace:default, user = user:i1restart, "
            "description = 'Interrupted extension invocation', source = 'direct', status = 'running', "
            "contract_version = 'async-receipt-v1', runtime_id = 'prior-runtime', "
            "extension_invocation = $extension_invocation, accepted_at = time::now(), updated_at = time::now()",
            {
                "task": interrupted_id,
                "extension_invocation": row["extension_invocation"],
            },
        )
        return interrupted_id
    finally:
        await db.close()


async def _seed_intervention_prediction(db_url: str, decision_id: str) -> str:
    from core.engine.foresight.contracts import build_comparator_plan

    prediction_id = "decision_prediction:i1intervention"
    comparator_plan = build_comparator_plan(
        {
            "comparator_type": "phased_rollout",
            "assignment_design": "matched",
            "feasibility": "conditional",
            "feasibility_reason": "The restart fixture can preserve delayed exposure.",
            "required_conditions": ["The delayed fixture cohort remains safe"],
            "assignment_unit": "fixture cohort",
            "allocation": "Stagger two deterministic fixture cohorts",
            "minimum_duration_days": 7,
            "guardrails": ["Stop if restart continuity degrades"],
            "measurements": [
                {
                    "capability_id": "restart-continuity",
                    "baseline_source": "Pre-restart fixture score",
                    "outcome_source": "Post-restart fixture score",
                    "cadence": "per restart",
                }
            ],
        },
        consequences=[
            {
                "target": {
                    "entity_id": "restart-continuity",
                    "metric": "capability_quality",
                    "unit": "score_delta",
                }
            }
        ],
        horizon_days=30,
    )
    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        await db.query(
            "UPSERT decision_prediction:i1intervention SET "
            "decision = <record>$decision, product = product:i1restart, "
            "archetype = 'executor', discipline = 'general', horizon_days = 30, "
            "expected_changes = [{ capability_id: 'restart-continuity', score_delta: 0.1f }], "
            "leading_indicators = ['Restart continuity remains visible'], "
            "falsification_condition = 'Restart continuity disappears', "
            "comparator_plan_version = 'ace.foresight.comparator-plan/v1', "
            "comparator_plan = $comparator_plan, comparator_plan_status = 'proposed', "
            "closed = false, resolution_status = 'open', created_at = time::now()",
            {"decision": decision_id, "comparator_plan": comparator_plan},
        )
        return prediction_id
    finally:
        await db.close()


async def _seed_f1_measurement_prediction(db_url: str, decision_id: str) -> tuple[str, str]:
    """Seed one fully scoped continuous F1 forecast without making a model call."""
    from core.engine.foresight.contracts import build_forecast_contract

    prediction_id = "decision_prediction:f1measurement"
    raw = {
        "horizon_days": 30,
        "applicability_conditions": ["The deterministic F1 fixture is active"],
        "no_action_baseline": "Restart continuity remains at its baseline without the intervention.",
        "compared_alternatives": ["Keep both fixture cohorts unexposed"],
        "expected_changes": [
            {
                "capability_id": "restart-continuity",
                "score_delta": 0.10,
                "lower_bound": 0.00,
                "upper_bound": 0.20,
                "interval_coverage": 0.80,
                "probability": 0.70,
                "order": 1,
                "lag_days": 30,
                "mechanism": "The intervention preserves state across a process restart.",
                "assumptions": ["The deterministic fixture remains comparable"],
                "dependencies": ["Both fixture cohorts emit the same metric"],
                "confounders": ["Host-level timing variance"],
                "evidence_refs": ["test:f1:forecast"],
            }
        ],
        "primary_risk": "The cohort comparison may not remain stable.",
        "leading_indicators": ["Restart continuity remains visible"],
        "falsification_condition": "The intervention cohort does not outperform the comparator.",
        "comparator_plan": {
            "comparator_type": "holdout",
            "assignment_design": "matched",
            "comparator_label": "Unexposed deterministic fixture cohort",
            "feasibility": "conditional",
            "feasibility_reason": "The disposable fixture can preserve two explicit cohorts.",
            "required_conditions": ["The operator confirms both fixture cohorts are safe"],
            "assignment_unit": "fixture cohort",
            "allocation": "Keep one deterministic fixture cohort unexposed",
            "eligibility_criteria": ["Both cohorts use the same runtime and metric definition"],
            "minimum_duration_days": 7,
            "guardrails": ["Stop if restart continuity degrades"],
            "measurements": [
                {
                    "capability_id": "restart-continuity",
                    "metric": "capability_quality",
                    "unit": "score_delta",
                    "baseline_source": "Structured fixture metric",
                    "outcome_source": "Structured fixture metric",
                    "cadence": "before and after restart",
                }
            ],
        },
    }
    forecast = build_forecast_contract(
        raw,
        decision_id=decision_id,
        product_id="product:i1restart",
        archetype="executor",
        discipline="reliability",
        model="deterministic-fixture-v1",
        current_state_baseline={"restart-continuity": 0.5},
        baseline_observed_at="2026-07-01T00:00:00Z",
        baseline_observation_refs=["test:f1:baseline"],
    )
    plan = forecast["evaluation"]["comparator_plan"]
    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        await db.query(
            "UPSERT decision_prediction:f1measurement SET "
            "decision = <record>$decision, product = product:i1restart, "
            "archetype = 'executor', discipline = 'reliability', horizon_days = 30, "
            "expected_changes = $expected_changes, primary_risk = $primary_risk, "
            "leading_indicators = $leading_indicators, falsification_condition = $falsification, "
            "contract_version = $contract_version, forecast_contract = $forecast_contract, "
            "comparator_plan_version = $plan_version, comparator_plan = $plan, "
            "comparator_plan_status = $plan_status, closed = false, "
            "resolution_status = 'open', created_at = time::now()",
            {
                "decision": decision_id,
                "expected_changes": raw["expected_changes"],
                "primary_risk": raw["primary_risk"],
                "leading_indicators": raw["leading_indicators"],
                "falsification": raw["falsification_condition"],
                "contract_version": forecast["contract_version"],
                "forecast_contract": forecast,
                "plan_version": plan["contract_version"],
                "plan": plan,
                "plan_status": plan["status"],
            },
        )
        return prediction_id, str(plan["plan_id"])
    finally:
        await db.close()


async def _make_prediction_overdue(db_url: str, prediction_id: str) -> None:
    db = AsyncSurreal(db_url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_i1_restart", "ace_i1_restart")
    try:
        await db.query(
            "UPDATE <record>$prediction SET created_at = time::now() - 31d",
            {"prediction": prediction_id},
        )
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
        await _assert_schema_version(db_url, 157)
        await _verify_legacy_rows_survive_v144(db_url)
        client = AceClient(base_url=api_url, token=token, timeout=10)
        thin_tools._client = client

        extension_submission = await client.post(
            "/extension-invocations",
            json={
                "contract_version": "extension-invocation-v1",
                "extension_id": "restart_fixture",
                "extension_version": "1.0.0",
                "action": "durable-retry",
                "workspace_id": "workspace:default",
                "question": "the restart fixture",
                "references": [
                    {
                        "namespace": "restart_fixture",
                        "kind": "evidence",
                        "id": "evidence:restart",
                        "version": "1",
                    }
                ],
                "correlation_id": "corr:i1-extension-restart",
                "idempotency_key": "i1-extension-restart-source",
            },
        )
        extension_task_id = extension_submission["id"]
        for _ in range(50):
            extension_status = await client.get(f"/tasks/{extension_task_id}")
            if extension_status["status"] == "completed":
                break
            await asyncio.sleep(0.1)
        assert extension_status["extension_receipt"]["coverage"]["state"] == "complete"
        interrupted_extension_id = await _seed_interrupted_extension_invocation(db_url, extension_task_id)

        deliberation_ids: dict[str, str] = {}

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
                    i2_receipt = status["task"]["deliberation_receipt"]
                    assert i2_receipt["contract_version"] == "deliberation-receipt-v1"
                    assert i2_receipt["completeness"]["state"] == "complete"
                    deliberation_ids[state] = i2_receipt["receipt_id"]
                    return task_id, receipt["decision_id"]
                await asyncio.sleep(0.1)
            raise AssertionError("deterministic task did not complete")

        identities = {state: await submit_decision(state) for state in ("unresolved", "accepted", "edited", "rejected")}
        _, accepted_decision_id = identities["accepted"]
        intervention_prediction_id = await _seed_intervention_prediction(db_url, accepted_decision_id)
        intervention_payload = {
            "request_id": "i1-intervention-restart-v1",
            "decision_id": accepted_decision_id,
            "prediction_id": intervention_prediction_id,
            "status": "partial",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "applicability_conditions_met": True,
            "conditions": [
                {
                    "condition": "The deterministic restart fixture is active",
                    "met": True,
                    "evidence_refs": ["test:i1-restart:intervention"],
                }
            ],
            "exposure": {"degree": 0.5, "scope": "restart fixture", "unit": "fraction"},
            "evidence_refs": ["test:i1-restart:intervention"],
        }
        intervention_before = await thin_tools.ace_capture(
            observation_type="intervention",
            content="The restart fixture intervention is partially implemented.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            intervention=intervention_payload,
        )
        assert intervention_before["resolution_trigger"]["state"] == "awaiting_horizon"
        indicator_payload = {
            "request_id": "i1-indicator-restart-v1",
            "decision_id": accepted_decision_id,
            "prediction_id": intervention_prediction_id,
            "indicator_id": "indicator:1",
            "effect": "supports",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "value": 1.0,
            "unit": "continuity_observed",
            "evidence_refs": ["test:i1-restart:indicator"],
            "reason": "The same evidence remains visible before restart.",
        }
        indicator_before = await thin_tools.ace_capture(
            observation_type="forecast_indicator",
            content="Restart continuity remains visible.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            indicator=indicator_payload,
        )
        assert indicator_before["indicator_state"]["overall_state"] == "supports"
        comparator_payload = {
            "request_id": "i1-comparator-restart-v1",
            "decision_id": accepted_decision_id,
            "prediction_id": intervention_prediction_id,
            "comparator_type": "phased_rollout",
            "design": "matched",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "window_start": "2026-07-01T00:00:00Z",
            "window_end": "2026-07-15T00:00:00Z",
            "measurements": [
                {
                    "capability_id": "restart-continuity",
                    "intervention_before": 0.5,
                    "intervention_after": 0.7,
                    "comparator_before": 0.5,
                    "comparator_after": 0.55,
                    "evidence_refs": ["test:i1-restart:comparator"],
                }
            ],
            "evidence_refs": ["test:i1-restart:comparator"],
            "reason": "Matched restart fixture cohorts.",
            "execution": {
                "assignment_unit": "fixture cohort",
                "eligibility_criteria_met": True,
                "guardrail_breaches": [],
                "deviations": [],
            },
        }
        comparator_before = await thin_tools.ace_capture(
            observation_type="forecast_comparator",
            content="A matched restart comparator remains visible.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            comparator=comparator_payload,
        )
        assert comparator_before["comparator"]["resolution_eligible"] is True
        assert comparator_before["resolution_trigger"]["state"] == "awaiting_horizon"

        f1_prediction_id, f1_plan_id = await _seed_f1_measurement_prediction(db_url, accepted_decision_id)
        f1_intervention_payload = {
            "request_id": "f1-closeout-intervention-v1",
            "decision_id": accepted_decision_id,
            "prediction_id": f1_prediction_id,
            "status": "completed",
            "observed_at": "2026-07-15T00:00:00Z",
            "applicability_conditions_met": True,
            "conditions": [
                {
                    "condition": "The deterministic F1 fixture is active",
                    "met": True,
                    "evidence_refs": ["test:f1:intervention"],
                }
            ],
            "exposure": {"degree": 1.0, "scope": "fixture cohort", "unit": "cohort"},
            "evidence_refs": ["test:f1:intervention"],
        }
        f1_intervention = await thin_tools.ace_capture(
            observation_type="intervention",
            content="The deterministic F1 intervention completed.",
            domain_path="f1.closeout.measurement",
            confidence=1.0,
            intervention=f1_intervention_payload,
        )
        assert f1_intervention["resolution_trigger"]["state"] == "awaiting_horizon"
        await _make_prediction_overdue(db_url, f1_prediction_id)

        measurement_points = [
            ("intervention", "baseline", 0.50),
            ("intervention", "outcome", 0.70),
            ("comparator", "baseline", 0.50),
            ("comparator", "outcome", 0.55),
        ]
        f1_measurement_results = []
        for arm, phase, value in measurement_points:
            payload = {
                "request_id": f"f1-closeout-{arm}-{phase}-v1",
                "decision_id": accepted_decision_id,
                "prediction_id": f1_prediction_id,
                "plan_id": f1_plan_id,
                "run_id": "f1-closeout-run-v1",
                "source_type": "structured_metric",
                "capability_id": "restart-continuity",
                "metric": "capability_quality",
                "unit": "score_delta",
                "arm": arm,
                "phase": phase,
                "value": value,
                "measured_at": ("2026-07-01T00:00:00Z" if phase == "baseline" else "2026-07-15T00:00:00Z"),
                "window_start": "2026-07-01T00:00:00Z",
                "window_end": "2026-07-15T00:00:00Z",
                "comparator_type": "holdout",
                "design": "matched",
                "evidence_refs": [f"test:f1:{arm}:{phase}"],
                "execution": {
                    "plan_id": f1_plan_id,
                    "assignment_unit": "fixture cohort",
                    "allocation": "Keep one deterministic fixture cohort unexposed",
                    "eligibility_criteria_met": True,
                    "guardrail_breaches": [],
                    "deviations": [],
                },
            }
            result = await thin_tools.ace_capture(
                observation_type="forecast_measurement",
                content=f"Observed the {arm} {phase} metric for F1 closeout.",
                domain_path="f1.closeout.measurement",
                confidence=1.0,
                measurement=payload,
            )
            f1_measurement_results.append((payload, result))

        assert [result["ingestion"]["status"] for _, result in f1_measurement_results] == [
            "collecting",
            "collecting",
            "collecting",
            "ingested",
        ]
        f1_final_measurement = f1_measurement_results[-1][1]
        assert f1_final_measurement["measurement"]["resolution_eligible"] is False
        assert f1_final_measurement["ingestion"]["comparator"]["resolution_eligible"] is True
        assert f1_final_measurement["ingestion"]["resolution_trigger"]["state"] == "resolved"
        assert f1_final_measurement["ingestion"]["resolution_trigger"]["score_eligible"] is True
        f1_comparator_id = f1_final_measurement["ingestion"]["comparator_observation_id"]
        f1_final_payload = f1_measurement_results[-1][0]

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
        interrupted_extension = await fresh_client.get(f"/tasks/{interrupted_extension_id}")
        assert interrupted_extension["status"] == "degraded"
        assert interrupted_extension["extension_receipt"]["attempt"]["resumable"] is True
        resumed_extension = await fresh_client.post(
            f"/extension-invocations/{interrupted_extension_id}/resume",
            json={},
        )
        resumed_extension_id = resumed_extension["id"]
        for _ in range(50):
            resumed_extension = await fresh_client.get(f"/tasks/{resumed_extension_id}")
            if resumed_extension["status"] == "completed":
                break
            await asyncio.sleep(0.1)
        resumed_receipt = resumed_extension["extension_receipt"]
        assert resumed_receipt["attempt"]["number"] == 2
        assert resumed_receipt["attempt"]["retry_of_task_id"] == interrupted_extension_id
        assert resumed_receipt["coverage"]["state"] == "complete"
        assert resumed_receipt["provenance"]["provider"] == "DeterministicFixtureProvider"
        prior_after_resume = await fresh_client.get(f"/tasks/{interrupted_extension_id}")
        assert prior_after_resume["extension_receipt"]["attempt"]["resumed_by_task_id"] == resumed_extension_id
        i3_task = await thin_tools.ace_task(
            "Exercise I3 material continuity after the real runtime restart",
            request_id="i3-closeout-fresh-restart-v1",
            decision={
                "selected_option": "Preserve the post-restart correction",
                "scope": "I3 fresh invocation restart acceptance",
                "assumptions": ["The retained correction remains active"],
                "alternatives": ["Ignore retained correction"],
                "reconsideration_conditions": ["The correction is invalidated"],
                "evidence_refs": [invalidating_id],
                "decision_type": "direction",
            },
        )
        i3_status = None
        for _ in range(50):
            i3_status = await thin_tools.ace_status(task_id=i3_task["id"])
            if i3_status["task"]["status"] == "completed":
                break
            await asyncio.sleep(0.1)
        assert i3_status is not None
        i3_receipt = i3_status["task"]["intelligence_use_receipt"]
        assert i3_receipt["contract_version"] == "intelligence-use-receipt-v1"
        assert i3_receipt["comparison"]["state"] == "matched"
        assert i3_receipt["material_intelligence_ids"] == [invalidating_id]
        assert i3_receipt["intelligence"][0]["evidence"]["decision_material"] is True
        assert i3_receipt["impact"]["beneficial_impact"] == "outcome_unsupported"
        assert i3_receipt["continuity"] == {
            "fresh_client_invocation": True,
            "runtime_restart": "real_supported_api_database_restart",
            "database_identity_preserved": True,
        }
        intervention_read = await fresh_client.get("/foresight/product:i1restart/interventions", params={"limit": 10})
        indicator_read = await fresh_client.get("/foresight/product:i1restart/indicators", params={"limit": 10})
        comparator_read = await fresh_client.get("/foresight/product:i1restart/comparators", params={"limit": 10})
        comparator_plan_read = await fresh_client.get(
            "/foresight/product:i1restart/comparator-plans", params={"limit": 10}
        )
        measurement_read = await fresh_client.get("/foresight/product:i1restart/measurements", params={"limit": 20})
        ingestion_read = await fresh_client.get(
            "/foresight/product:i1restart/measurement-ingestions", params={"limit": 10}
        )
        calibration_read = await fresh_client.get("/foresight/product:i1restart/calibration", params={"limit": 20})
        intervention_after = await thin_tools.ace_capture(
            observation_type="intervention",
            content="The restart fixture intervention is partially implemented.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            intervention=intervention_payload,
        )
        indicator_after = await thin_tools.ace_capture(
            observation_type="forecast_indicator",
            content="Restart continuity remains visible.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            indicator=indicator_payload,
        )
        comparator_after = await thin_tools.ace_capture(
            observation_type="forecast_comparator",
            content="A matched restart comparator remains visible.",
            domain_path="i1.restart.foresight",
            confidence=1.0,
            comparator=comparator_payload,
        )
        f1_measurement_after = await thin_tools.ace_capture(
            observation_type="forecast_measurement",
            content="Observed the comparator outcome metric for F1 closeout.",
            domain_path="f1.closeout.measurement",
            confidence=1.0,
            measurement=f1_final_payload,
        )

        for state, (state_task_id, state_decision_id) in identities.items():
            after_status = await thin_tools.ace_status(task_id=state_task_id)
            receipt = after_status["task"]["decision_receipt"]
            assert receipt["decision_id"] == state_decision_id
            assert receipt["originating_task_id"] == state_task_id
            assert receipt["human_disposition"]["state"] == state
            assert receipt["completeness"]["state"] == "complete"
            assert receipt["provenance"]["state"] == "complete"
            i2_receipt = after_status["task"]["deliberation_receipt"]
            assert i2_receipt["receipt_id"] == deliberation_ids[state]
            assert i2_receipt["coverage"]["state"] == "complete"
            assert i2_receipt["contributors"][0]["artifact"]["evidence_ids"] == ["test:i2:restart"]

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
        assert intervention_after["status"] == "duplicate"
        assert intervention_after["id"] == intervention_before["id"]
        restored = {item["observation_id"]: item for item in intervention_read["interventions"]}
        assert restored[intervention_before["id"]]["status"] == "partial"
        assert restored[intervention_before["id"]]["prediction_id"] == intervention_prediction_id
        assert restored[intervention_before["id"]]["compatibility"]["state"] == "current"
        assert indicator_after["status"] == "duplicate"
        assert indicator_after["id"] == indicator_before["id"]
        restored_indicators = {item["observation_id"]: item for item in indicator_read["indicators"]}
        assert restored_indicators[indicator_before["id"]]["effect"] == "supports"
        assert restored_indicators[indicator_before["id"]]["prediction_id"] == intervention_prediction_id
        assert comparator_after["status"] == "duplicate"
        assert comparator_after["id"] == comparator_before["id"]
        restored_comparators = {item["observation_id"]: item for item in comparator_read["comparators"]}
        assert restored_comparators[comparator_before["id"]]["resolution_eligible"] is True
        assert restored_comparators[comparator_before["id"]]["prediction_id"] == intervention_prediction_id
        assert restored_comparators[comparator_before["id"]]["plan_alignment"]["state"] == "aligned"
        assert restored_comparators[comparator_before["id"]]["plan_alignment"]["link_method"] == (
            "prediction_plan_auto_link"
        )
        restored_plans = {item["prediction_id"]: item["plan"] for item in comparator_plan_read["plans"]}
        restored_plan = restored_plans[intervention_prediction_id]
        assert restored_plan["contract_version"] == "ace.foresight.comparator-plan/v1"
        assert restored_plan["status"] == "proposed"
        assert restored_plan["evidence_status"] == "plan_only_not_observed"
        assert restored_plan["resolution_eligible"] is False
        assert f1_measurement_after["status"] == "duplicate"
        assert f1_measurement_after["id"] == f1_final_measurement["id"]
        assert f1_measurement_after["ingestion"]["status"] == "ingested"
        assert f1_measurement_after["ingestion"]["comparator_observation_id"] == f1_comparator_id
        restored_measurements = {item["sample"]["observation_id"]: item for item in measurement_read["measurements"]}
        assert (
            len(
                [item for item in restored_measurements.values() if item["sample"]["prediction_id"] == f1_prediction_id]
            )
            == 4
        )
        assert restored_measurements[f1_final_measurement["id"]]["sample"]["resolution_eligible"] is False
        f1_ingestions = {item["prediction_id"]: item for item in ingestion_read["ingestions"]}
        assert f1_ingestions[f1_prediction_id]["status"] == "ingested"
        assert f1_ingestions[f1_prediction_id]["receipt"]["comparator_observation_id"] == f1_comparator_id
        restored_f1_comparator = restored_comparators[f1_comparator_id]
        assert restored_f1_comparator["plan_alignment"]["state"] == "aligned"
        assert restored_f1_comparator["effect_method"] == "difference_in_differences/v1"
        f1_outcomes = [item for item in calibration_read["outcomes"] if item["prediction_id"] == f1_prediction_id]
        assert len(f1_outcomes) == 1
        assert f1_outcomes[0]["score_eligible"] is True
        assert f1_outcomes[0]["actual_deltas"]["restart-continuity"] == pytest.approx(0.15)
        assert f1_outcomes[0]["prediction_score"]["state"] == "scored"
        assert f1_outcomes[0]["comparator_context"]["plan_id"] == f1_plan_id
    finally:
        thin_tools._client = None
        if client:
            await client.close()
        await _stop(api_process)
        await _stop(db_process)
        api_log.close()
        db_log.close()
