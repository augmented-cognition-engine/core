from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from core.engine.api import tasks
from core.engine.api.tasks import TaskCreate, TaskResumeRequest


def _task(*, status: str = "degraded", task_id: str = "task:root") -> dict:
    body = TaskCreate(
        description="Re-run durable work",
        workspace_id="workspace:test",
        model="budget",
        execution_limits={"wall_time_seconds": 5},
    )
    return {
        "id": task_id,
        "status": status,
        "contract_version": "async-receipt-v1",
        "product": "product:test",
        "workspace": "workspace:test",
        "user": "user:test",
        "description": body.description,
        "request_options": body.model_dump(exclude={"idempotency_key", "wait_seconds"}, exclude_none=True),
        "attempt": tasks._new_task_attempt(task_id),
    }


@pytest.fixture(autouse=True)
async def clean_runtime():
    tasks._active_tasks.clear()
    tasks._resume_locks.clear()
    tasks._accepting_tasks = True
    yield
    jobs = list(tasks._active_tasks.values())
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    tasks._active_tasks.clear()
    tasks._resume_locks.clear()


@pytest.mark.asyncio
async def test_degraded_direct_task_creates_one_linked_successor_and_replays_it():
    records = {"task:root": _task()}
    submissions = 0

    async def get_record(task_id: str):
        return records.get(task_id)

    async def update_record(task_id: str, fields: dict):
        records[task_id].update(fields)
        return records[task_id]

    async def submit(body, user, **kwargs):
        nonlocal submissions
        submissions += 1
        assert body.description == "Re-run durable work"
        assert body.execution_limits.wall_time_seconds == 5
        task_id = kwargs["requested_task_id"]
        records[task_id] = {
            "id": task_id,
            "status": "pending",
            "product": user["product"],
            "workspace": body.workspace_id,
            "user": user["sub"],
            "attempt": kwargs["task_attempt"],
        }
        return tasks._public_task(records[task_id])

    user = {"sub": "user:test", "product": "product:test", "workspace": "workspace:test"}
    with (
        patch.object(tasks, "_get_task_record", new=get_record),
        patch.object(tasks, "_update_receipt", new=update_record),
        patch.object(tasks, "submit_task", new=submit),
    ):
        first = await tasks.resume_task(
            "task:root",
            TaskResumeRequest(reason="runtime restarted", policy_version="operator-v1"),
            user,
        )
        replay = await tasks.resume_task("task:root", None, user)

    assert submissions == 1
    assert first["id"].startswith("task:retry_")
    assert replay["id"] == first["id"]
    assert replay["idempotent_replay"] is True
    assert records["task:root"]["attempt"]["resumed_by_task_id"] == first["id"]
    assert first["attempt"]["number"] == 2
    assert first["attempt"]["root_task_id"] == "task:root"
    assert first["attempt"]["retry_of_task_id"] == "task:root"
    assert first["attempt"]["retry_reason"] == "runtime restarted"
    assert first["attempt"]["retry_actor"] == "user:test"
    assert first["attempt"]["retry_policy_version"] == "operator-v1"


@pytest.mark.asyncio
async def test_concurrent_resume_requests_share_one_successor():
    records = {"task:root": _task()}
    submissions = 0

    async def get_record(task_id: str):
        return records.get(task_id)

    async def update_record(task_id: str, fields: dict):
        records[task_id].update(fields)
        return records[task_id]

    async def submit(body, user, **kwargs):
        nonlocal submissions
        submissions += 1
        await asyncio.sleep(0)
        task_id = kwargs["requested_task_id"]
        records[task_id] = {
            "id": task_id,
            "status": "pending",
            "product": user["product"],
            "workspace": body.workspace_id,
            "user": user["sub"],
            "attempt": kwargs["task_attempt"],
        }
        return tasks._public_task(records[task_id])

    user = {"sub": "user:test", "product": "product:test"}
    with (
        patch.object(tasks, "_get_task_record", new=get_record),
        patch.object(tasks, "_update_receipt", new=update_record),
        patch.object(tasks, "submit_task", new=submit),
    ):
        first, second = await asyncio.gather(
            tasks.resume_task("task:root", None, user),
            tasks.resume_task("task:root", None, user),
        )

    assert submissions == 1
    assert first["id"] == second["id"]
    assert {first["idempotent_replay"], second["idempotent_replay"]} == {False, True}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "running", "completed", "cancelled"])
