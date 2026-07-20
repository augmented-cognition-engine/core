"""Regression tests for the durable-receipt M3 rehearsal caller."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from scripts import verify_m3_rehearsal


@pytest.mark.asyncio
async def test_initial_rehearsal_polls_the_durable_task_receipt(tmp_path):
    marker_state = tmp_path / "state.json"
    first = AsyncMock()
    first.get = AsyncMock(return_value={"status": "ok"})
    first.submit_task = AsyncMock(
        return_value={
            "id": "task:receipt",
            "status": "completed",
            "output": "Reliability first.",
            "reasoning_trace": {"provenance": {"model": "CLIProvider:test"}},
        }
    )
    first.post = AsyncMock(return_value={"id": "observation:receipt"})
    fresh = AsyncMock()
    fresh.get = AsyncMock(return_value={"insights": []})

    clients = iter((first, fresh))
    with (
        patch.object(verify_m3_rehearsal, "AceClient", side_effect=lambda **_kwargs: next(clients)),
        patch.object(verify_m3_rehearsal.uuid, "uuid4", return_value=type("U", (), {"hex": "fixedmarker0"})()),
    ):
        fresh.get.return_value = {"insights": [{"content": "m31-fixedmarke: prefer reliability"}]}
        await verify_m3_rehearsal._initial("http://test", 123, marker_state)

    first.submit_task.assert_awaited_once()
    assert first.submit_task.await_args.kwargs == {"wait": True, "wait_timeout": 123}
    state = json.loads(marker_state.read_text())
    assert state["task_id"] == "task:receipt"
    assert state["task_status"] == "completed"
