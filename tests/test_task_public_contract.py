"""Deterministic public-contract tests for durable asynchronous ACE tasks."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from core.engine.api import tasks
from core.engine.api.tasks import TaskCreate
from core.engine.extensions.invocation import (
    ExtensionInvocationEnvelope,
    ExtensionOutcome,
    ExtensionTaskPlan,
    RegisteredTaskAction,
    invocation_metadata,
)
from core.engine.orchestration.executor import OrchestrationResult, _persist_task
from core.engine.orchestration.request import OrchestrationRequest


def _result(*, status: str = "completed", error: str | None = None) -> OrchestrationResult:
    return OrchestrationResult(
        task_id=None,
        output="durable output" if status == "completed" else "",
        classification={
            "domain_path": "public.contract",
            "discipline": "engineering",
            "archetype": "executor",
            "mode": "deliberative",
        },
        snapshot={
            "total_count": 2,
            "token_usage": {
                "total_tokens": 42,
                "providers": ["OllamaProvider"],
                "models": ["qwen3:4b"],
            },
        },
        events=[],
        status=status,
        error=error,
        duration_ms=31_001,
    )


class MemoryReceiptStore:
    def __init__(self, task_id: str = "task:receipt") -> None:
        self.task_id = task_id
        self.state = {"id": task_id, "status": "pending", "product": "product:test"}
        self.created = False

    async def create_or_get(self, _body, _user):
        if self.created:
            return self.state, False
        self.created = True
        return self.state, True

    async def update(self, _task_id, fields):
        self.state.update(fields)
        return self.state

    async def get(self, _task_id):
        return self.state


@pytest.fixture(autouse=True)
async def clean_runtime():
    tasks._active_tasks.clear()
    tasks._accepting_tasks = True
    yield
    jobs = list(tasks._active_tasks.values())
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    tasks._active_tasks.clear()


@pytest.mark.asyncio
async def test_simulated_31_second_task_returns_receipt_then_survives_disconnect():
    """A virtual 31s result is completed after the submitting call has returned."""
    store = MemoryReceiptStore()
    release = asyncio.Event()

    async def slow_orchestrate(request):
        assert request.task_id == store.task_id
        await release.wait()
        return _result()

    body = TaskCreate(description="slow work", workspace_id="workspace:test")
    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_create_or_get_receipt", new=store.create_or_get),
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch("core.engine.orchestration.orchestrate", new=slow_orchestrate),
    ):
        started = time.monotonic()
        receipt = await tasks.create_task(body, user)
        elapsed = time.monotonic() - started

        assert elapsed < 0.5
        assert receipt["id"] == store.task_id
        assert receipt["status"] in {"pending", "running"}
        assert receipt["retrieval"]["tool"] == "ace_status"

        # The original call is gone.  Releasing the deterministic slow fixture
        # models provider completion after a generic 30s client would have died.
        release.set()
        await tasks._active_tasks[store.task_id]
        completed = await tasks.get_task(store.task_id, user)

    assert completed["status"] == "completed"
    assert completed["output"] == "durable output"
    assert completed["model_calls"]["actual"] == 0
    assert completed["latency"]["task_wall_ms"] == 31_001
    assert completed["latency"]["first_useful_result_ms"] == 31_001
    assert completed["reasoning_trace"]["provenance"] == {
        "task_id": store.task_id,
        "provider": "OllamaProvider",
        "model": "OllamaProvider:qwen3:4b",
        "duration_ms": 31_001,
        "token_usage": {
            "total_tokens": 42,
            "providers": ["OllamaProvider"],
            "models": ["qwen3:4b"],
        },
    }
    assert completed["decision_receipt"]["contract_version"] == "decision-receipt-v1"
    assert completed["deliberation_receipt"]["contract_version"] == "deliberation-receipt-v1"
    assert completed["intelligence_use_receipt"]["contract_version"] == "intelligence-use-receipt-v1"
    assert completed["extension_receipt"] == {}


def test_pre_acceptance_call_estimate_is_bounded_and_explained():
    estimate = tasks._estimate_task_model_calls(
        TaskCreate(
            description="deep analysis",
            workspace_id="workspace:test",
            deep=True,
            force_skill="architecture",
            frameworks_hint=["a", "b"],
        )
    )
    assert estimate["low"] <= estimate["expected"] <= estimate["high"]
    assert estimate["expected_serial_wall_ms"] == estimate["expected"] * estimate["assumed_call_ms"]
    assert estimate["soft_limit"] >= 1
    assert estimate["method"] == "heuristic_v1"
    assert "deep_framework_composition" in estimate["reasons"]


def test_bounded_output_contract_estimates_one_call_plus_conditional_repair():
    estimate = tasks._estimate_task_model_calls(
        TaskCreate(
            description="Return exactly three concise bullets with a measurable metric in every bullet",
            workspace_id="workspace:test",
        )
    )

    assert estimate["low"] == 1
    assert estimate["expected"] == 1
    assert estimate["bounded_high"] == 2
    assert estimate["high"] == estimate["escalated_high"]
    assert estimate["high"] > estimate["bounded_high"]
    assert estimate["method"] == "bounded_contract_v1"


def test_execution_receipt_exposes_bounded_route_without_claiming_semantic_verification():
    stage_plan = {
        "planner": "dynamic_stage_policy_v1",
        "route": "bounded_interactive",
        "stages": [{"stage": "ace_intelligence_probe", "selected": True, "reason": "no_llm_indexed_retrieval"}],
        "intelligence": {"retrieved": 1, "injected": 1, "relevant_conflicts": 0},
    }
    result = SimpleNamespace(
        pattern_result=None,
        output="- result",
        snapshot={
            "bounded_interactive": {
                "selected": True,
                "attempts": 1,
                "contract": "exactly 1 bullet(s)",
                "validation": "deterministic_shape",
                "semantic_verification": "not_claimed",
            }
        },
        classification={"routing_governance": {"stage_plan": stage_plan}},
    )

    execution = tasks._execution_coverage(result)

    assert execution["bounded_interactive"] == {
        "selected": True,
        "attempts": 1,
        "contract": "exactly 1 bullet(s)",
        "validation": "deterministic_shape",
        "semantic_verification": "not_claimed",
    }
    assert execution["stage_plan"] == stage_plan


@pytest.mark.asyncio
async def test_completed_receipt_records_adaptive_shadow_evidence_without_an_evaluator_call():
    store = MemoryReceiptStore()
    result = _result()
    adaptive_plan = {
        "planner": "adaptive_reasoning_shadow_v1",
        "advisory_only": True,
        "priority": "balanced",
        "stages": [
            {"stage": "semantic_classification", "selected": True},
            {"stage": "ace_intelligence", "selected": True},
            {"stage": "verification", "selected": False},
        ],
    }
    result.classification["routing_governance"] = {"adaptive_stage_plan": adaptive_plan}
    result.snapshot["token_usage"] = {
        "llm_calls": [
            {
                "stage": "classification",
                "retry_count": 0,
            }
        ],
        "calls": [],
        "latency": {
            "call_count": 1,
            "retry_count": 0,
            "stages": {"classification": {"calls": 1}},
        },
        "total_tokens": 20,
        "providers": ["OllamaProvider"],
        "models": ["qwen3:4b"],
    }

    async def orchestrate(_request):
        return result

    body = TaskCreate(description="balanced work", workspace_id="workspace:test")
    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_create_or_get_receipt", new=store.create_or_get),
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch("core.engine.orchestration.orchestrate", new=orchestrate),
        patch.object(tasks, "_persist_structured_decision", new=AsyncMock(return_value={})),
    ):
        receipt = await tasks.create_task(body, user)
        await tasks._active_tasks[receipt["id"]]
        completed = await tasks.get_task(receipt["id"], user)

    evidence = completed["execution"]["adaptive_evidence"]
    assert evidence["advisory_only"] is True
    assert evidence["actual"]["model_calls"] == 1
    assert evidence["actual"]["task_wall_ms"] == 31_001
    assert evidence["quality_evidence"]["user_feedback"] == "not_yet_available"
    assert evidence["comparison"]["stages"][0]["agreement"] is True


@pytest.mark.asyncio
async def test_retry_reuses_receipt_without_duplicate_orchestration():
    store = MemoryReceiptStore()
    release = asyncio.Event()
    calls = 0

    async def slow_orchestrate(_request):
        nonlocal calls
        calls += 1
        await release.wait()
        return _result()

    body = TaskCreate(
        description="same submission",
        workspace_id="workspace:test",
        idempotency_key="caller-retry-1",
    )
    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_create_or_get_receipt", new=store.create_or_get),
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch("core.engine.orchestration.orchestrate", new=slow_orchestrate),
    ):
        first = await tasks.create_task(body, user)
        await asyncio.sleep(0)
        retry = await tasks.create_task(body, user)
        assert first["id"] == retry["id"]
        assert retry["idempotent_replay"] is True
        assert calls == 1
        release.set()
        await tasks._active_tasks[store.task_id]


@pytest.mark.asyncio
async def test_explicit_retry_key_rejects_a_different_request():
    body = TaskCreate(
        description="new request",
        workspace_id="workspace:test",
        idempotency_key="caller-retry-1",
    )
    db = AsyncMock()
    db.query = AsyncMock(
        return_value=[
            {
                "id": "task:existing",
                "status": "completed",
                "request_fingerprint": "fingerprint-for-a-different-request",
            }
        ]
    )

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with patch.object(tasks, "pool", new=FakePool()):
        with pytest.raises(HTTPException) as exc:
            await tasks._create_or_get_receipt(body, {"sub": "user:test", "product": "product:test"})
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_executor_does_not_prematurely_complete_a_precreated_receipt():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[{"id": "task:receipt"}])

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    request = OrchestrationRequest(
        task_id="task:receipt",
        description="durable work",
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:test",
    )
    with (
        patch("core.engine.core.db.pool", new=FakePool()),
        patch("core.engine.orchestration.executor.get_accumulator", return_value=None),
    ):
        task_id = await _persist_task(request, {"domain_path": "engineering"}, {}, "result")

    assert task_id == "task:receipt"
    query = db.query.call_args.args[0]
    assert "status = 'running'" in query
    assert "status = 'completed'" not in query


@pytest.mark.asyncio
async def test_short_task_can_return_completed_result_in_bounded_wait_window():
    store = MemoryReceiptStore()
    body = TaskCreate(description="short", workspace_id="workspace:test", wait_seconds=1)
    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_create_or_get_receipt", new=store.create_or_get),
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch("core.engine.orchestration.orchestrate", new=AsyncMock(return_value=_result())),
    ):
        response = await tasks.create_task(body, user)
    assert response["status"] == "completed"
    assert response["output"] == "durable output"


@pytest.mark.asyncio
async def test_failed_and_degraded_states_are_explicit_and_errors_are_bounded():
    store = MemoryReceiptStore()
    secret_error = "provider failed at /srv/example/private/repo token=super-secret-value"
    with (
        patch.object(tasks, "_update_receipt", new=store.update),
        patch(
            "core.engine.orchestration.orchestrate",
            new=AsyncMock(return_value=_result(status="failed", error=secret_error)),
        ),
    ):
        await tasks._execute_receipt(
            store.task_id,
            TaskCreate(description="fail", workspace_id="workspace:test"),
            {"sub": "user:test", "product": "product:test"},
        )
    assert store.state["status"] == "failed"
    message = store.state["error"]["message"]
    assert "super-secret-value" not in message
    assert "/srv/" not in message
    assert len(message) <= 400

    store.state["status"] = "running"
    store.state["error"] = {
        "code": "runtime_restarted",
        "message": "The API runtime restarted before orchestration completed.",
    }
    assert tasks._public_task(store.state)["status"] == "running"
    store.state["status"] = "degraded"
    assert tasks._public_task(store.state)["error"]["code"] == "runtime_restarted"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["projector_exception", "validator_rejection"])
async def test_projection_failure_preserves_completed_task_and_raw_output(failure_mode):
    store = MemoryReceiptStore(task_id=f"task:{failure_mode}")
    envelope = ExtensionInvocationEnvelope(
        extension_id="example",
        extension_version="1.0.0",
        action="project",
        workspace_id="workspace:test",
        question="Return one bounded recommendation.",
        references=[],
        correlation_id="corr:projection-failure",
    )
    plan = ExtensionTaskPlan(
        description="Return one bounded recommendation.",
        outcome_contract="example-outcome-v1",
    )

    def project(output, _execution):
        if failure_mode == "projector_exception":
            raise RuntimeError("token=projector-private")
        return ExtensionOutcome(
            contract_version="example-outcome-v1",
            data={"recommendation": output},
        )

    def validate(_outcome):
        if failure_mode == "validator_rejection":
            raise ValueError("api_key=validator-private")

    action = RegisteredTaskAction(
        extension_id="example",
        extension_version="1.0.0",
        action="project",
        prepare=lambda _envelope, _actor: plan,
        project_outcome=project,
        validate_outcome=validate,
        output_contract="example-outcome-v1",
    )
    metadata = invocation_metadata(envelope, plan, action)
    metadata_attempt = dict(metadata["attempt"])
    body = TaskCreate(description=plan.description, workspace_id="workspace:test")
    user = {"sub": "user:test", "product": "product:test"}

    with (
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch.object(
            tasks,
            "_persist_structured_decision",
            new=AsyncMock(return_value={"contract_version": "decision-receipt-v1"}),
        ),
        patch("core.engine.orchestration.orchestrate", new=AsyncMock(return_value=_result())),
        patch("core.engine.extensions.registry.registered_task_action", return_value=action),
    ):
        await tasks._execute_receipt(
            store.task_id,
            body,
            user,
            extension_invocation=metadata,
        )

    receipt = store.state["extension_receipt"]
    serialized = str(receipt)
    assert store.state["status"] == "completed"
    assert store.state["output"] == "durable output"
    assert store.state["error"] is None
    assert receipt["attempt"]["status"] == "completed"
    assert receipt["raw_core_output"] == {
        "available": True,
        "content": "durable output",
    }
    assert receipt["outcome"]["data"] == {}
    assert receipt["coverage"]["state"] == "degraded"
    assert "extension_outcome_projection" in receipt["coverage"]["missing_or_degraded"]
    assert receipt["failures"][0]["code"] == "outcome_projection_failed"
    assert receipt["human_decision"] is None
    assert receipt["adoption"] is None
    assert metadata["attempt"] == metadata_attempt
    assert "projector-private" not in serialized
    assert "validator-private" not in serialized
    assert "<redacted>" in serialized


def test_nested_agent_error_is_used_when_top_level_failure_is_empty():
    result = _result(status="failed")
    result.pattern_result = SimpleNamespace(
        agent_results=[SimpleNamespace(error="provider unavailable at /internal/provider token=secret-value")]
    )
    message = tasks._bounded_public_error(tasks._orchestration_error(result))["message"]
    assert "provider unavailable" in message
    assert "/internal/" not in message
    assert "secret-value" not in message


def test_execution_coverage_surfaces_partial_committee_without_exposing_secrets():
    result = _result()
    result.pattern_result = SimpleNamespace(
        pattern_name="team",
        agent_results=[
            SimpleNamespace(agent_id="researcher", status="completed", duration_ms=120, error=None),
            SimpleNamespace(
                agent_id="skeptic",
                status="timeout",
                duration_ms=300_000,
                error="tool timed out at /internal/tools token=secret-value",
            ),
            SimpleNamespace(agent_id="synthesizer", status="completed", duration_ms=80, error=None),
        ],
    )

    coverage = tasks._execution_coverage(result)

    assert coverage["state"] == "partial"
    assert coverage["usable_output"] is True
    assert coverage["contributors"]["total"] == 3
    assert coverage["contributors"]["completed"] == 2
    assert coverage["contributors"]["timed_out"] == 1
    assert coverage["contributors"]["coverage_ratio"] == 0.6667
    assert coverage["attention"]["required"] is True
    public_error = coverage["contributors"]["items"][1]["error"]["message"]
    assert "/internal/" not in public_error
    assert "secret-value" not in public_error


@pytest.mark.asyncio
async def test_usable_partial_result_stays_completed_but_receipt_exposes_coverage():
    store = MemoryReceiptStore()
    result = _result()
    result.pattern_result = SimpleNamespace(
        pattern_name="fanout",
        agent_results=[
            SimpleNamespace(agent_id="arm-a", status="failed", duration_ms=10, error="provider timeout"),
            SimpleNamespace(agent_id="arm-b", status="completed", duration_ms=20, error=None),
        ],
    )
    with (
        patch.object(tasks, "_update_receipt", new=store.update),
        patch("core.engine.orchestration.orchestrate", new=AsyncMock(return_value=result)),
    ):
        await tasks._execute_receipt(
            store.task_id,
            TaskCreate(description="partial", workspace_id="workspace:test"),
            {"sub": "user:test", "product": "product:test"},
        )

    assert store.state["status"] == "completed"
    assert store.state["output"] == "durable output"
    assert store.state["execution"]["state"] == "partial"
    assert store.state["execution"]["contributors"]["failed"] == 1


def test_budget_model_alias_resolves_before_provider_execution():
    from core.engine.core.config import settings

    assert tasks._resolve_task_model("budget") == settings.llm_budget_model
    assert tasks._resolve_task_model("provider:model") == "provider:model"
    assert tasks._resolve_task_model(None) is None


@pytest.mark.asyncio
async def test_completed_task_receipt_resolves_selected_route_when_usage_is_empty():
    from core.engine.core.config import settings
    from core.engine.core.llm import llm

    store = MemoryReceiptStore()
    result = _result()
    result.snapshot["token_usage"] = {
        "total_tokens": 0,
        "providers": [],
        "models": [],
    }

    class SelectedProvider:
        def _resolve_model(self, requested):
            return f"native:{requested}"

    with (
        patch.object(tasks, "_update_receipt", new=store.update),
        patch.object(llm, "_cached_provider", new=SelectedProvider()),
        patch("core.engine.orchestration.orchestrate", new=AsyncMock(return_value=result)),
    ):
        await tasks._execute_receipt(
            store.task_id,
            TaskCreate(description="route provenance", workspace_id="workspace:test"),
            {"sub": "user:test", "product": "product:test"},
        )

    provenance = store.state["reasoning_trace"]["provenance"]
    assert provenance["provider"] == "SelectedProvider"
    assert provenance["requested_model"] == settings.llm_model
    assert provenance["model"] == f"native:{settings.llm_model}"


@pytest.mark.asyncio
async def test_task_retrieval_enforces_product_ownership():
    store = MemoryReceiptStore()
    with patch.object(tasks, "_get_task_record", new=store.get):
        with pytest.raises(HTTPException) as exc:
            await tasks.get_task(store.task_id, {"sub": "user:other", "product": "product:other"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_runtime_restart_reconciliation_marks_interrupted_rows_degraded():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[{"id": "task:old", "status": "degraded"}])

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with patch.object(tasks, "pool", new=FakePool()):
        count = await tasks.initialize_task_runtime()
    assert count == 1
    query = db.query.call_args.args[0]
    assert "status = 'degraded'" in query
    assert "runtime_id != $runtime_id" in query
    assert "process_stopped_during_cancellation" in query
    assert "cancellation_process_unavailable" in query


@pytest.mark.asyncio
async def test_client_poll_timeout_does_not_masquerade_as_task_failure(monkeypatch):
    from ace_mcp_client.client import AceClient

    client = AceClient()
    client.get = AsyncMock(return_value={"id": "task:slow", "status": "running"})
    result = await client.wait_for_task("task:slow", timeout=0)
    assert result["status"] == "running"
    assert result["polling"]["status"] == "timed_out"
    assert "still be running" in result["polling"]["message"]


@pytest.mark.asyncio
async def test_ace_status_retrieves_task_through_existing_tool():
    import ace_mcp_client.tools as thin_tools

    client = AsyncMock()
    client.get = AsyncMock(return_value={"id": "task:done", "status": "completed", "output": "ok"})
    old_client = thin_tools._client
    thin_tools._client = client
    try:
        result = await thin_tools.ace_status(filter="task:done")
    finally:
        thin_tools._client = old_client
    assert result["status"] == "completed"
    assert result["task"]["output"] == "ok"
    client.get.assert_awaited_once_with("/tasks/task:done")


@pytest.mark.asyncio
async def test_cancellation_records_completed_before_request(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "_get_task_record",
        AsyncMock(return_value={"id": "task:done", "status": "completed"}),
    )
    update = AsyncMock(side_effect=lambda task_id, fields: {"id": task_id, "status": "completed", **fields})
    monkeypatch.setattr(tasks, "_update_receipt", update)

    result = await tasks.cancel_task_execution("task:done", actor="user:one", reason="too late")

    assert result["cancellation"]["state"] == "completed_before_cancellation"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_supported_cancellation_persists_requested_then_acknowledged():
    store = MemoryReceiptStore(task_id="task:cancel-active")
    release = asyncio.Event()
    updates: list[str] = []

    async def blocked_orchestrate(_request):
        await release.wait()
        return _result()

    async def update(task_id, fields):
        cancellation = fields.get("cancellation")
        if isinstance(cancellation, dict):
            updates.append(str(cancellation.get("state")))
        return await store.update(task_id, fields)

    body = TaskCreate(description="cancel this work", workspace_id="workspace:test")
    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_create_or_get_receipt", new=store.create_or_get),
        patch.object(tasks, "_update_receipt", new=update),
        patch.object(tasks, "_get_task_record", new=store.get),
        patch("core.engine.orchestration.orchestrate", new=blocked_orchestrate),
    ):
        await tasks.create_task(body, user)
        await asyncio.sleep(0)
        result = await tasks.cancel_task_execution(
            store.task_id,
            actor="user:test",
            reason="no longer needed",
        )

    assert result["status"] == "cancelled"
    assert result["cancellation"]["state"] == "acknowledged"
    assert result["cancellation"]["requested_at"] is not None
    assert result["cancellation"]["acknowledged_at"] is not None
    assert updates == ["requested", "acknowledged"]


@pytest.mark.asyncio
async def test_cancellation_records_process_stopped_when_runtime_job_is_absent(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "_get_task_record",
        AsyncMock(return_value={"id": "task:orphan", "status": "running"}),
    )
    updates: list[dict] = []

    async def update(task_id, fields):
        updates.append(fields)
        return {"id": task_id, **fields}

    monkeypatch.setattr(tasks, "_update_receipt", update)
    monkeypatch.setattr(tasks, "_active_tasks", {})

    result = await tasks.cancel_task_execution("task:orphan", actor="user:one", reason="stop")

    assert result["status"] == "degraded"
    assert result["cancellation"]["state"] == "process_stopped_during_cancellation"
    assert [item["cancellation"]["state"] for item in updates] == [
        "requested",
        "process_stopped_during_cancellation",
    ]


@pytest.mark.asyncio
async def test_cancellation_rechecks_terminal_state_before_reporting_stopped_process(monkeypatch):
    get = AsyncMock(
        side_effect=[
            {"id": "task:raced", "status": "running"},
            {"id": "task:raced", "status": "completed"},
        ]
    )
    monkeypatch.setattr(tasks, "_get_task_record", get)
    updates: list[dict] = []

    async def update(task_id, fields):
        updates.append(fields)
        return {"id": task_id, "status": "completed", **fields}

    monkeypatch.setattr(tasks, "_update_receipt", update)
    monkeypatch.setattr(tasks, "_active_tasks", {})

    result = await tasks.cancel_task_execution("task:raced", actor="user:one", reason="stop")

    assert result["status"] == "completed"
    assert result["cancellation"]["state"] == "completed_before_cancellation"
    assert [item["cancellation"]["state"] for item in updates] == [
        "requested",
        "completed_before_cancellation",
    ]