async def test_non_resumable_states_replay_same_receipt(status: str):
    record = _task(status=status)
    submit = AsyncMock()
    with (
        patch.object(tasks, "_get_task_record", new=AsyncMock(return_value=record)),
        patch.object(tasks, "submit_task", new=submit),
    ):
        receipt = await tasks.resume_task("task:root", None, {"sub": "user:test", "product": "product:test"})
    assert receipt["id"] == "task:root"
    assert receipt["idempotent_replay"] is True
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_route_cannot_bypass_extension_repreparation():
    record = _task()
    record["extension_invocation"] = {"contract_version": "extension-invocation-v1"}
    with patch.object(tasks, "_get_task_record", new=AsyncMock(return_value=record)):
        with pytest.raises(HTTPException) as exc:
            await tasks.resume_task("task:root", None, {"sub": "user:test", "product": "product:test"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "extension_retry_route_required"


@pytest.mark.asyncio
async def test_resume_fails_closed_on_conflicting_attempt_lineage():
    record = _task()
    record["attempt"]["contract_version"] = "task-attempt-v999"
    with patch.object(tasks, "_get_task_record", new=AsyncMock(return_value=record)):
        with pytest.raises(HTTPException) as exc:
            await tasks.resume_task("task:root", None, {"sub": "user:test", "product": "product:test"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "task_attempt_contract_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda record: record["request_options"].update(workspace_id="workspace:other"),
            "task_request_scope_conflict",
        ),
        (lambda record: record.update(request_fingerprint="sha256:wrong"), "task_request_fingerprint_conflict"),
    ],
)
async def test_resume_fails_closed_when_durable_request_no_longer_matches_receipt(mutation, code: str):
    record = _task()
    mutation(record)
    with patch.object(tasks, "_get_task_record", new=AsyncMock(return_value=record)):
        with pytest.raises(HTTPException) as exc:
            await tasks.resume_task("task:root", None, {"sub": "user:test", "product": "product:test"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user",
    [
        {"sub": "user:other", "product": "product:test"},
        {"sub": "user:test", "product": "product:other"},
        {"sub": "user:test", "product": "product:test", "workspace": "workspace:other"},
    ],
)
async def test_resume_is_bound_to_original_product_principal_and_workspace(user: dict):
    with patch.object(tasks, "_get_task_record", new=AsyncMock(return_value=_task())):
        with pytest.raises(HTTPException) as exc:
            await tasks.resume_task("task:root", None, user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_first_receipt_is_created_with_predeclared_root_attempt_identity():
    body = TaskCreate(description="durable", workspace_id="workspace:test")
    created = {
        "id": "task:direct_test",
        "status": "pending",
        "attempt": tasks._new_task_attempt("task:direct_test"),
    }
    db = AsyncMock()
    db.query = AsyncMock(side_effect=[[], [], [created]])

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with (
        patch.object(tasks, "pool", new=FakePool()),
        patch.object(tasks, "_direct_task_id", return_value="task:direct_test"),
    ):
        receipt, was_created = await tasks._create_or_get_receipt(
            body,
            {"sub": "user:test", "product": "product:test"},
        )

    assert was_created is True
    assert receipt["id"] == "task:direct_test"
    create_call = db.query.await_args_list[2]
    assert "CREATE ONLY <record>$requested_task_id" in create_call.args[0]
    assert str(create_call.args[1]["requested_task_id"]) == "task:direct_test"
    assert create_call.args[1]["attempt"]["root_task_id"] == "task:direct_test"


def test_v177_declares_generic_task_attempt_projection():
    migration = Path(tasks.__file__).parents[2] / "schema" / "v177_task_attempt_replay.surql"
    text = migration.read_text(encoding="utf-8")
    assert "DEFINE FIELD IF NOT EXISTS attempt ON TABLE task" in text
    assert "task_attempt_root" in text
    assert "value = '177'" in text
