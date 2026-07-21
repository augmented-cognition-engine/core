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


def test_nested_agent_error_is_used_when_top_level_failure_is_empty():
    result = _result(status="failed")
    result.pattern_result = SimpleNamespace(
        agent_results=[SimpleNamespace(error="provider unavailable at /internal/provider token=secret-value")]
    )
    message = tasks._bounded_public_error(tasks._orchestration_error(result))["message"]
    assert "provider unavailable" in message
    assert "/internal/" not in message
    assert "secret-value" not in message


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
